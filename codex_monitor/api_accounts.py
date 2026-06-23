from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any, Callable

import codex_usage

try:
    from fastapi import HTTPException
except ImportError:  # pragma: no cover
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

from .api_http import validate_outbound_url
from .api_refs import store
from .api_timing import logger, timed_dependency
from .session_signals import SESSION_SIGNAL_THRESHOLD_DEFAULTS, SESSION_SIGNAL_THRESHOLD_KEYS

AUTH_SNAPSHOT_SOURCE = "codex_auth"
MAX_ACCOUNT_FILTERS = int(os.environ.get("MAX_ACCOUNT_FILTERS", "50"))
AUTO_ACCOUNT_LIMIT_CAP_CREDITS = 400
AUTO_ACCOUNT_LIMIT_RESET_WEEKDAY = 4
AUTO_ACCOUNT_LIMIT_RESET_TIME = "00:00"
AUTO_ACCOUNT_LIMIT_TIMEZONE = "UTC"
AUTO_ACCOUNT_LIMIT_THRESHOLDS = [0.7, 0.85, 0.95, 1.0]
VISIBLE_USAGE_HISTORY_TTL_SECONDS = 60
_logged_missing_auth_files: set[str] = set()
_logged_unreadable_auth_files: set[str] = set()
_visible_usage_history_cache: dict[str, dict[str, Any]] = {}


def codex_auth_warning(codex_home: Path) -> str | None:
    auth_path = codex_home.expanduser() / "auth.json"
    if not auth_path.exists():
        message = f"Codex auth file was not found: {auth_path}."
        key = str(auth_path)
        if key not in _logged_missing_auth_files:
            logger.warning("codex_auth_file_missing path=%s", auth_path)
            _logged_missing_auth_files.add(key)
        return message
    if not auth_path.is_file():
        message = f"Codex auth path is not a file: {auth_path}."
        key = str(auth_path)
        if key not in _logged_unreadable_auth_files:
            logger.warning("codex_auth_file_unreadable path=%s reason=not_file", auth_path)
            _logged_unreadable_auth_files.add(key)
        return message
    return None


def decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
        return json.loads(decoded.decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return {}


def read_codex_auth_identity(codex_home: Path) -> dict[str, Any] | None:
    auth_path = codex_home.expanduser() / "auth.json"
    warning = codex_auth_warning(codex_home)
    if warning:
        return None
    try:
        with timed_dependency("service.auth_file", path=str(auth_path)):
            data = json.loads(auth_path.read_text(encoding="utf-8"))
    except OSError as exc:
        key = str(auth_path)
        if key not in _logged_unreadable_auth_files:
            logger.warning("codex_auth_file_unreadable path=%s reason=%s", auth_path, exc)
            _logged_unreadable_auth_files.add(key)
        return None
    except json.JSONDecodeError as exc:
        key = str(auth_path)
        if key not in _logged_unreadable_auth_files:
            logger.warning("codex_auth_file_unreadable path=%s reason=json_decode_error line=%s", auth_path, exc.lineno)
            _logged_unreadable_auth_files.add(key)
        return None

    tokens = data.get("tokens") if isinstance(data, dict) else {}
    if not isinstance(tokens, dict):
        return None
    claims = decode_jwt_payload(str(tokens.get("id_token") or ""))
    account_id = str(tokens.get("account_id") or claims.get("sub") or "").strip()
    email = str(claims.get("email") or "").strip().lower()
    name = str(claims.get("name") or "").strip()
    if not any((account_id, email, name)):
        return None
    return {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "account_id": account_id or None,
        "email": email or None,
        "name": name or None,
        "source": AUTH_SNAPSHOT_SOURCE,
    }


def parse_snapshot_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def account_label(snapshot: dict[str, Any]) -> str:
    return str(snapshot.get("email") or snapshot.get("account_id") or "unknown")


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.environ.get(name, default)).strip())
    except ValueError:
        return default


def _env_float_list(name: str, default: list[float]) -> list[float]:
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        return list(default)
    values: list[float] = []
    for item in raw.split(","):
        try:
            values.append(float(item.strip()))
        except ValueError:
            return list(default)
    return values or list(default)


def auto_account_limit_defaults() -> dict[str, Any]:
    suffixes = sorted({
        item.strip().lower()
        for item in str(os.environ.get("AUTO_ACCOUNT_LIMIT_EMAIL_SUFFIXES", "")).split(",")
        if item.strip()
    })
    return {
        "email_suffixes": suffixes,
        "cap_credits": _env_int("AUTO_ACCOUNT_LIMIT_CAP_CREDITS", AUTO_ACCOUNT_LIMIT_CAP_CREDITS),
        "reset_weekday": _env_int("AUTO_ACCOUNT_LIMIT_RESET_WEEKDAY", AUTO_ACCOUNT_LIMIT_RESET_WEEKDAY),
        "reset_time": str(os.environ.get("AUTO_ACCOUNT_LIMIT_RESET_TIME", AUTO_ACCOUNT_LIMIT_RESET_TIME)).strip() or AUTO_ACCOUNT_LIMIT_RESET_TIME,
        "timezone": str(os.environ.get("AUTO_ACCOUNT_LIMIT_TIMEZONE", AUTO_ACCOUNT_LIMIT_TIMEZONE)).strip() or AUTO_ACCOUNT_LIMIT_TIMEZONE,
        "thresholds": _env_float_list("AUTO_ACCOUNT_LIMIT_THRESHOLDS", AUTO_ACCOUNT_LIMIT_THRESHOLDS),
    }


def is_auto_account_limit_account(account: str | None, defaults: dict[str, Any] | None = None) -> bool:
    normalized = str(account or "").strip().lower()
    suffixes = list((defaults or auto_account_limit_defaults()).get("email_suffixes") or [])
    return bool(normalized) and any(normalized.endswith(str(suffix).lower()) for suffix in suffixes)


def auto_account_limit_payload(account: str, defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    defaults = defaults or auto_account_limit_defaults()
    return {
        "account": account.strip().lower(),
        "metric": "total_credits",
        "cap_value": float(defaults["cap_credits"]),
        "reset_weekday": int(defaults["reset_weekday"]),
        "reset_time": str(defaults["reset_time"]),
        "timezone": str(defaults["timezone"]),
        "thresholds": list(defaults["thresholds"]),
        "enabled": True,
    }


def confirmed_account_labels(snapshots: list[dict[str, Any]]) -> set[str]:
    return {
        label
        for snapshot in snapshots
        if (label := account_label(snapshot)) != "unknown"
    }


def first_auth_snapshot_at(snapshots: list[dict[str, Any]]) -> str | None:
    observed = [
        str(snapshot["observed_at"])
        for snapshot in snapshots
        if snapshot.get("observed_at")
    ]
    if not observed:
        return None
    return min(observed, key=parse_snapshot_time)


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def visible_usage_history(codex_home: Path | None = None) -> dict[str, Any]:
    base = (codex_home or Path(os.environ.get("CODEX_HOME", codex_usage.DEFAULT_CODEX_HOME))).expanduser()
    cache_key = str(base)
    cached = _visible_usage_history_cache.get(cache_key)
    now = monotonic()
    if cached and float(cached.get("expires_at") or 0) > now:
        return dict(cached["data"])

    roots = codex_usage.default_session_roots(base)
    discovered_files = codex_usage.discover_session_files(roots)
    resolved_roots = [root.expanduser().resolve(strict=False) for root in roots]
    sessions_root = resolved_roots[0] if resolved_roots else None
    archived_root = resolved_roots[1] if len(resolved_roots) > 1 else None
    sessions_root_files = 0
    archived_sessions_root_files = 0
    days: list[str] = []
    for path in discovered_files:
        resolved_path = path.expanduser().resolve(strict=False)
        if sessions_root and path_is_within(resolved_path, sessions_root):
            sessions_root_files += 1
        if archived_root and path_is_within(resolved_path, archived_root):
            archived_sessions_root_files += 1
        file_day = codex_usage.session_file_day(path)
        if file_day is not None:
            days.append(file_day.isoformat())

    data = {
        "earliest_usage_day": min(days) if days else None,
        "latest_usage_day": max(days) if days else None,
        "visible_rollout_files": len(discovered_files),
        "sessions_root_files": sessions_root_files,
        "archived_sessions_root_files": archived_sessions_root_files,
        "docker_mount_like": cache_key.replace("\\", "/").startswith("/codex"),
    }
    _visible_usage_history_cache[cache_key] = {
        "expires_at": now + VISIBLE_USAGE_HISTORY_TTL_SECONDS,
        "data": data,
    }
    return dict(data)


def account_resolver_from_snapshots(
    snapshots: list[dict[str, Any]],
    unknown_account_mapping: str | None = None,
) -> Callable[[codex_usage.UsageRecord], str]:
    ordered = sorted(
        (snapshot for snapshot in snapshots if snapshot.get("observed_at")),
        key=lambda snapshot: parse_snapshot_time(str(snapshot["observed_at"])),
    )
    unknown_account = str(unknown_account_mapping or "").strip() or "unknown"

    def resolver(record: codex_usage.UsageRecord) -> str:
        if not ordered:
            return unknown_account
        record_time = record.timestamp.astimezone(timezone.utc)
        chosen = None
        for snapshot in ordered:
            if parse_snapshot_time(str(snapshot["observed_at"])) <= record_time:
                chosen = snapshot
            else:
                break
        return account_label(chosen) if chosen else unknown_account

    return resolver


def parse_accounts_param(value: str | None) -> set[str] | None:
    if not value:
        return None
    accounts = {item.strip() for item in value.split(",") if item.strip()}
    if len(accounts) > MAX_ACCOUNT_FILTERS:
        raise HTTPException(status_code=400, detail=f"accounts may not include more than {MAX_ACCOUNT_FILTERS} values")
    return accounts or None


def validate_settings_updates(updates: dict[str, Any]) -> dict[str, Any]:
    validated = dict(updates)
    for key in ("daily_budget_credits", "weekly_budget_credits", "monthly_budget_credits"):
        if key in validated:
            raise HTTPException(
                status_code=400,
                detail=f"{key} is no longer supported; use per-account weekly credit limits instead",
            )
    if "account_credit_limit_migration_done" in validated:
        raise HTTPException(status_code=400, detail="account_credit_limit_migration_done is read-only")
    whole_number_keys = (
        "session_high_input_tokens",
        "session_high_uncached_input_tokens",
        "session_low_cache_min_uncached_tokens",
        "session_large_total_tokens",
        "session_high_output_tokens",
    )
    for key in whole_number_keys:
        if key not in validated or validated[key] is None:
            continue
        value = str(validated[key]).strip()
        if not value:
            raise HTTPException(status_code=400, detail=f"{key} must be a positive whole number")
        try:
            number = float(value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"{key} must be a whole number") from exc
        if number <= 0 or not number.is_integer():
            raise HTTPException(status_code=400, detail=f"{key} must be a positive whole number")
        validated[key] = str(int(number))
    if "session_low_cache_max_reuse_ratio" in validated and validated["session_low_cache_max_reuse_ratio"] is not None:
        value = str(validated["session_low_cache_max_reuse_ratio"]).strip()
        if not value:
            raise HTTPException(status_code=400, detail="session_low_cache_max_reuse_ratio must be between 0 and 1")
        try:
            number = float(value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="session_low_cache_max_reuse_ratio must be between 0 and 1") from exc
        if number < 0 or number > 1:
            raise HTTPException(status_code=400, detail="session_low_cache_max_reuse_ratio must be between 0 and 1")
        validated["session_low_cache_max_reuse_ratio"] = str(number)
    if "session_long_context_pricing_signal_enabled" in validated and validated["session_long_context_pricing_signal_enabled"] is not None:
        value = str(validated["session_long_context_pricing_signal_enabled"]).strip().lower()
        if value not in {"1", "true", "yes", "on", "0", "false", "no", "off"}:
            raise HTTPException(status_code=400, detail="session_long_context_pricing_signal_enabled must be true or false")
        validated["session_long_context_pricing_signal_enabled"] = "true" if value in {"1", "true", "yes", "on"} else "false"
    if "ui_theme" in validated and validated["ui_theme"] is not None:
        value = str(validated["ui_theme"]).strip().lower()
        if value not in {"catppuccin", "classic"}:
            raise HTTPException(status_code=400, detail="ui_theme must be catppuccin or classic")
        validated["ui_theme"] = value
    for key in ("webhook_url",):
        value = str(validated.get(key) or "").strip()
        if value:
            try:
                validate_outbound_url(value, key)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            validated[key] = value
    return validated


async def record_current_auth_snapshot() -> dict[str, Any] | None:
    codex_home = Path(os.environ.get("CODEX_HOME", codex_usage.DEFAULT_CODEX_HOME))
    snapshot = read_codex_auth_identity(codex_home)
    if not snapshot:
        return None
    inserted = await store.record_auth_snapshot(snapshot)
    snapshot["_inserted"] = inserted
    return snapshot


async def ensure_default_account_limits(accounts: list[str]) -> list[dict[str, Any]]:
    ensured: list[dict[str, Any]] = []
    seen: set[str] = set()
    defaults = auto_account_limit_defaults()
    for account in accounts:
        normalized = str(account or "").strip().lower()
        if not normalized or normalized in seen or not is_auto_account_limit_account(normalized, defaults):
            continue
        seen.add(normalized)
        row, inserted = await store.ensure_account_limit(auto_account_limit_payload(normalized, defaults))
        if inserted:
            row = {**row, "_inserted": True}
        ensured.append(row)
    return ensured


async def ensure_default_account_limits_from_snapshots(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return await ensure_default_account_limits([account_label(snapshot) for snapshot in snapshots])

def account_options_from_snapshots(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    options: dict[str, dict[str, Any]] = {}
    for snapshot in sorted(snapshots, key=lambda item: str(item.get("observed_at", ""))):
        label = account_label(snapshot)
        current = options.get(label, {"account": label, "first_seen": snapshot.get("observed_at")})
        current["last_seen"] = snapshot.get("observed_at")
        current["account_id"] = snapshot.get("account_id")
        current["email"] = snapshot.get("email")
        current["name"] = snapshot.get("name")
        current["source"] = snapshot.get("source")
        options[label] = current
    return sorted(options.values(), key=lambda item: str(item.get("account")))


def merge_usage_account_options(options: list[dict[str, Any]], accounts: list[str]) -> list[dict[str, Any]]:
    merged = {str(option.get("account")): dict(option) for option in options if option.get("account")}
    for account in accounts:
        if account not in merged:
            merged[account] = {"account": account, "source": "usage"}
    return sorted(merged.values(), key=lambda item: str(item.get("account")))


def validate_unknown_account_mapping(value: str | None, snapshots: list[dict[str, Any]]) -> str:
    mapping = str(value or "").strip()
    if not mapping:
        return ""
    known_accounts = confirmed_account_labels(snapshots)
    if mapping not in known_accounts:
        raise ValueError("unknown_account_mapping must be blank or one of the known accounts")
    return mapping
