import importlib
import asyncio
import os
import sys
import tempfile
import types
import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo


class MonitorLimitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["MONITOR_DB"] = os.path.join(cls.tmp.name, "monitor.sqlite3")
        os.environ["VALKEY_URL"] = "redis://127.0.0.1:1/0"
        redis_stub = types.SimpleNamespace(
            Redis=types.SimpleNamespace(from_url=lambda *args, **kwargs: (_ for _ in ()).throw(Exception("no redis"))),
            RedisError=Exception,
        )
        sys.modules.setdefault("redis", redis_stub)
        class DummyFastAPI:
            def __init__(self, *args, **kwargs):
                pass

            def mount(self, *args, **kwargs):
                pass

            def middleware(self, *args, **kwargs):
                return lambda fn: fn

            def get(self, *args, **kwargs):
                return lambda fn: fn

            def put(self, *args, **kwargs):
                return lambda fn: fn

            def post(self, *args, **kwargs):
                return lambda fn: fn

        fastapi_stub = types.ModuleType("fastapi")
        fastapi_stub.FastAPI = DummyFastAPI
        fastapi_stub.HTTPException = Exception
        fastapi_stub.Request = object
        responses_stub = types.ModuleType("fastapi.responses")
        class DummyResponse:
            def __init__(self, *args, **kwargs):
                pass

        responses_stub.FileResponse = DummyResponse
        responses_stub.StreamingResponse = DummyResponse
        staticfiles_stub = types.ModuleType("fastapi.staticfiles")
        staticfiles_stub.StaticFiles = DummyResponse
        sys.modules.setdefault("fastapi", fastapi_stub)
        sys.modules.setdefault("fastapi.responses", responses_stub)
        sys.modules.setdefault("fastapi.staticfiles", staticfiles_stub)
        global monitor_service
        monitor_service = importlib.import_module("monitor_service")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_friday_reset_window(self):
        start, end = monitor_service.reset_window_for_day(date(2026, 5, 29), 4)

        self.assertEqual(start, date(2026, 5, 29))
        self.assertEqual(end, date(2026, 6, 4))
        self.assertEqual(monitor_service.reset_at_iso(end, "UTC"), "2026-06-05T00:00:00+00:00")

    def test_limit_status_thresholds(self):
        limit = {
            "id": 1,
            "account": "work@example.com",
            "metric": "total_tokens",
            "cap_value": 450_000_000,
            "reset_weekday": 4,
            "reset_time": "00:00",
            "timezone": "UTC",
            "thresholds": "[0.7,0.85,0.95,1.0]",
            "enabled": 1,
        }
        report = {"totals": {"total_tokens": 400_000_000}}

        status = monitor_service.account_limit_status_from_report(limit, report, date(2026, 5, 29))

        self.assertEqual(status.account, "work@example.com")
        self.assertAlmostEqual(status.ratio, 400_000_000 / 450_000_000)
        self.assertEqual(status.crossed_thresholds, [0.7, 0.85])
        self.assertEqual(status.next_threshold, 0.95)
        self.assertFalse(status.exceeded)
        self.assertEqual(status.elapsed_days, 1)
        self.assertEqual(status.remaining_days, 7)
        self.assertEqual(status.burn_severity, "critical")
        self.assertEqual([item.id for item in status.burn_advisories], ["projected-exhaustion", "thin-runway"])

    def test_reset_time_window_before_reset_hour(self):
        start, end = monitor_service.reset_window_for_datetime(
            datetime(2026, 5, 29, 5, 59, tzinfo=ZoneInfo("UTC")),
            4,
            "06:00",
        )

        self.assertEqual(start.isoformat(), "2026-05-22T06:00:00+00:00")
        self.assertEqual(end.isoformat(), "2026-05-29T06:00:00+00:00")

    def test_reset_time_window_at_reset_hour(self):
        start, end = monitor_service.reset_window_for_datetime(
            datetime(2026, 5, 29, 6, 0, tzinfo=ZoneInfo("UTC")),
            4,
            "06:00",
        )

        self.assertEqual(start.isoformat(), "2026-05-29T06:00:00+00:00")
        self.assertEqual(end.isoformat(), "2026-06-05T06:00:00+00:00")

    def test_reset_time_window_for_friday_1307(self):
        start, end = monitor_service.reset_window_for_datetime(
            datetime(2026, 5, 29, 13, 7, tzinfo=ZoneInfo("UTC")),
            4,
            "00:00",
        )

        self.assertEqual(start.isoformat(), "2026-05-29T00:00:00+00:00")
        self.assertEqual(end.isoformat(), "2026-06-05T00:00:00+00:00")

    def test_credit_limit_status_thresholds(self):
        limit = {
            "id": 1,
            "account": "work@example.com",
            "metric": "total_credits",
            "cap_value": 5_000,
            "reset_weekday": 4,
            "reset_time": "00:00",
            "timezone": "UTC",
            "thresholds": "[0.7,0.85,0.95,1.0]",
            "enabled": 1,
        }
        report = {"totals": {"total_tokens": 400_000_000, "total_credits": 4_400}}

        status = monitor_service.account_limit_status_from_report(limit, report, date(2026, 5, 29))

        self.assertEqual(status.metric, "total_credits")
        self.assertAlmostEqual(status.ratio, 4_400 / 5_000)
        self.assertEqual(status.crossed_thresholds, [0.7, 0.85])
        self.assertEqual(status.next_threshold, 0.95)
        self.assertAlmostEqual(status.safe_daily_spend, 600 / 7)

    def test_credit_limit_status_marks_exhausted_window(self):
        limit = {
            "id": 1,
            "account": "work@example.com",
            "metric": "total_credits",
            "cap_value": 300,
            "reset_weekday": 4,
            "reset_time": "09:00",
            "timezone": "UTC",
            "thresholds": "[0.7,0.85,0.95,1.0]",
            "enabled": 1,
        }
        report = {"totals": {"total_credits": 320}}

        status = monitor_service.account_limit_status_from_report(limit, report, date(2026, 6, 3))

        self.assertTrue(status.exceeded)
        self.assertEqual(status.projected_exhaustion_date, "2026-06-03")
        self.assertEqual(status.projected_exhaustion_label, "Already exhausted")
        self.assertEqual(status.burn_severity, "critical")
        self.assertEqual([item.id for item in status.burn_advisories], ["window-exhausted"])

    def test_credit_limit_status_keeps_reset_day_open_before_non_midnight_reset(self):
        limit = {
            "id": 1,
            "account": "work@example.com",
            "metric": "total_credits",
            "cap_value": 500,
            "reset_weekday": 4,
            "reset_time": "09:00",
            "timezone": "UTC",
            "thresholds": "[0.7,0.85,0.95,1.0]",
            "enabled": 1,
        }
        report = {"totals": {"total_credits": 100}}

        status = monitor_service.account_limit_status_from_report(
            limit,
            report,
            datetime(2026, 5, 29, 8, 0, tzinfo=ZoneInfo("UTC")),
        )

        self.assertEqual(status.window_start_at, "2026-05-22T09:00:00+00:00")
        self.assertEqual(status.window_end_at, "2026-05-29T09:00:00+00:00")
        self.assertEqual(status.window_end.isoformat(), "2026-05-29")
        self.assertEqual(status.remaining_days, 1)
        self.assertAlmostEqual(status.safe_daily_spend, 400)

    def test_memory_cache_uses_namespace_prefix(self):
        cache = monitor_service.JsonCache("redis://127.0.0.1:1/0", key_prefix="test-prefix")
        old_debug_timing = monitor_service.DEBUG_TIMING_ENABLED
        monitor_service.DEBUG_TIMING_ENABLED = False

        try:
            asyncio.run(cache.set("sample", {"ok": True}, 60))

            self.assertIn("test-prefix:sample", cache.memory)
            self.assertEqual(asyncio.run(cache.get("sample")), {"ok": True})
        finally:
            monitor_service.DEBUG_TIMING_ENABLED = old_debug_timing

    def test_memory_cache_disabled_for_multi_worker_default(self):
        cache = monitor_service.JsonCache(
            "redis://127.0.0.1:1/0",
            key_prefix="test-prefix",
            memory_fallback_mode="single-worker",
            worker_count=2,
        )

        asyncio.run(cache.set("sample", {"ok": True}, 60))

        self.assertEqual(cache.memory, {})
        self.assertIsNone(asyncio.run(cache.get("sample")))
        status = asyncio.run(cache.status())
        self.assertEqual(status["backend"], "disabled")
        self.assertFalse(status["ok"])

    def test_aggregate_rows_does_not_mutate_records(self):
        record = monitor_service.codex_usage.UsageRecord(
            timestamp=monitor_service.codex_usage.parse_timestamp("2026-05-27T10:00:00Z"),
            day="2026-05-27",
            model="gpt-5.5",
            effort="high",
            session_id="a",
            path="a.jsonl",
            usage=monitor_service.codex_usage.TokenUsage(input_tokens=1000, total_tokens=1000),
        )
        prices = {"models": {"gpt-5.5": {"input": 1.0, "cached_input": 0.1, "output": 2.0}}}

        rows, _ = monitor_service.aggregate_rows_from_records(
            [record],
            prices,
            account_resolver=lambda _: "work@example.com",
        )

        self.assertEqual(record.account, "unknown")
        self.assertEqual(rows[0]["account"], "work@example.com")

    def test_validate_outbound_url_rejects_non_http_url(self):
        with self.assertRaises(ValueError):
            monitor_service.validate_outbound_url("file:///tmp/hook", "webhook_url")


if __name__ == "__main__":
    unittest.main()
