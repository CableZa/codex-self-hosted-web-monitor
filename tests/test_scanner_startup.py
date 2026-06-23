import asyncio
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

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


if __name__ == "__main__":
    unittest.main()
