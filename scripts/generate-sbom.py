#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
REQUIREMENT_RE = re.compile(r"^(?P<name>[A-Za-z0-9_.-]+)(?P<extras>\[[^\]]+\])?(?P<specifier>.*)$")
DEP_NAME_RE = re.compile(r"^\s*(?P<name>[A-Za-z0-9_.-]+)")
EXTRA_RE = re.compile(r"extra\s*==\s*['\"](?P<extra>[^'\"]+)['\"]")


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def component(name: str, version: str | None, component_type: str, scope: str | None = None, purl: str | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "type": component_type,
        "name": name,
    }
    if version:
        data["version"] = version
    if purl:
        data["purl"] = purl
    if scope:
        data["scope"] = scope
    return data


def pypi_purl(name: str, version: str) -> str:
    return f"pkg:pypi/{quote(normalize_name(name), safe='')}@{quote(version, safe='')}"


def npm_purl(name: str, version: str) -> str:
    return f"pkg:npm/{quote(name, safe='/')}@{quote(version, safe='')}"


def python_components(path: Path) -> list[dict[str, Any]]:
    distributions = {
        normalize_name(str(dist.metadata.get("Name") or "")): dist
        for dist in metadata.distributions()
        if dist.metadata.get("Name")
    }
    queued: list[tuple[str, set[str]]] = []
    missing_roots: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = REQUIREMENT_RE.match(line)
        if not match:
            continue
        requirement_name = match.group("name")
        name = normalize_name(match.group("name"))
        extras = match.group("extras") or ""
        if name not in distributions:
            missing_roots.append(requirement_name)
            continue
        queued.append((name, {item.strip() for item in extras.strip("[]").split(",") if item.strip()}))
    if missing_roots:
        missing = ", ".join(sorted(missing_roots, key=str.lower))
        raise RuntimeError(f"installed Python distributions are missing for requirements: {missing}")

    items: dict[str, dict[str, Any]] = {}
    while queued:
        name, active_extras = queued.pop(0)
        dist = distributions.get(name)
        if dist is None:
            continue
        dist_name = str(dist.metadata["Name"])
        normalized = normalize_name(dist_name)
        if normalized in items:
            continue
        items[normalized] = component(dist_name, dist.version, "library", purl=pypi_purl(dist_name, dist.version))
        for requirement in dist.requires or ():
            extra_match = EXTRA_RE.search(requirement)
            if extra_match and extra_match.group("extra") not in active_extras:
                continue
            dep_match = DEP_NAME_RE.match(requirement)
            if dep_match:
                queued.append((normalize_name(dep_match.group("name")), set()))
    return sorted(items.values(), key=lambda item: str(item["name"]).lower())


def npm_components(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    packages = data.get("packages", {})
    items: dict[tuple[str, str], dict[str, Any]] = {}
    scope_rank = {"excluded": 0, "optional": 1, "required": 2}
    for key, value in packages.items():
        if not key.startswith("node_modules/") or not isinstance(value, dict):
            continue
        name = str(value.get("name") or key.rsplit("node_modules/", 1)[-1])
        scope = "excluded" if value.get("dev") else "optional" if value.get("optional") else "required"
        version = str(value.get("version") or "")
        item_key = (name, version)
        existing = items.get(item_key)
        if existing is not None and scope_rank[str(existing["scope"])] >= scope_rank[scope]:
            continue
        items[item_key] = component(name, version, "library", scope, npm_purl(name, version))
    return sorted(items.values(), key=lambda item: (str(item["name"]).lower(), str(item.get("version") or "")))


def main() -> int:
    components = [
        component("codex-self-hosted-web-monitor", None, "application"),
        *python_components(ROOT / "requirements.txt"),
        *npm_components(ROOT / "package-lock.json"),
    ]
    bom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "component": component("codex-self-hosted-web-monitor", None, "application"),
        },
        "components": components,
    }
    print(json.dumps(bom, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
