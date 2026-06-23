import asyncio
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch


class MonitorStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.environ["VALKEY_URL"] = "redis://127.0.0.1:1/0"

        import monitor_service

        self.monitor_service = monitor_service
        self.store = monitor_service.Store(Path(self.tmp.name) / "monitor.sqlite3")

    def tearDown(self):
        self.store.conn.close()

    def test_default_settings_and_fx_round_trip(self):
        settings = asyncio.run(self.store.settings())

        self.assertEqual(settings["pricing_mode"], "credits")
        self.assertEqual(settings["usd_zar_fallback_rate"], "18.50")
        self.assertEqual(settings["dashboard_url"], "http://127.0.0.1:8787")
        self.assertEqual(settings["ui_theme"], "catppuccin")
        self.assertEqual(settings["unknown_account_mapping"], "")
        self.assertEqual(settings["cache_generation"], "1")
        self.assertEqual(settings["session_high_input_tokens"], "1000000")
        self.assertEqual(settings["session_low_cache_max_reuse_ratio"], "0.5")
        self.assertEqual(settings["session_long_context_pricing_signal_enabled"], "true")
        self.assertTrue(float(settings["daily_budget_credits"]) > 0)
        self.assertEqual(float(settings["daily_budget_credits"]), round(float(settings["daily_budget_credits"])))

        asyncio.run(self.store.save_fx_rate(date(2026, 6, 3), 19.25, "test-source"))
        fx = asyncio.run(self.store.get_fx_rate(date(2026, 6, 3)))

        self.assertEqual(fx["day"], "2026-06-03")
        self.assertEqual(fx["usd_zar"], 19.25)
        self.assertEqual(fx["source"], "test-source")

    def test_cache_generation_defaults_and_bumps(self):
        self.assertEqual(asyncio.run(self.store.cache_generation()), 1)
        self.assertEqual(asyncio.run(self.store.bump_cache_generation("test")), 2)
        self.assertEqual(asyncio.run(self.store.cache_generation()), 2)
        self.assertEqual(asyncio.run(self.store.setting_generation("usage_cache_generation")), 1)
        self.assertEqual(asyncio.run(self.store.bump_setting_generation("usage_cache_generation", "test")), 2)
        self.assertEqual(asyncio.run(self.store.setting_generation("usage_cache_generation")), 2)

    def test_run_db_retries_locked_operations(self):
        attempts = 0

        def flaky_operation():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise sqlite3.OperationalError("database is locked")
            return "done"

        with patch("codex_monitor.api_store.time.sleep", return_value=None) as sleep_mock:
            result = self.store._run_db_operation(flaky_operation, 8, 0.05, None)

        self.assertEqual(result, "done")
        self.assertEqual(attempts, 3)
        self.assertEqual(sleep_mock.call_count, 2)

    def test_run_db_rolls_back_after_non_lock_sqlite_error(self):
        def failing_write():
            self.store.conn.execute("insert into settings(key, value) values(?, ?)", ("rollback-test", "1"))
            raise sqlite3.IntegrityError("expected failure after write")

        with self.assertRaises(sqlite3.IntegrityError):
            self.store._run_db_operation(failing_write, 1, 0.05, None)

        self.assertFalse(self.store.conn.in_transaction)
        self.assert_duplicate_write_releases_sqlite_lock()
        settings = asyncio.run(self.store.settings())
        self.assertNotIn("rollback-test", settings)

    def test_run_db_does_not_block_event_loop(self):
        entered = threading.Event()
        release = threading.Event()

        def slow_operation():
            entered.set()
            release.wait(timeout=1)
            return "done"

        async def exercise():
            started_at = time.perf_counter()
            task = asyncio.create_task(self.store._run_db(slow_operation))
            while not entered.is_set():
                await asyncio.sleep(0.001)
            await asyncio.sleep(0.01)
            tick_elapsed = time.perf_counter() - started_at
            release.set()
            result = await task
            return tick_elapsed, result

        tick_elapsed, result = asyncio.run(exercise())

        self.assertEqual(result, "done")
        self.assertLess(tick_elapsed, 0.2)

    def test_cancelled_run_db_keeps_lock_until_worker_finishes(self):
        entered = threading.Event()
        release = threading.Event()
        second_started = threading.Event()

        def slow_operation():
            entered.set()
            release.wait(timeout=1)
            return "done"

        def second_operation():
            second_started.set()
            return "second"

        async def exercise():
            first = asyncio.create_task(self.store._run_db(slow_operation))
            while not entered.is_set():
                await asyncio.sleep(0.001)
            first.cancel()
            second = asyncio.create_task(self.store._run_db(second_operation))
            await asyncio.sleep(0.02)
            second_started_before_release = second_started.is_set()
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await first
            second_result = await second
            return second_started_before_release, second_result

        second_started_before_release, second_result = asyncio.run(exercise())

        self.assertFalse(second_started_before_release)
        self.assertEqual(second_result, "second")

    def test_concurrent_store_calls_keep_fx_rows_correct(self):
        start_day = date(2026, 6, 4)

        async def exercise():
            await asyncio.gather(
                *(
                    self.store.save_fx_rate(start_day + timedelta(days=index), 18.0 + index, f"source-{index}")
                    for index in range(8)
                )
            )
            return await asyncio.gather(
                *(self.store.get_fx_rate(start_day + timedelta(days=index)) for index in range(8))
            )

        rows = asyncio.run(exercise())

        self.assertEqual([row["source"] for row in rows], [f"source-{index}" for index in range(8)])
        self.assertEqual([row["usd_zar"] for row in rows], [18.0 + index for index in range(8)])

    def test_auth_snapshot_dedupe_summary_uniqueness_and_alert_ordering(self):
        snapshot = {
            "observed_at": "2026-06-03T08:00:00+00:00",
            "account_id": "acct-1",
            "email": "work@example.com",
            "name": "Work",
            "source": "manual",
        }

        self.assertTrue(asyncio.run(self.store.record_auth_snapshot(snapshot)))
        self.assertFalse(asyncio.run(self.store.record_auth_snapshot(snapshot)))
        snapshots = asyncio.run(self.store.auth_snapshots())
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]["email"], "work@example.com")

        payload = {"type": "usage_summary", "period": "today"}
        self.assertTrue(asyncio.run(self.store.record_summary_once(date(2026, 6, 3), "10:00", payload)))
        self.assertFalse(asyncio.run(self.store.record_summary_once(date(2026, 6, 3), "10:00", payload)))

        budget_payload = {
            "type": "budget_alert",
            "period": "today",
            "period_start": "2026-06-03",
            "period_end": "2026-06-03",
            "budget_zar": 500,
            "current_zar": 600,
            "budget_credits": 10,
            "current_credits": 12,
            "unit": "credits",
        }
        account_payload = {
            "type": "account_limit_alert",
            "account": "work@example.com",
            "metric": "total_credits",
            "window_start": "2026-05-29T00:00:00+00:00",
            "window_end": "2026-06-05T00:00:00+00:00",
        }
        burn_payload = {
            "type": "account_burn_alert",
            "account": "work@example.com",
            "metric": "total_credits",
            "severity": "warning",
            "advisory_id": "projected-exhaustion",
            "window_start": "2026-05-29T00:00:00+00:00",
            "window_end": "2026-06-05T00:00:00+00:00",
        }
        asyncio.run(self.store.record_alert(budget_payload, 1.0))
        asyncio.run(self.store.record_account_limit_alert(account_payload, 0.7))
        self.assertTrue(asyncio.run(self.store.record_account_burn_alert(burn_payload)))
        self.assertFalse(asyncio.run(self.store.record_account_burn_alert(burn_payload)))
        self.store.conn.execute("update alerts set created_at = ? where id = 1", ("2026-06-03T08:00:00+00:00",))
        self.store.conn.execute(
            "update account_limit_alerts set created_at = ? where id = 1",
            ("2026-06-03T09:00:00+00:00",),
        )
        self.store.conn.execute(
            "update account_burn_alerts set created_at = ? where id = 1",
            ("2026-06-03T10:00:00+00:00",),
        )
        self.store.conn.commit()

        alerts = asyncio.run(self.store.alerts(limit=3))

        self.assertEqual([alert["payload"]["type"] for alert in alerts], ["account_burn_alert", "account_limit_alert", "budget_alert"])

    def assert_duplicate_write_releases_sqlite_lock(self):
        external_conn = sqlite3.connect(self.store.path, timeout=1)
        try:
            external_conn.execute("begin immediate")
            external_conn.rollback()
        finally:
            external_conn.close()

    def test_duplicate_record_summary_once_releases_sqlite_lock(self):
        payload = {"type": "usage_summary", "period": "today"}

        self.assertTrue(asyncio.run(self.store.record_summary_once(date(2026, 6, 3), "10:00", payload)))
        self.assertFalse(asyncio.run(self.store.record_summary_once(date(2026, 6, 3), "10:00", payload)))

        self.assert_duplicate_write_releases_sqlite_lock()

    def test_duplicate_record_account_limit_alert_releases_sqlite_lock(self):
        payload = {
            "type": "account_limit_alert",
            "account": "work@example.com",
            "metric": "total_credits",
            "window_start": "2026-05-29T00:00:00+00:00",
            "window_end": "2026-06-05T00:00:00+00:00",
        }

        self.assertTrue(asyncio.run(self.store.record_account_limit_alert(payload, 0.7)))
        self.assertFalse(asyncio.run(self.store.record_account_limit_alert(payload, 0.7)))

        self.assert_duplicate_write_releases_sqlite_lock()

    def test_duplicate_record_account_burn_alert_releases_sqlite_lock(self):
        payload = {
            "type": "account_burn_alert",
            "account": "work@example.com",
            "metric": "total_credits",
            "severity": "warning",
            "advisory_id": "projected-exhaustion",
            "window_start": "2026-05-29T00:00:00+00:00",
            "window_end": "2026-06-05T00:00:00+00:00",
        }

        self.assertTrue(asyncio.run(self.store.record_account_burn_alert(payload)))
        self.assertFalse(asyncio.run(self.store.record_account_burn_alert(payload)))

        self.assert_duplicate_write_releases_sqlite_lock()

    def test_daily_aggregate_save_read_filtering_and_warnings(self):
        row = {
            "day": "2026-06-03",
            "account": "work@example.com",
            "model": "gpt-5.5",
            "effort": "high",
            "input_tokens": 1000,
            "cached_input_tokens": 100,
            "output_tokens": 200,
            "reasoning_output_tokens": 0,
            "total_tokens": 1200,
            "input_usd": 0.001,
            "cached_input_usd": 0.00001,
            "output_usd": 0.002,
            "reasoning_output_usd": 0,
            "total_usd": 0.00301,
            "input_credits": 1,
            "cached_input_credits": 0.1,
            "output_credits": 2,
            "reasoning_output_credits": 0,
            "total_credits": 3.1,
            "long_context_applied": True,
            "events": 1,
            "sessions": {"session-1"},
            "files": {"rollout.jsonl"},
        }
        cache_version = "v3:test:test"

        asyncio.run(self.store.save_usage_daily_aggregate(cache_version, date(2026, 6, 3), [row], ["b", "a"]))

        days = asyncio.run(self.store.usage_aggregate_days(cache_version, date(2026, 6, 1), date(2026, 6, 5)))
        rows = asyncio.run(self.store.usage_aggregate_rows(cache_version, date(2026, 6, 1), date(2026, 6, 5)))
        filtered = asyncio.run(
            self.store.usage_aggregate_rows(
                cache_version,
                date(2026, 6, 1),
                date(2026, 6, 5),
                {"missing@example.com"},
            )
        )
        warnings = asyncio.run(self.store.usage_aggregate_warnings(cache_version, date(2026, 6, 1), date(2026, 6, 5)))

        self.assertEqual(days, {"2026-06-03"})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["account"], "work@example.com")
        self.assertEqual(rows[0]["long_context_applied"], 1)
        self.assertEqual(filtered, [])
        self.assertEqual(warnings, ["a", "b"])

    def test_prunes_obsolete_usage_aggregate_cache_schemas(self):
        row = {
            "day": "2026-06-03",
            "account": "work@example.com",
            "model": "gpt-5.5",
            "effort": "high",
            "input_tokens": 1000,
            "cached_input_tokens": 100,
            "output_tokens": 200,
            "reasoning_output_tokens": 0,
            "total_tokens": 1200,
            "input_usd": 0.001,
            "cached_input_usd": 0.00001,
            "output_usd": 0.002,
            "reasoning_output_usd": 0,
            "total_usd": 0.00301,
            "input_credits": 1,
            "cached_input_credits": 0.1,
            "output_credits": 2,
            "reasoning_output_credits": 0,
            "total_credits": 3.1,
            "long_context_applied": False,
            "events": 1,
            "sessions": {"session-1"},
            "files": {"rollout.jsonl"},
        }

        asyncio.run(self.store.save_usage_daily_aggregate("v2:test:test", date(2026, 6, 3), [row], []))
        asyncio.run(self.store.save_usage_daily_aggregate("v3:test:test", date(2026, 6, 4), [{**row, "day": "2026-06-04"}], []))

        deleted = asyncio.run(self.store.prune_usage_aggregate_cache_schemas("v3"))
        old_days = asyncio.run(self.store.usage_aggregate_days("v2:test:test", date(2026, 6, 1), date(2026, 6, 5)))
        current_days = asyncio.run(self.store.usage_aggregate_days("v3:test:test", date(2026, 6, 1), date(2026, 6, 5)))

        self.assertEqual(deleted, {"aggregate_rows": 1, "day_markers": 1})
        self.assertEqual(old_days, set())
        self.assertEqual(current_days, {"2026-06-04"})

    def test_account_limit_upsert_updates_existing_row(self):
        payload = {
            "account": "Work@Example.com",
            "metric": "total_tokens",
            "cap_value": 1000,
            "reset_weekday": 4,
            "reset_time": "06:00",
            "timezone": "UTC",
            "thresholds": [0.5, 0.9],
            "enabled": True,
        }

        first = asyncio.run(self.store.upsert_account_limit(payload))
        payload["cap_value"] = 2000
        payload["metric"] = "total_credits"
        second = asyncio.run(self.store.upsert_account_limit(payload))
        limits = asyncio.run(self.store.account_limits(enabled_only=False))

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(limits), 1)
        self.assertEqual(limits[0]["account"], "work@example.com")
        self.assertEqual(limits[0]["metric"], "total_credits")
        self.assertEqual(limits[0]["cap_value"], 2000)

    def test_ensure_account_limit_inserts_matching_default_without_overwriting_existing_row(self):
        first, first_inserted = asyncio.run(
            self.store.ensure_account_limit(
                {
                    "account": "User@Auto-Limit.example",
                    "metric": "total_credits",
                    "cap_value": 400,
                    "reset_weekday": 4,
                    "reset_time": "00:00",
                    "timezone": "UTC",
                    "thresholds": [0.7, 0.85, 0.95, 1.0],
                    "enabled": True,
                }
            )
        )
        second, second_inserted = asyncio.run(
            self.store.ensure_account_limit(
                {
                    "account": "user@auto-limit.example",
                    "metric": "total_credits",
                    "cap_value": 999,
                    "reset_weekday": 0,
                    "reset_time": "00:00",
                    "timezone": "UTC",
                    "thresholds": [1.0],
                    "enabled": False,
                }
            )
        )

        self.assertTrue(first_inserted)
        self.assertFalse(second_inserted)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(second["cap_value"], 400)
        self.assertEqual(second["reset_weekday"], 4)
        self.assertEqual(second["reset_time"], "00:00")
        self.assertEqual(second["timezone"], "UTC")
        self.assertEqual(second["enabled"], 1)


if __name__ == "__main__":
    unittest.main()
