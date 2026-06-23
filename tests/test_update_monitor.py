import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "update-monitor.py"


def load_update_monitor():
    spec = importlib.util.spec_from_file_location("update_monitor", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["update_monitor"] = module
    spec.loader.exec_module(module)
    return module


class UpdateMonitorTests(unittest.TestCase):
    def setUp(self):
        self.update_monitor = load_update_monitor()

    def test_semver_parse_and_order(self):
        versions = [
            self.update_monitor.SemVer.parse("0.7.1"),
            self.update_monitor.SemVer.parse("v0.8.0"),
            self.update_monitor.SemVer.parse("0.7.10"),
        ]

        self.assertEqual(str(sorted(versions)[-1]), "0.8.0")

    def test_write_status_adds_generated_at(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runtime" / "update-status.json"

            self.update_monitor.write_status(path, {"state": "up_to_date"})

            contents = path.read_text(encoding="utf-8")
        self.assertIn('"state": "up_to_date"', contents)
        self.assertIn('"generated_at"', contents)

    def test_run_command_missing_command_can_be_nonfatal(self):
        result = self.update_monitor.run_command(["definitely-missing-codex-monitor-command"], check=False)

        self.assertEqual(result.returncode, 127)

    def test_update_state_reports_checkout_version_when_running_is_older(self):
        with patch.object(self.update_monitor, "read_checkout_version", return_value="0.8.0"):
            with patch.object(self.update_monitor, "running_version", return_value="0.7.1"):
                with patch.object(self.update_monitor, "git_available", return_value=True):
                    with patch.object(self.update_monitor, "latest_remote_tag", return_value=("0.7.1", "v0.7.1")):
                        status = self.update_monitor.update_state("origin", "http://example.test/healthz", "docker")

        self.assertEqual(status["state"], "update_available")
        self.assertEqual(status["latest_version"], "0.8.0")
        self.assertIsNone(status["latest_tag"])
