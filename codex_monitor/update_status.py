from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STABLE_TAG_RE = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)$")
DEFAULT_TAGS_URL = "https://api.github.com/repos/CableZa/codex-self-hosted-web-monitor/tags?per_page=100"


@dataclass(frozen=True, order=True)
class SemVer:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> "SemVer":
        match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)$", value.strip())
        if not match:
            raise ValueError(f"invalid semver: {value}")
        return cls(*(int(part) for part in match.groups()))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def manual_update_command(install_mode: str | None) -> str:
    if install_mode == "docker":
        return "./scripts/update-and-redeploy"
    if install_mode == "local":
        return r"python .\scripts\update-monitor.py apply --install-mode local"
    return "python scripts/update-monitor.py apply"


def latest_tag_from_names(names: list[str]) -> tuple[str, str]:
    candidates: list[tuple[SemVer, str]] = []
    for name in names:
        match = STABLE_TAG_RE.match(name)
        if not match:
            continue
        candidates.append((SemVer.parse(match.group("version")), name))
    if not candidates:
        raise RuntimeError("no stable v*.*.* tags found")
    latest_version, latest_tag = sorted(candidates)[-1]
    return str(latest_version), latest_tag


def latest_tag_from_github_tags(payload: Any) -> tuple[str, str]:
    if not isinstance(payload, list):
        raise RuntimeError("release tag response must be a JSON list")
    names = [str(item.get("name", "")) for item in payload if isinstance(item, dict)]
    return latest_tag_from_names(names)


def update_state_from_latest(
    *,
    current_version: str | None,
    running_version: str | None,
    latest_version: str,
    latest_tag: str | None,
    install_mode: str,
    check_mode: str,
    source_url: str | None = None,
    remote: str | None = None,
) -> dict[str, Any]:
    checked_at = utc_now()
    compare_version = running_version or current_version
    state = "up_to_date"
    message = "Running version is current."
    if compare_version and SemVer.parse(latest_version) > SemVer.parse(compare_version):
        state = "update_available"
        message = f"Version {latest_version} is available."

    return {
        "state": state,
        "checked_at": checked_at,
        "current_version": current_version,
        "running_version": running_version,
        "latest_version": latest_version,
        "latest_tag": latest_tag,
        "install_mode": install_mode,
        "remote": remote,
        "check_mode": check_mode,
        "source_url": source_url,
        "manual_update_command": manual_update_command(install_mode),
        "message": message,
    }


def checking_failed_status(
    *,
    current_version: str | None,
    running_version: str | None,
    install_mode: str,
    check_mode: str,
    error: Exception | str,
    source_url: str | None = None,
    remote: str | None = None,
) -> dict[str, Any]:
    return {
        "state": "checking_failed",
        "checked_at": utc_now(),
        "current_version": current_version,
        "running_version": running_version,
        "latest_version": None,
        "latest_tag": None,
        "install_mode": install_mode,
        "remote": remote,
        "check_mode": check_mode,
        "source_url": source_url,
        "manual_update_command": manual_update_command(install_mode),
        "message": "Update check failed.",
        "error": str(error),
    }


async def http_update_state(
    *,
    http_client: Any,
    tags_url: str,
    current_version: str,
    install_mode: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    response = await http_client.get(tags_url, timeout=timeout_seconds)
    response.raise_for_status()
    latest_version, latest_tag = latest_tag_from_github_tags(response.json())
    return update_state_from_latest(
        current_version=current_version,
        running_version=current_version,
        latest_version=latest_version,
        latest_tag=latest_tag,
        install_mode=install_mode,
        check_mode="builtin_http",
        source_url=tags_url,
    )


def read_status_file(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def fresh_updating_status(path: Path, max_age_seconds: int) -> bool:
    status = read_status_file(path)
    if not status or status.get("state") != "updating":
        return False
    try:
        age_seconds = datetime.now(timezone.utc).timestamp() - path.stat().st_mtime
    except OSError:
        return False
    return age_seconds <= max_age_seconds


def write_status(path: Path, status: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": utc_now(), **status}
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)
