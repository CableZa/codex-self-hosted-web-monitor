import asyncio
import os
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import httpx
from fastapi.testclient import TestClient

from codex_monitor.config import AppConfig


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.payload = payload or {}

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("failed", request=httpx.Request("GET", "http://example.test"), response=None)


class FakeHttpClient:
    def __init__(self, get_response=None, post_response=None, get_error=None, post_error=None):
        self.get_response = get_response or FakeResponse()
        self.post_response = post_response or FakeResponse()
        self.get_error = get_error
        self.post_error = post_error

    async def get(self, *_args, **_kwargs):
        if self.get_error:
            raise self.get_error
        return self.get_response

    async def post(self, *_args, **_kwargs):
        if self.post_error:
            raise self.post_error
        return self.post_response


class FakeAsyncRedis:
    def __init__(self, error_type=Exception):
        self.values = {}
        self.info_payload = {"aof_enabled": 1, "rdb_changes_since_last_save": 0}
        self.error_type = error_type
        self.fail_scan = False
        self.closed = False

    async def ping(self):
        return True

    async def get(self, key):
        return self.values.get(key)

    async def setex(self, key, _ttl, value):
        self.values[key] = value
        return True

    async def delete(self, key):
        self.values.pop(key, None)
        return 1

    async def info(self, _section):
        return dict(self.info_payload)

    async def aclose(self):
        self.closed = True

    async def scan_iter(self, match=None):
        if self.fail_scan:
            raise self.error_type("scan failed")
        prefix = (match or "").removesuffix("*")
        for key in list(self.values):
            if not prefix or key.startswith(prefix):
                yield key


class MonitorApiTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.environ["MONITOR_DB"] = os.path.join(self.tmp.name, "monitor.sqlite3")
        os.environ["VALKEY_URL"] = "redis://127.0.0.1:1/0"
        os.environ["SCANNER_ENABLED"] = "false"
        os.environ.pop("FX_LIVE_ENABLED", None)
        os.environ.pop("CUSTOM_CA_BUNDLE", None)
        os.environ.pop("CACHE_MEMORY_FALLBACK_MODE", None)
        os.environ.pop("MONITOR_API_WORKERS", None)
        os.environ.pop("AUTO_ACCOUNT_LIMIT_EMAIL_SUFFIXES", None)
        os.environ.pop("AUTO_ACCOUNT_LIMIT_CAP_CREDITS", None)
        os.environ.pop("AUTO_ACCOUNT_LIMIT_RESET_WEEKDAY", None)
        os.environ.pop("AUTO_ACCOUNT_LIMIT_RESET_TIME", None)
        os.environ.pop("AUTO_ACCOUNT_LIMIT_TIMEZONE", None)
        os.environ.pop("AUTO_ACCOUNT_LIMIT_THRESHOLDS", None)

        import monitor_service
        import codex_monitor.api as monitor_api
        import codex_monitor.api_usage as monitor_usage

        self.monitor_service = monitor_service
        self.monitor_api = monitor_api
        self.monitor_usage = monitor_usage
        self.app = monitor_service.create_app(AppConfig.from_env())
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        http_client = getattr(self.monitor_api, "shared_http_client", None)
        if hasattr(http_client, "aclose"):
            asyncio.run(http_client.aclose())
        self.monitor_api.store.conn.close()

    def sample_usage_report(self, start=None, end=None, accounts=None):
        start = start or date(2026, 6, 1)
        end = end or date(2026, 6, 1)
        account = sorted(accounts)[0] if accounts else "work@example.com"
        return self.monitor_service.report_from_aggregate_rows(
            [
                {
                    "day": start.isoformat(),
                    "account": account,
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
            ],
            {"models": {}, "updated": "test"},
            start,
            end,
            [],
            [],
        )

    def sample_session_records(self):
        return [
            self.monitor_usage.codex_usage.UsageRecord(
                timestamp=self.monitor_usage.parse_snapshot_time("2026-06-01T10:00:00Z"),
                day="2026-06-01",
                model="gpt-5.5",
                effort="high",
                session_id="session-a",
                path="rollout-a.jsonl",
                usage=self.monitor_usage.codex_usage.TokenUsage(
                    input_tokens=1000,
                    cached_input_tokens=100,
                    output_tokens=200,
                    reasoning_output_tokens=0,
                    total_tokens=1200,
                ),
            ),
            self.monitor_usage.codex_usage.UsageRecord(
                timestamp=self.monitor_usage.parse_snapshot_time("2026-06-01T10:05:00Z"),
                day="2026-06-01",
                model="gpt-5.4-mini",
                effort="high",
                session_id="session-a",
                path="rollout-a.jsonl",
                usage=self.monitor_usage.codex_usage.TokenUsage(
                    input_tokens=2000,
                    cached_input_tokens=300,
                    output_tokens=400,
                    reasoning_output_tokens=0,
                    total_tokens=2400,
                ),
            ),
            self.monitor_usage.codex_usage.UsageRecord(
                timestamp=self.monitor_usage.parse_snapshot_time("2026-06-01T11:00:00Z"),
                day="2026-06-01",
                model="gpt-5.5",
                effort="low",
                session_id="session-b",
                path="rollout-b.jsonl",
                usage=self.monitor_usage.codex_usage.TokenUsage(
                    input_tokens=500,
                    cached_input_tokens=0,
                    output_tokens=100,
                    reasoning_output_tokens=0,
                    total_tokens=600,
                ),
            ),
        ]

    def sample_session_history_report(self, start=None, end=None, account_filter=None):
        start = start or date(2026, 6, 1)
        end = end or date(2026, 6, 1)
        records = self.sample_session_records()

        def resolver(_record):
            return "work@example.com"

        return self.monitor_usage.session_history_report_from_records(
            records,
            {"models": {"gpt-5.5": {"input": 5.0, "cached_input": 0.5, "output": 30.0}, "gpt-5.4-mini": {"input": 0.75, "cached_input": 0.075, "output": 4.5}}},
            {
                "session-a": self.monitor_usage.codex_usage.SessionMetadata("session-a", "Build the dashboard", "Check the review", "/repo/dashboard", "dashboard"),
                "session-b": self.monitor_usage.codex_usage.SessionMetadata("session-b", "Fix the parser", "Fix the parser", "/repo/parser", "parser"),
            },
            files_scanned=2,
            roots=[Path("sessions")],
            start_day=start,
            end_day=end,
            warnings=[],
            account_resolver=resolver,
            account_filter=account_filter,
            snapshots=[
                {"observed_at": "2026-06-01T09:00:00Z", "email": "old@example.com", "source": "manual"},
                {"observed_at": "2026-06-01T10:00:00Z", "email": "work@example.com", "source": "codex_auth"},
            ],
        )

    def sample_session_detail_report(self, session_id="session-a", account_filter=None):
        records = self.sample_session_records()

        def resolver(_record):
            return "work@example.com"

        return self.monitor_usage.session_detail_report_from_records(
            records,
            {"models": {"gpt-5.5": {"input": 5.0, "cached_input": 0.5, "output": 30.0}, "gpt-5.4-mini": {"input": 0.75, "cached_input": 0.075, "output": 4.5}}},
            {
                "session-a": self.monitor_usage.codex_usage.SessionMetadata("session-a", "Build the dashboard", "Check the review", "/repo/dashboard", "dashboard"),
                "session-b": self.monitor_usage.codex_usage.SessionMetadata("session-b", "Fix the parser", "Fix the parser", "/repo/parser", "parser"),
            },
            files_scanned=2,
            roots=[Path("sessions")],
            start_day=date(2026, 6, 1),
            end_day=date(2026, 6, 1),
            warnings=[],
            session_id=session_id,
            account_resolver=resolver,
            account_filter=account_filter,
        )
