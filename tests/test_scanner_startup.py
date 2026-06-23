import asyncio
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from codex_monitor.config import AppConfig


class ScannerStartupTests(unittest.TestCase):
    def test_scanner_initializes_requested_snapshot_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MONITOR_DB"] = os.path.join(tmp, "monitor.sqlite3")
            os.environ["VALKEY_URL"] = "redis://127.0.0.1:1/0"

            from codex_monitor import scanner
            from codex_monitor import api_app

            state = api_app.configure_runtime(AppConfig.from_env())
            generation = asyncio.run(state.store.bump_cache_generation("test"))
            state.store.conn.close()
            api_app.requested_snapshot_generation = 1

            with patch.object(api_app, "scanner_loop", AsyncMock()) as loop_mock:
                asyncio.run(scanner.main_async())

            loop_mock.assert_awaited_once()
            self.assertEqual(api_app.requested_snapshot_generation, generation)
            api_app.store.conn.close()

    def test_update_status_write_failure_does_not_stop_scanner(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["MONITOR_DB"] = os.path.join(tmp, "monitor.sqlite3")
            os.environ["VALKEY_URL"] = "redis://127.0.0.1:1/0"

            from codex_monitor import api_app
            from codex_monitor import api_scanner_runtime

            state = api_app.configure_runtime(AppConfig.from_env())
            api_app.UPDATE_CHECK_ENABLED = True
            api_app.UPDATE_CHECK_INTERVAL_SECONDS = 60
            api_app.UPDATE_CHECK_TAGS_URL = "https://example.test/tags"
            api_app.UPDATE_INSTALL_MODE = "docker"
            api_app.UPDATE_STATUS_PATH = Path(tmp) / "missing" / "status.json"
            api_scanner_runtime.last_update_check_monotonic = 0
            response = Mock()
            response.json.return_value = [{"name": "v0.17.0"}]
            response.raise_for_status.return_value = None

            with patch.object(state.http_client, "get", AsyncMock(return_value=response)):
                with patch.object(api_scanner_runtime, "write_status", side_effect=OSError("read-only")):
                    asyncio.run(api_scanner_runtime.maybe_check_for_updates())

            state.store.conn.close()


if __name__ == "__main__":
    unittest.main()
