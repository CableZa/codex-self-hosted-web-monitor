from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "extract-release-notes.py"
SPEC = importlib.util.spec_from_file_location("extract_release_notes", SCRIPT_PATH)
assert SPEC is not None
extract_release_notes_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(extract_release_notes_module)


class ExtractReleaseNotesTests(unittest.TestCase):
    def test_extracts_only_requested_version(self) -> None:
        changelog = """# Changelog

## Unreleased

- Future change.

## v0.17.0 - 2026-06-23

### Fixed

- Current release fix.

## v0.16.0 - 2026-06-23

- Older release.
"""

        notes = extract_release_notes_module.extract_release_notes(changelog, "v0.17.0")

        self.assertIn("Current release fix", notes)
        self.assertNotIn("Future change", notes)
        self.assertNotIn("Older release", notes)
        self.assertNotIn("## v0.17.0", notes)

    def test_accepts_refs_tags_prefix(self) -> None:
        changelog = """# Changelog

## v0.17.0 - 2026-06-23

- Current release fix.
"""

        notes = extract_release_notes_module.extract_release_notes(changelog, "refs/tags/v0.17.0")

        self.assertEqual("- Current release fix.\n", notes)

    def test_missing_version_fails(self) -> None:
        with self.assertRaises(ValueError):
            extract_release_notes_module.extract_release_notes("# Changelog\n", "v9.9.9")


if __name__ == "__main__":
    unittest.main()
