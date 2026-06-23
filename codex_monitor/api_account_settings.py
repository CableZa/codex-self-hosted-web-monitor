from __future__ import annotations

import os
from datetime import date
from typing import Any
from zoneinfo import ZoneInfo

import codex_usage
from fastapi import HTTPException

from . import api_app as app_module
from .api_accounts import (
    confirmed_account_labels,
    parse_snapshot_time,
)
from .api_dates import iter_days
from .api_limits import validate_account_limit_payload
from .session_signals import SESSION_SIGNAL_THRESHOLD_KEYS

PUBLIC_SETTINGS_KEYS = {
    "daily_budget_zar",
    "weekly_budget_zar",
    "monthly_budget_zar",
    "pricing_mode",
    "usd_zar_fallback_rate",
    "webhook_url",
    "dashboard_url",
    "dashboard_mode",
    "ui_theme",
    "unknown_account_mapping",
    *SESSION_SIGNAL_THRESHOLD_KEYS,
}


def public_settings(settings: dict[str, str]) -> dict[str, str]:
    filtered = {key: value for key, value in settings.items() if key in PUBLIC_SETTINGS_KEYS}
    webhook_url = str(settings.get("webhook_url") or "").strip()
    webhook_ui_enabled = os.environ.get("WEBHOOK_UI_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
    filtered["webhook_ui_enabled"] = "true" if (webhook_ui_enabled or bool(webhook_url)) else "false"
    return filtered


async def cached_unknown_usage_totals(
    earliest_usage_day: str | None,
    first_snapshot_at: str | None,
    unknown_account_mapping: str,
) -> dict[str, Any] | None:
    if not earliest_usage_day or not first_snapshot_at or unknown_account_mapping.strip():
        return None
    prices = codex_usage.load_prices(codex_usage.DEFAULT_PRICES_PATH)
    cache_version = app_module.usage_aggregate_cache_version(prices, unknown_account_mapping)
    start_day = date.fromisoformat(earliest_usage_day)
    first_snapshot_day = parse_snapshot_time(first_snapshot_at).astimezone(ZoneInfo(app_module.DEFAULT_TZ)).date()
    expected_days = {day.isoformat() for day in iter_days(start_day, first_snapshot_day)}
    cached_days = await app_module.store.usage_aggregate_days(cache_version, start_day, first_snapshot_day)
    if cached_days != expected_days:
        return None
    rows = await app_module.store.usage_aggregate_rows(cache_version, start_day, first_snapshot_day, {"unknown"})
    combined = app_module.empty_usage_bucket()
    for row in rows:
        app_module.add_aggregate_row(combined, row)
    return app_module.bucket_as_report_row(combined)


async def account_attribution_report(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    settings = await app_module.store.settings()
    unknown_account_mapping = str(settings.get("unknown_account_mapping") or "")
    history = app_module.visible_usage_history()
    first_snapshot = app_module.first_auth_snapshot_at(snapshots)
    history["first_auth_snapshot_at"] = first_snapshot
    history["unknown_usage_totals"] = await app_module.cached_unknown_usage_totals(
        history.get("earliest_usage_day"),
        first_snapshot,
        unknown_account_mapping,
    )
    issues: list[dict[str, Any]] = []
    earliest_usage_day = str(history.get("earliest_usage_day") or "")
    latest_usage_day = str(history.get("latest_usage_day") or "")
    if earliest_usage_day and first_snapshot:
        first_snapshot_day = parse_snapshot_time(first_snapshot).astimezone(ZoneInfo(app_module.DEFAULT_TZ)).date()
        earliest_day = date.fromisoformat(earliest_usage_day)
        gap_days = (first_snapshot_day - earliest_day).days
        unknown_totals = history.get("unknown_usage_totals")
        has_unknown_before_first_snapshot = gap_days > 0 or bool(unknown_totals and float(unknown_totals.get("total_credits") or 0) > 0)
        if not unknown_account_mapping.strip() and has_unknown_before_first_snapshot:
            issues.append(
                {
                    "type": "unknown_usage_before_first_snapshot",
                    "severity": "warning",
                    "recommended_action": "add_manual_baseline_snapshot",
                    "detail": "Older usage appears before the first confirmed auth snapshot and may still be unattributed.",
                    "earliest_usage_day": earliest_usage_day,
                    "first_auth_snapshot_at": first_snapshot,
                    "unknown_usage_totals": unknown_totals,
                }
            )
        if gap_days >= 14:
            issues.append(
                {
                    "type": "late_first_snapshot",
                    "severity": "warning" if gap_days >= 30 else "info",
                    "recommended_action": "add_manual_baseline_snapshot",
                    "detail": f"The first confirmed auth snapshot was recorded {gap_days} days after visible usage history starts.",
                    "earliest_usage_day": earliest_usage_day,
                    "first_auth_snapshot_at": first_snapshot,
                    "unknown_usage_totals": unknown_totals,
                }
            )
    if history.get("docker_mount_like") and earliest_usage_day and latest_usage_day:
        visible_rollout_files = int(history.get("visible_rollout_files") or 0)
        archived_sessions_root_files = int(history.get("archived_sessions_root_files") or 0)
        span_days = (date.fromisoformat(latest_usage_day) - date.fromisoformat(earliest_usage_day)).days + 1
        if span_days >= 45 and visible_rollout_files <= 12:
            issues.append(
                {
                    "type": "sparse_visible_history",
                    "severity": "warning" if archived_sessions_root_files == 0 or span_days >= 90 else "info",
                    "recommended_action": "check_codex_host_home_mount",
                    "detail": f"The container can see only {visible_rollout_files} rollout files across {span_days} days of visible history.",
                    "earliest_usage_day": earliest_usage_day,
                    "first_auth_snapshot_at": first_snapshot,
                }
            )
    history.pop("docker_mount_like", None)
    return {"history": history, "issues": issues}


async def validated_confirmed_account_limit(payload: dict[str, Any]) -> dict[str, Any]:
    validated = validate_account_limit_payload(payload)
    snapshots = await app_module.store.auth_snapshots(limit=1000)
    if validated["account"] not in confirmed_account_labels(snapshots):
        raise HTTPException(status_code=400, detail="account must match a confirmed auth snapshot")
    return validated
