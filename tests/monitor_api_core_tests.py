from .monitor_api_base import *


class MonitorApiCoreTests(MonitorApiTestBase):
    def test_config_reads_env_defaults(self):
        config = AppConfig.from_env()

        self.assertEqual(str(config.db_path), os.environ["MONITOR_DB"])
        self.assertFalse(config.scanner_enabled)
        self.assertFalse(config.fx_live_enabled)
        self.assertIsNone(config.custom_ca_bundle)
        self.assertEqual(config.timezone, "UTC")
        self.assertEqual(config.cache_memory_fallback_mode, "single-worker")
        self.assertEqual(config.monitor_api_workers, 1)

    def test_config_reads_cache_fallback_env(self):
        os.environ["CACHE_MEMORY_FALLBACK_MODE"] = "disabled"
        os.environ["MONITOR_API_WORKERS"] = "2"

        config = AppConfig.from_env()

        self.assertEqual(config.cache_memory_fallback_mode, "disabled")
        self.assertEqual(config.monitor_api_workers, 2)

    def test_config_reads_optional_fx_and_ca_env(self):
        os.environ["FX_LIVE_ENABLED"] = "true"
        os.environ["CUSTOM_CA_BUNDLE"] = "/certs/macos-ca-bundle.pem"

        config = AppConfig.from_env()

        self.assertTrue(config.fx_live_enabled)
        self.assertEqual(str(config.custom_ca_bundle), "/certs/macos-ca-bundle.pem")

    def test_healthz_shape(self):
        response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"ok", "version", "generated_at", "error"})
        self.assertEqual(response.json()["version"], self.monitor_api.APP_VERSION)

    def test_async_valkey_cache_set_get_and_status(self):
        fake = FakeAsyncRedis(self.monitor_api.cache_module.redis.RedisError)
        cache = self.monitor_api.JsonCache("redis://example.test:6379/0", key_prefix="unit")

        with patch.object(self.monitor_api.cache_module.aioredis.Redis, "from_url", return_value=fake):
            asyncio.run(cache.set("sample", {"ok": True}, 60))
            cached = asyncio.run(cache.get("sample"))
            status = asyncio.run(cache.status())

        self.assertEqual(cached, {"ok": True})
        self.assertEqual(fake.values["unit:sample"], '{"ok": true}')
        self.assertEqual(status["backend"], "valkey")
        self.assertTrue(status["ok"])

    def test_cache_corrupt_json_is_miss_and_deleted(self):
        fake = FakeAsyncRedis(self.monitor_api.cache_module.redis.RedisError)
        fake.values["unit:sample"] = "{bad json"
        cache = self.monitor_api.JsonCache("redis://example.test:6379/0", key_prefix="unit")

        with patch.object(self.monitor_api.cache_module.aioredis.Redis, "from_url", return_value=fake):
            cached = asyncio.run(cache.get("sample"))

        self.assertIsNone(cached)
        self.assertNotIn("unit:sample", fake.values)

    def test_failed_clear_does_not_repair_remote_dirty_on_set(self):
        fake = FakeAsyncRedis(self.monitor_api.cache_module.redis.RedisError)
        fake.values["unit:old"] = '{"stale": true}'
        fake.fail_scan = True
        cache = self.monitor_api.JsonCache("redis://example.test:6379/0", key_prefix="unit")

        with patch.object(self.monitor_api.cache_module.aioredis.Redis, "from_url", return_value=fake):
            asyncio.run(cache.clear())
            self.assertTrue(cache.remote_dirty)
            fake.fail_scan = False
            asyncio.run(cache.set("fresh", {"ok": True}, 60))
            self.assertTrue(cache.remote_dirty)
            self.assertIn("unit:old", fake.values)
            self.assertEqual(fake.values["unit:fresh"], '{"ok": true}')
            asyncio.run(cache.clear())

        self.assertFalse(cache.remote_dirty)
        self.assertNotIn("unit:old", fake.values)
        self.assertNotIn("unit:fresh", fake.values)

    def test_multi_worker_cache_disables_memory_fallback(self):
        cache = self.monitor_api.JsonCache(
            "redis://127.0.0.1:1/0",
            key_prefix="unit",
            memory_fallback_mode="single-worker",
            worker_count=2,
        )

        asyncio.run(cache.set("sample", {"ok": True}, 60))
        cached = asyncio.run(cache.get("sample"))
        status = asyncio.run(cache.status())

        self.assertIsNone(cached)
        self.assertEqual(cache.memory, {})
        self.assertEqual(status["backend"], "disabled")
        self.assertFalse(status["ok"])

    def test_changelog_route_parses_recent_release_groups(self):
        changelog_path = Path(self.tmp.name) / "CHANGELOG.md"
        changelog_path.write_text(
            """# Changelog

## Unreleased

No unreleased changes.

## v0.7.0 - 2026-06-05

### Added

- Added a backend changelog endpoint.
- Added a dashboard changelog entry point.

### Fixed

- Fixed project metrics overflow.

## v0.6.0 - 2026-06-04

### Changed

- Changed usage-window controls.
""",
            encoding="utf-8",
        )

        with patch.object(self.monitor_api, "CHANGELOG_PATH", changelog_path):
            response = self.client.get("/api/changelog?limit=1")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["source"], "CHANGELOG.md")
        self.assertIsNone(body["unreleased"])
        self.assertEqual(len(body["releases"]), 1)
        release = body["releases"][0]
        self.assertEqual(release["version"], "0.7.0")
        self.assertEqual(release["date"], "2026-06-05")
        self.assertEqual(release["title"], "v0.7.0 - 2026-06-05")
        self.assertEqual([group["name"] for group in release["groups"]], ["Added", "Fixed"])
        self.assertEqual(release["groups"][0]["items"][0], "Added a backend changelog endpoint.")

    def test_changelog_route_returns_unreleased_when_items_exist(self):
        changelog_path = Path(self.tmp.name) / "CHANGELOG.md"
        changelog_path.write_text(
            """# Changelog

## Unreleased

### Added

- Added unreleased work.

## v0.6.0 - 2026-06-04

### Changed

- Changed existing behavior.
""",
            encoding="utf-8",
        )

        with patch.object(self.monitor_api, "CHANGELOG_PATH", changelog_path):
            response = self.client.get("/api/changelog")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["unreleased"]["title"], "Unreleased")
        self.assertIsNone(body["unreleased"]["version"])
        self.assertIsNone(body["unreleased"]["date"])
        self.assertEqual(body["unreleased"]["groups"][0]["items"], ["Added unreleased work."])
        self.assertEqual(body["releases"][0]["version"], "0.6.0")

    def test_changelog_route_validates_limit_and_missing_file(self):
        response = self.client.get("/api/changelog?limit=0")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "limit must be between 1 and 20")

        response = self.client.get("/api/changelog?limit=21")
        self.assertEqual(response.status_code, 400)

        with patch.object(self.monitor_api, "CHANGELOG_PATH", Path(self.tmp.name) / "missing.md"):
            response = self.client.get("/api/changelog")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "CHANGELOG.md not found")

    def test_update_status_route_returns_unavailable_without_host_status(self):
        with patch.object(self.monitor_api, "UPDATE_STATUS_PATH", Path(self.tmp.name) / "missing-status.json"):
            response = self.client.get("/api/update-status")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["state"], "unavailable")
        self.assertEqual(body["current_version"], self.monitor_api.APP_VERSION)
        self.assertEqual(body["manual_update_command"], "python scripts/update-monitor.py apply")

    def test_update_status_route_reads_host_status(self):
        status_path = Path(self.tmp.name) / "update-status.json"
        status_path.write_text(
            '{"state":"update_available","current_version":"0.7.1","latest_version":"0.8.0","generated_at":"2026-06-05T10:00:00+00:00"}',
            encoding="utf-8",
        )

        with patch.object(self.monitor_api, "UPDATE_STATUS_PATH", status_path):
            response = self.client.get("/api/update-status")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["state"], "update_available")
        self.assertEqual(body["latest_version"], "0.8.0")
        self.assertEqual(body["manual_update_command"], "python scripts/update-monitor.py apply")
        self.assertFalse(body["stale"])

    def test_update_status_route_returns_update_metadata(self):
        status_path = Path(self.tmp.name) / "update-status.json"
        status_path.write_text(
            '{"state":"update_available","current_version":"0.7.1","latest_version":"0.8.0","latest_tag":"v0.8.0","install_mode":"docker","check_mode":"builtin_http","source_url":"https://example.test/tags","generated_at":"2026-06-05T10:00:00+00:00"}',
            encoding="utf-8",
        )

        with patch.object(self.monitor_api, "UPDATE_STATUS_PATH", status_path):
            response = self.client.get("/api/update-status")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["check_mode"], "builtin_http")
        self.assertEqual(body["source_url"], "https://example.test/tags")
        self.assertEqual(body["manual_update_command"], "./scripts/update-and-redeploy")

    def test_root_serves_static_index(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])

    def test_summary_contract_periods_dates_and_account_filter(self):
        calls = []

        async def fake_usage_report(start, end, account_filter=None):
            calls.append((start, end, account_filter))
            return self.sample_usage_report(start, end, account_filter)

        with patch.object(self.monitor_api, "now_local", return_value=datetime(2026, 6, 3, tzinfo=timezone.utc)):
            with patch.object(self.monitor_api, "usage_report", side_effect=fake_usage_report):
                response = self.client.get("/api/summary?period=week&accounts=beta@example.com,alpha@example.com")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["period"], {"from": "2026-06-01", "to": "2026-06-03"})
        self.assertEqual(calls[0], (date(2026, 6, 1), date(2026, 6, 3), {"alpha@example.com", "beta@example.com"}))
        self.assertGreaterEqual(set(body), {"totals", "by_day", "by_account", "cache"})

        response = self.client.get("/api/summary?period=missing")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "unknown period: missing")

        response = self.client.get("/api/summary?date_from=2026-06-02&date_to=2026-06-01")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "date_from must be before date_to")

    def test_summary_exact_window_uses_datetime_params(self):
        calls = []

        async def fake_usage_report_for_window(start_at, end_at, account_filter=None):
            calls.append((start_at, end_at, account_filter))
            report = self.sample_usage_report(start_at.date(), end_at.date(), account_filter)
            report["period"] = {"from": start_at.isoformat(), "to": end_at.isoformat()}
            return report

        with patch.object(self.monitor_api, "usage_report_for_window", side_effect=fake_usage_report_for_window):
            response = self.client.get(
                "/api/summary?start_at=2026-06-01T08:30&end_at=2026-06-01T12:45&accounts=work@example.com"
            )

        self.assertEqual(response.status_code, 200)
        tz = ZoneInfo("UTC")
        self.assertEqual(calls[0], (
            datetime(2026, 6, 1, 8, 30, tzinfo=tz),
            datetime(2026, 6, 1, 12, 45, tzinfo=tz),
            {"work@example.com"},
        ))
        self.assertEqual(response.json()["period"]["from"], "2026-06-01T08:30:00+00:00")

        response = self.client.get("/api/summary?start_at=2026-06-01T12:00&end_at=2026-06-01T12:00")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "start_at must be before end_at")

    def test_days_contract_with_cache_metadata_and_account_filter(self):
        calls = []

        async def fake_days_report(start, end, account_filter=None):
            calls.append((start, end, account_filter))
            rows = [self.monitor_api.empty_day_row(start), self.monitor_api.empty_day_row(end)]
            return self.monitor_api.days_response(
                start,
                end,
                rows,
                {"rate": 18.5, "source": "fallback", "day": "2026-06-03"},
                False,
                90,
            )

        with patch.object(self.monitor_api, "days_report", side_effect=fake_days_report):
            response = self.client.get(
                "/api/days?date_from=2026-06-01&date_to=2026-06-02&accounts=work@example.com"
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["period"], {"from": "2026-06-01", "to": "2026-06-02"})
        self.assertEqual(len(body["days"]), 2)
        self.assertEqual(body["exchange_rate"]["source"], "fallback")
        self.assertEqual(calls[0], (date(2026, 6, 1), date(2026, 6, 2), {"work@example.com"}))

    def test_days_exact_window_uses_datetime_params(self):
        calls = []

        async def fake_days_report_for_window(start_at, end_at, account_filter=None):
            calls.append((start_at, end_at, account_filter))
            return self.monitor_api.days_response(
                start_at.date(),
                end_at.date(),
                [self.monitor_api.empty_day_row(start_at.date())],
                {"rate": 18.5, "source": "fallback", "day": "2026-06-03"},
                False,
                90,
                start_at.isoformat(),
                end_at.isoformat(),
            )

        with patch.object(self.monitor_api, "days_report_for_window", side_effect=fake_days_report_for_window):
            response = self.client.get("/api/days?start_at=2026-06-01T08:30&end_at=2026-06-02T09:00")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["period"], {"from": "2026-06-01T08:30:00+00:00", "to": "2026-06-02T09:00:00+00:00"})
        self.assertEqual(calls[0][0], datetime(2026, 6, 1, 8, 30, tzinfo=ZoneInfo("UTC")))
        self.assertEqual(calls[0][1], datetime(2026, 6, 2, 9, 0, tzinfo=ZoneInfo("UTC")))

    def test_days_route_ignores_stale_day_cache_versions(self):
        day = date(2026, 6, 3)
        stale_row = {
            "day": day.isoformat(),
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
            "sessions": 1,
            "files": 1,
        }
        stale_report = {
            "period": {"from": day.isoformat(), "to": day.isoformat()},
            "days": [stale_row],
            "exchange_rate": {"rate": 18.5, "source": "fallback", "day": day.isoformat()},
            "cache": {"hit": True, "ttl_seconds": 90, "served_at": "2026-06-03T00:00:00+00:00"},
        }
        asyncio.run(self.monitor_api.cache.clear())
        asyncio.run(self.monitor_api.cache.set("days:v5:2026-06-03:2026-06-03:all", stale_report, 90))
        asyncio.run(self.monitor_api.cache.set("day:v5:2026-06-03:all", stale_row, 90))

        with patch.object(self.monitor_api.usage_module, "usage_report", return_value=self.sample_usage_report(day, day)):
            response = self.client.get("/api/days?date_from=2026-06-03&date_to=2026-06-03")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["days"][0]["uncached_input_tokens"], 900)
        self.assertEqual(body["days"][0]["input_tokens"], 1000)

    def test_snapshot_route_ignores_old_generation_latest_snapshot(self):
        old_snapshot = {
            "generated_at": "2026-06-03T08:00:00+00:00",
            "timezone": "UTC",
            "reports": {},
            "budgets": [],
            "account_limits": [],
            "alerts_emitted": [],
        }
        generation = asyncio.run(self.monitor_api.usage_module.usage_cache_generation())
        old_key = self.monitor_api.versioned_cache_key(generation, self.monitor_api.latest_snapshot_cache_key())
        asyncio.run(self.monitor_api.cache.set(old_key, old_snapshot, 180))
        asyncio.run(self.monitor_api.invalidate_derived_cache("test"))
        self.monitor_api.latest_snapshot = {}

        with patch.object(self.monitor_api, "build_snapshot", side_effect=AssertionError("API snapshot must not rebuild")):
            response = self.client.get("/api/snapshot")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "warming")
        self.assertFalse(body["cache"]["response"]["hit"])
        self.assertEqual(body["cache"]["generation"], generation + 1)
