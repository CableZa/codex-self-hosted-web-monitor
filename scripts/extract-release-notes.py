#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


VERSION_HEADING_RE = re.compile(r"^##\s+(?:\[)?v?(?P<version>\d+\.\d+\.\d+)(?:\])?(?:\s+-\s+.*)?\s*$")


def normalize_version(value: str) -> str:
    version = value.strip()
    if version.startswith("refs/tags/"):
        version = version.removeprefix("refs/tags/")
    return version.removeprefix("v")


def extract_release_notes(changelog: str, version: str) -> str:
    target = normalize_version(version)
    lines = changelog.splitlines()
    start: int | None = None

    for index, line in enumerate(lines):
        match = VERSION_HEADING_RE.match(line)
        if match and match.group("version") == target:
            start = index + 1
            break

    if start is None:
        raise ValueError(f"release notes for version {target} were not found")

    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break

    notes = "\n".join(lines[start:end]).strip()
    if not notes:
        raise ValueError(f"release notes for version {target} are empty")
    return notes + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract release notes for one changelog version.")
    parser.add_argument("version", help="Release version or tag, for example v0.17.0")
    parser.add_argument(
        "--changelog",
        type=Path,
        default=Path("CHANGELOG.md"),
        help="Changelog path. Defaults to CHANGELOG.md.",
    )
    args = parser.parse_args()

    try:
        notes = extract_release_notes(args.changelog.read_text(encoding="utf-8"), args.version)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(notes, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
