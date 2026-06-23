from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import api_store as store_module
from .update_status import manual_update_command
from .version import APP_VERSION

UPDATE_STATUS_PATH = store_module.SCRIPT_DIR / "runtime" / "update-status.json"
UPDATE_STATUS_MAX_AGE_SECONDS = int(os.environ.get("UPDATE_STATUS_MAX_AGE_SECONDS", "86400"))
RELEASE_HEADING_RE = re.compile(r"^##\s+v(?P<version>\d+\.\d+\.\d+)\s+-\s+(?P<date>\d{4}-\d{2}-\d{2})\s*$")
SECTION_HEADING_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$")
GROUP_HEADING_RE = re.compile(r"^###\s+(?P<name>.+?)\s*$")
BULLET_RE = re.compile(r"^\s*-\s+(?P<item>.+?)\s*$")


def non_empty_changelog_groups(section: dict[str, Any]) -> list[dict[str, Any]]:
    return [group for group in section["groups"] if group["items"]]


def changelog_section_has_items(section: dict[str, Any]) -> bool:
    return any(group["items"] for group in section["groups"])


def parse_changelog_markdown(markdown: str, limit: int) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    releases: list[dict[str, Any]] = []
    unreleased: dict[str, Any] | None = None
    current: dict[str, Any] | None = None
    current_group: dict[str, Any] | None = None

    def start_section(section: dict[str, Any]) -> None:
        nonlocal current, current_group
        current = section
        current_group = None

    for line in markdown.splitlines():
        release_match = RELEASE_HEADING_RE.match(line)
        if release_match:
            section = {
                "version": release_match.group("version"),
                "date": release_match.group("date"),
                "title": line.removeprefix("##").strip(),
                "groups": [],
            }
            releases.append(section)
            start_section(section)
            continue

        section_match = SECTION_HEADING_RE.match(line)
        if section_match:
            title = section_match.group("title").strip()
            if title.lower() == "unreleased":
                unreleased = {"version": None, "date": None, "title": title, "groups": []}
                start_section(unreleased)
            else:
                start_section({"version": None, "date": None, "title": title, "groups": []})
            continue

        if current is None:
            continue

        group_match = GROUP_HEADING_RE.match(line)
        if group_match:
            current_group = {"name": group_match.group("name").strip(), "items": []}
            current["groups"].append(current_group)
            continue

        bullet_match = BULLET_RE.match(line)
        if not bullet_match:
            continue

        if current_group is None:
            current_group = {"name": "Changes", "items": []}
            current["groups"].append(current_group)
        current_group["items"].append(bullet_match.group("item").strip())

    parsed_releases = [
        {**release, "groups": non_empty_changelog_groups(release)}
        for release in releases
        if changelog_section_has_items(release)
    ][:limit]
    parsed_unreleased = None
    if unreleased is not None and changelog_section_has_items(unreleased):
        parsed_unreleased = {**unreleased, "groups": non_empty_changelog_groups(unreleased)}
    return parsed_releases, parsed_unreleased


def read_update_status(path: Any = None) -> dict[str, Any]:
    status_path = path or UPDATE_STATUS_PATH
    generated_at = datetime.now(timezone.utc).isoformat()
    if not status_path.exists():
        return {
            "state": "unavailable",
            "generated_at": generated_at,
            "current_version": APP_VERSION,
            "manual_update_command": manual_update_command(None),
            "message": "No host update status has been written.",
        }
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "state": "checking_failed",
            "generated_at": generated_at,
            "current_version": APP_VERSION,
            "manual_update_command": manual_update_command(None),
            "message": "Could not read host update status.",
            "error": str(exc),
        }

    status.setdefault("generated_at", generated_at)
    status.setdefault("current_version", APP_VERSION)
    status.setdefault("manual_update_command", manual_update_command(status.get("install_mode")))
    try:
        age_seconds = datetime.now(timezone.utc).timestamp() - status_path.stat().st_mtime
        status["stale"] = age_seconds > UPDATE_STATUS_MAX_AGE_SECONDS
    except OSError:
        status["stale"] = False
    return status
