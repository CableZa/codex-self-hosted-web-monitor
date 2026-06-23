from .monitor_api_base import *


class MonitorApiAccountsTests(MonitorApiTestBase):
    def test_settings_round_trip_and_url_validation(self):
        response = self.client.get("/api/settings")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("cache_generation", response.json())
        self.assertNotIn("account_limit_generation", response.json())
        self.assertNotIn("usage_cache_generation", response.json())
        self.assertNotIn("account_credit_limit_migration_done", response.json())
        self.assertNotIn("daily_budget_credits", response.json())

        response = self.client.put("/api/settings", json={"webhook_url": "file:///tmp/hook"})
        self.assertEqual(response.status_code, 400)

        response = self.client.put("/api/settings", json={"daily_budget_credits": "10.5"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            "daily_budget_credits is no longer supported; use per-account weekly credit limits instead",
        )

        response = self.client.put("/api/settings", json={"daily_budget_credits": "10"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            "daily_budget_credits is no longer supported; use per-account weekly credit limits instead",
        )

        response = self.client.put("/api/settings", json={"dashboard_mode": "compact"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["dashboard_mode"], "compact")

        response = self.client.put("/api/settings", json={"ui_theme": "classic"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ui_theme"], "classic")

        response = self.client.put("/api/settings", json={"ui_theme": "solarized"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "ui_theme must be catppuccin or classic")

        response = self.client.put("/api/settings", json={"session_high_input_tokens": "0"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "session_high_input_tokens must be a positive whole number")

        response = self.client.put("/api/settings", json={"session_low_cache_max_reuse_ratio": "1.5"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "session_low_cache_max_reuse_ratio must be between 0 and 1")

        response = self.client.put("/api/settings", json={
            "session_high_input_tokens": "2000000",
            "session_low_cache_max_reuse_ratio": "0.25",
            "session_long_context_pricing_signal_enabled": "false",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["session_high_input_tokens"], "2000000")
        self.assertEqual(response.json()["session_low_cache_max_reuse_ratio"], "0.25")
        self.assertEqual(response.json()["session_long_context_pricing_signal_enabled"], "false")

    def test_settings_webhook_visibility_is_derived_from_current_runtime_state(self):
        self.monitor_api.store.conn.execute(
            "insert into settings(key, value) values('webhook_ui_enabled', 'true') "
            "on conflict(key) do update set value='true'"
        )
        self.monitor_api.store.conn.execute(
            "insert into settings(key, value) values('webhook_url', '') "
            "on conflict(key) do update set value=''"
        )
        self.monitor_api.store.conn.commit()

        response = self.client.get("/api/settings")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["webhook_ui_enabled"], "false")

        asyncio.run(self.monitor_api.store.update_settings({"webhook_url": "https://example.test/hook"}))
        response = self.client.get("/api/settings")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["webhook_ui_enabled"], "true")

    def test_settings_update_schema_hides_removed_credit_budget_fields(self):
        properties = self.monitor_api.SettingsUpdate.model_json_schema().get("properties", {})
        self.assertNotIn("daily_budget_credits", properties)
        self.assertNotIn("weekly_budget_credits", properties)
        self.assertNotIn("monthly_budget_credits", properties)

        response = self.client.put("/api/settings", json={"account_credit_limit_migration_done": "true"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "account_credit_limit_migration_done is read-only")

    def test_unknown_account_mapping_settings_validation(self):
        snapshot = {
            "observed_at": "2026-06-03T08:00:00+00:00",
            "email": "work@example.com",
            "source": "manual",
        }
        asyncio.run(self.monitor_api.store.record_auth_snapshot(snapshot))

        response = self.client.put("/api/settings", json={"unknown_account_mapping": "missing@example.com"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "unknown_account_mapping must be blank or one of the known accounts")

        with patch.object(self.monitor_api, "build_snapshot", side_effect=AssertionError("API settings must not rebuild snapshots")):
            response = self.client.put("/api/settings", json={"unknown_account_mapping": "work@example.com"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["unknown_account_mapping"], "work@example.com")

        with patch.object(self.monitor_api, "build_snapshot", side_effect=AssertionError("API settings must not rebuild snapshots")):
            response = self.client.put("/api/settings", json={"unknown_account_mapping": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["unknown_account_mapping"], "")

    def test_accounts_and_manual_auth_snapshot_contract(self):
        snapshot = {
            "observed_at": "2026-06-03T08:00:00+00:00",
            "account_id": "acct-1",
            "email": "Work@Example.com",
            "name": "Work",
            "source": "manual",
        }

        response = self.client.post("/api/auth-snapshots", json=snapshot)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["inserted"])
        self.assertEqual(response.json()["snapshot"]["email"], "work@example.com")

        response = self.client.post("/api/auth-snapshots", json=snapshot)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["inserted"])

        response = self.client.post("/api/auth-snapshots", json={"observed_at": "bad", "email": "x@example.com"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "observed_at must be an ISO timestamp")

        with patch.object(self.monitor_api, "record_current_auth_snapshot", side_effect=AssertionError("GET /api/accounts must stay read-only")):
            with patch.object(self.monitor_api, "ensure_default_account_limits_from_snapshots", side_effect=AssertionError("GET /api/accounts must not seed defaults")):
                with patch.object(self.monitor_api, "usage_report", return_value={"by_account": [], "accounts": ["work@example.com"]}):
                    response = self.client.get("/api/accounts")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["accounts"][0]["account"], "work@example.com")
        self.assertEqual(response.json()["snapshots"][0]["source"], "manual")
        self.assertEqual(response.json()["auto_account_limit_defaults"]["email_suffixes"], [])
        self.assertEqual(response.json()["auto_account_limit_defaults"]["cap_credits"], 400)

    def test_accounts_route_includes_unknown_usage_account(self):
        with patch.object(self.monitor_api, "record_current_auth_snapshot", side_effect=AssertionError("GET /api/accounts must stay read-only")):
            with patch.object(self.monitor_api.store, "auth_snapshots", return_value=[]):
                with patch.object(
                    self.monitor_api,
                    "usage_report",
                    return_value={"by_account": [{"account": "unknown"}], "accounts": ["unknown"]},
                ):
                    response = self.client.get("/api/accounts")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["accounts"][0]["account"], "unknown")
        self.assertEqual(response.json()["accounts"][0]["source"], "usage")
        self.assertEqual(response.json()["snapshots"], [])

    def test_accounts_route_merges_usage_accounts_with_snapshots(self):
        snapshots = [
            {
                "observed_at": "2026-06-03T08:00:00+00:00",
                "email": "work@example.com",
                "source": "manual",
            }
        ]
        with patch.object(self.monitor_api, "record_current_auth_snapshot", side_effect=AssertionError("GET /api/accounts must stay read-only")):
            with patch.object(self.monitor_api.store, "auth_snapshots", return_value=snapshots):
                with patch.object(
                    self.monitor_api,
                    "usage_report",
                    return_value={"by_account": [{"account": "unknown"}, {"account": "work@example.com"}], "accounts": ["unknown", "work@example.com"]},
                ):
                    response = self.client.get("/api/accounts")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([option["account"] for option in response.json()["accounts"]], ["unknown", "work@example.com"])
        self.assertEqual(response.json()["accounts"][0]["source"], "usage")
        self.assertEqual(response.json()["accounts"][1]["source"], "manual")

    def test_accounts_route_returns_attribution_detection(self):
        snapshot = {
            "observed_at": "2026-06-01T10:00:00+00:00",
            "email": "work@example.com",
            "source": "manual",
        }
        asyncio.run(self.monitor_api.store.record_auth_snapshot(snapshot))
        cached_days = {
            day.isoformat()
            for day in self.monitor_api.iter_days(date(2026, 2, 1), date(2026, 6, 1))
        }
        unknown_rows = [
            {
                "day": "2026-02-01",
                "account": "unknown",
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
                "input_credits": 10,
                "cached_input_credits": 1,
                "output_credits": 7,
                "reasoning_output_credits": 0,
                "total_credits": 18,
                "long_context_applied": False,
                "events": 3,
                "sessions": ["session-1"],
                "files": ["rollout-2026-02-01.jsonl"],
            }
        ]

        with patch.object(
            self.monitor_api,
            "visible_usage_history",
            return_value={
                "earliest_usage_day": "2026-02-01",
                "latest_usage_day": "2026-06-02",
                "visible_rollout_files": 48,
                "sessions_root_files": 30,
                "archived_sessions_root_files": 18,
                "docker_mount_like": True,
            },
        ):
            with patch.object(self.monitor_api.store, "settings", AsyncMock(return_value={"unknown_account_mapping": ""})):
                with patch.object(self.monitor_api.store, "usage_aggregate_days", AsyncMock(return_value=cached_days)):
                    with patch.object(self.monitor_api.store, "usage_aggregate_rows", AsyncMock(return_value=unknown_rows)):
                        with patch.object(
                            self.monitor_api,
                            "usage_report",
                            return_value={"by_account": [{"account": "unknown"}, {"account": "work@example.com"}], "accounts": ["unknown", "work@example.com"]},
                        ):
                            response = self.client.get("/api/accounts")

        self.assertEqual(response.status_code, 200)
        attribution = response.json()["attribution"]
        self.assertEqual(attribution["history"]["earliest_usage_day"], "2026-02-01")
        self.assertEqual(attribution["history"]["first_auth_snapshot_at"], "2026-06-01T10:00:00+00:00")
        self.assertEqual(attribution["history"]["unknown_usage_totals"]["total_credits"], 18)
        self.assertEqual(
            [issue["type"] for issue in attribution["issues"]],
            ["unknown_usage_before_first_snapshot", "late_first_snapshot"],
        )

    def test_accounts_route_returns_sparse_history_detection(self):
        with patch.object(self.monitor_api.store, "auth_snapshots", AsyncMock(return_value=[])):
            with patch.object(
                self.monitor_api,
                "visible_usage_history",
                return_value={
                    "earliest_usage_day": "2026-01-01",
                    "latest_usage_day": "2026-05-15",
                    "visible_rollout_files": 6,
                    "sessions_root_files": 6,
                    "archived_sessions_root_files": 0,
                    "docker_mount_like": True,
                },
            ):
                with patch.object(self.monitor_api.store, "settings", AsyncMock(return_value={"unknown_account_mapping": ""})):
                    with patch.object(
                        self.monitor_api,
                        "usage_report",
                        return_value={"by_account": [{"account": "unknown"}], "accounts": ["unknown"]},
                    ):
                        response = self.client.get("/api/accounts")

        self.assertEqual(response.status_code, 200)
        issues = response.json()["attribution"]["issues"]
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["type"], "sparse_visible_history")
        self.assertEqual(issues[0]["severity"], "warning")

    def test_cached_unknown_usage_totals_skips_incomplete_aggregate_coverage(self):
        with patch.object(self.monitor_api.store, "usage_aggregate_days", AsyncMock(return_value={"2026-02-01"})):
            totals = asyncio.run(
                self.monitor_api.cached_unknown_usage_totals(
                    "2026-02-01",
                    "2026-02-03T10:00:00+00:00",
                    "",
                )
            )

        self.assertIsNone(totals)

    def test_summary_unknown_account_filter_matches_unattributed_usage(self):
        prices = {"models": {"gpt-5.5": {"input": 5.0, "cached_input": 0.5, "output": 30.0}}, "updated": "test"}
        records = [
            self.monitor_api.codex_usage.UsageRecord(
                timestamp=self.monitor_api.parse_snapshot_time("2026-06-01T09:00:00Z"),
                day="2026-06-01",
                model="gpt-5.5",
                effort="high",
                session_id="unknown-session",
                path="unknown.jsonl",
                usage=self.monitor_api.codex_usage.TokenUsage(input_tokens=100, output_tokens=10, total_tokens=110),
            ),
            self.monitor_api.codex_usage.UsageRecord(
                timestamp=self.monitor_api.parse_snapshot_time("2026-06-01T11:00:00Z"),
                day="2026-06-01",
                model="gpt-5.5",
                effort="high",
                session_id="known-session",
                path="known.jsonl",
                usage=self.monitor_api.codex_usage.TokenUsage(input_tokens=200, output_tokens=20, total_tokens=220),
            ),
        ]
        snapshots = [{"observed_at": "2026-06-01T10:00:00Z", "email": "work@example.com", "source": "manual"}]
        resolver = self.monitor_api.account_resolver_from_snapshots(snapshots)

        rows, _warnings = self.monitor_api.aggregate_rows_from_records(records, prices, resolver)
        report = self.monitor_api.report_from_aggregate_rows(rows, prices, date(2026, 6, 1), date(2026, 6, 1), [], [])
        self.assertEqual([row["account"] for row in report["by_account"]], ["work@example.com", "unknown"])
        self.assertEqual(self.monitor_usage.report_account_labels(report, snapshots), ["unknown", "work@example.com"])

        filtered_rows, _warnings = self.monitor_api.aggregate_rows_from_records(records, prices, resolver, {"unknown"})
        filtered_report = self.monitor_api.report_from_aggregate_rows(filtered_rows, prices, date(2026, 6, 1), date(2026, 6, 1), [], [])
        self.assertEqual(filtered_report["by_account"][0]["account"], "unknown")
        self.assertEqual(filtered_report["totals"]["input_tokens"], 100)

        async def fake_usage_report(start, end, account_filter=None):
            self.assertEqual(account_filter, {"unknown"})
            return {
                **filtered_report,
                "exchange_rate": {"rate": 18.5, "source": "test", "day": start.isoformat()},
                "accounts": self.monitor_usage.report_account_labels(filtered_report, snapshots),
            }

        with patch.object(self.monitor_api, "usage_report", side_effect=fake_usage_report):
            response = self.client.get("/api/summary?date_from=2026-06-01&date_to=2026-06-01&accounts=unknown")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["by_account"][0]["account"], "unknown")
        self.assertEqual(response.json()["totals"]["input_tokens"], 100)

    def test_unknown_account_mapping_assigns_unattributed_usage_to_known_account(self):
        prices = {"models": {"gpt-5.5": {"input": 5.0, "cached_input": 0.5, "output": 30.0}}, "updated": "test"}
        records = [
            self.monitor_api.codex_usage.UsageRecord(
                timestamp=self.monitor_api.parse_snapshot_time("2026-06-01T09:00:00Z"),
                day="2026-06-01",
                model="gpt-5.5",
                effort="high",
                session_id="unknown-session",
                path="unknown.jsonl",
                usage=self.monitor_api.codex_usage.TokenUsage(input_tokens=100, output_tokens=10, total_tokens=110),
            ),
            self.monitor_api.codex_usage.UsageRecord(
                timestamp=self.monitor_api.parse_snapshot_time("2026-06-01T11:00:00Z"),
                day="2026-06-01",
                model="gpt-5.5",
                effort="high",
                session_id="known-session",
                path="known.jsonl",
                usage=self.monitor_api.codex_usage.TokenUsage(input_tokens=200, output_tokens=20, total_tokens=220),
            ),
        ]
        snapshots = [{"observed_at": "2026-06-01T10:00:00Z", "email": "work@example.com", "source": "manual"}]
        resolver = self.monitor_api.account_resolver_from_snapshots(snapshots, "work@example.com")

        rows, _warnings = self.monitor_api.aggregate_rows_from_records(records, prices, resolver)
        report = self.monitor_api.report_from_aggregate_rows(rows, prices, date(2026, 6, 1), date(2026, 6, 1), [], [])
        self.assertEqual([row["account"] for row in report["by_account"]], ["work@example.com"])
        self.assertEqual(report["totals"]["input_tokens"], 300)
        self.assertEqual(self.monitor_usage.report_account_labels(report, snapshots), ["work@example.com"])

        filtered_rows, _warnings = self.monitor_api.aggregate_rows_from_records(records, prices, resolver, {"unknown"})
        filtered_report = self.monitor_api.report_from_aggregate_rows(filtered_rows, prices, date(2026, 6, 1), date(2026, 6, 1), [], [])
        self.assertEqual(filtered_report["totals"]["input_tokens"], 0)

        filtered_rows, _warnings = self.monitor_api.aggregate_rows_from_records(records, prices, resolver, {"work@example.com"})
        filtered_report = self.monitor_api.report_from_aggregate_rows(filtered_rows, prices, date(2026, 6, 1), date(2026, 6, 1), [], [])
        self.assertEqual(filtered_report["totals"]["input_tokens"], 300)

    def test_summary_endpoint_uses_unknown_account_mapping_setting(self):
        snapshot = {
            "observed_at": "2026-06-01T10:00:00Z",
            "email": "work@example.com",
            "source": "manual",
        }
        records = [
            self.monitor_api.codex_usage.UsageRecord(
                timestamp=self.monitor_api.parse_snapshot_time("2026-06-01T09:00:00Z"),
                day="2026-06-01",
                model="gpt-5.5",
                effort="high",
                session_id="pre-auth",
                path="pre-auth.jsonl",
                usage=self.monitor_api.codex_usage.TokenUsage(input_tokens=100, output_tokens=10, total_tokens=110),
            ),
            self.monitor_api.codex_usage.UsageRecord(
                timestamp=self.monitor_api.parse_snapshot_time("2026-06-01T11:00:00Z"),
                day="2026-06-01",
                model="gpt-5.5",
                effort="high",
                session_id="post-auth",
                path="post-auth.jsonl",
                usage=self.monitor_api.codex_usage.TokenUsage(input_tokens=200, output_tokens=20, total_tokens=220),
            ),
        ]
        prices = {"models": {"gpt-5.5": {"input": 5.0, "cached_input": 0.5, "output": 30.0}}, "updated": "test"}

        asyncio.run(self.monitor_api.store.record_auth_snapshot(snapshot))
        with patch.object(self.monitor_api, "build_snapshot", side_effect=AssertionError("API settings must not rebuild snapshots")):
            response = self.client.put("/api/settings", json={"unknown_account_mapping": "work@example.com"})
        self.assertEqual(response.status_code, 200)

        with patch.object(self.monitor_api.usage_module.codex_usage, "load_prices", return_value=prices):
            with patch.object(self.monitor_api.usage_module, "scan_usage_files_for_period_sync", return_value=(records, {}, [], [], [])):
                response = self.client.get("/api/summary?start_at=2026-06-01T08:00:00Z&end_at=2026-06-01T12:00:00Z")
                unknown_response = self.client.get("/api/summary?start_at=2026-06-01T08:00:00Z&end_at=2026-06-01T12:00:00Z&accounts=unknown")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["account"] for row in response.json()["by_account"]], ["work@example.com"])
        self.assertEqual(response.json()["totals"]["input_tokens"], 300)
        self.assertEqual(response.json()["accounts"], ["work@example.com"])
        self.assertEqual(unknown_response.status_code, 200)
        self.assertEqual(unknown_response.json()["totals"]["input_tokens"], 0)

    def test_unknown_account_mapping_is_part_of_historic_aggregate_cache_version(self):
        prices = {"models": {}, "updated": "test", "credit_source": "test"}

        default_version = self.monitor_api.usage_aggregate_cache_version(prices)
        mapped_version = self.monitor_api.usage_aggregate_cache_version(prices, "work@example.com")

        self.assertNotEqual(default_version, mapped_version)
        self.assertEqual(default_version, "v4:test:test:unknown=unknown")
        self.assertEqual(mapped_version, "v4:test:test:unknown=work@example.com")

    def test_snapshot_route_uses_cache_shape(self):
        today = date(2026, 6, 3)
        snapshot = {
            "generated_at": "2026-06-03T08:00:00+00:00",
            "timezone": "UTC",
            "reports": {},
            "budgets": [],
            "account_limits": [],
            "alerts_emitted": [],
            "cache": {"backend": "memory"},
        }
        generation = asyncio.run(self.monitor_api.store.cache_generation())
        key = self.monitor_api.versioned_cache_key(generation, self.monitor_api.snapshot_cache_key(today))
        asyncio.run(self.monitor_api.cache.set(key, snapshot, 90))

        with patch.object(self.monitor_api, "now_local", return_value=datetime(2026, 6, 3, tzinfo=timezone.utc)):
            response = self.client.get("/api/snapshot")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["timezone"], "UTC")
        self.assertTrue(body["cache"]["response"]["hit"])
        self.assertEqual(body["cache"]["backend"]["backend"], "memory")
        self.assertEqual(body["cache"]["generation"], generation)

    def test_snapshot_route_uses_shared_latest_cache_without_building_snapshot(self):
        snapshot = {
            "generated_at": "2026-06-03T08:00:00+00:00",
            "timezone": "UTC",
            "reports": {},
            "budgets": [],
            "account_limits": [],
            "alerts_emitted": [],
        }
        generation = asyncio.run(self.monitor_api.store.cache_generation())
        key = self.monitor_api.versioned_cache_key(generation, self.monitor_api.latest_snapshot_cache_key())
        asyncio.run(self.monitor_api.cache.set(key, snapshot, 180))

        with patch.object(self.monitor_api, "now_local", return_value=datetime(2026, 6, 3, tzinfo=timezone.utc)):
            with patch.object(self.monitor_api, "build_snapshot", side_effect=AssertionError("API snapshot must not rebuild")):
                response = self.client.get("/api/snapshot")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["generated_at"], "2026-06-03T08:00:00+00:00")
        self.assertTrue(body["cache"]["response"]["hit"])

    def test_snapshot_route_cache_miss_returns_warming_without_building_snapshot(self):
        asyncio.run(self.monitor_api.cache.clear())
        self.monitor_api.latest_snapshot = {}

        with patch.object(self.monitor_api, "build_snapshot", side_effect=AssertionError("API snapshot must not rebuild")):
            response = self.client.get("/api/snapshot")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "warming")
        self.assertFalse(response.json()["cache"]["response"]["hit"])

    def test_publish_latest_snapshot_writes_shared_and_dated_cache(self):
        today = date(2026, 6, 3)
        report = self.sample_usage_report(today, today)
        snapshot = {
            "generated_at": "2026-06-03T08:00:00+00:00",
            "timezone": "UTC",
            "reports": {"today": report},
            "budgets": [],
            "account_limits": [],
            "alerts_emitted": [],
        }

        with patch.object(self.monitor_api, "now_local", return_value=datetime(2026, 6, 3, tzinfo=timezone.utc)):
            asyncio.run(self.monitor_api.publish_latest_snapshot(snapshot))

        generation = asyncio.run(self.monitor_api.store.cache_generation())
        latest = asyncio.run(self.monitor_api.cache.get(self.monitor_api.versioned_cache_key(generation, self.monitor_api.latest_snapshot_cache_key())))
        dated = asyncio.run(self.monitor_api.cache.get(self.monitor_api.versioned_cache_key(generation, self.monitor_api.snapshot_cache_key(today))))
        self.assertEqual(latest["generated_at"], "2026-06-03T08:00:00+00:00")
        self.assertEqual(dated["generated_at"], "2026-06-03T08:00:00+00:00")
        self.assertEqual(latest["cache_generation"], generation)

    def test_sse_event_format(self):
        event = self.monitor_api.sse_event("dashboard_update", {"type": "dashboard_update", "generated_at": "2026-06-03T08:00:00+00:00"})

        self.assertEqual(
            event,
            'event: dashboard_update\ndata: {"generated_at": "2026-06-03T08:00:00+00:00", "type": "dashboard_update"}\n\n',
        )

    def test_static_reports_keep_frontend_keys(self):
        report = self.monitor_service.report_from_aggregate_rows(
            [],
            {"models": {}, "updated": "test"},
            date(2026, 6, 1),
            date(2026, 6, 1),
            [],
            [],
        )

        self.assertGreaterEqual(
            set(report),
            {
                "totals",
                "by_day",
                "by_week",
                "by_month",
                "by_model",
                "by_effort",
                "by_account",
                "by_day_model",
                "by_day_account",
                "by_model_effort",
                "warnings",
                "pricing_metadata",
                "source_roots",
                "files_scanned",
                "usage_events",
            },
        )

    def test_daily_cache_key_versions_are_current(self):
        self.assertEqual(self.monitor_api.day_cache_key(date(2026, 6, 1)), "day:v8:2026-06-01:all")
        self.assertEqual(self.monitor_api.days_cache_key(date(2026, 6, 1), date(2026, 6, 2)), "days:v9:2026-06-01:2026-06-02:all")
        self.assertEqual(self.monitor_api.latest_snapshot_cache_key(), "snapshot-latest:v1")
        self.assertEqual(self.monitor_api.cache_keys_module.session_history_cache_key(date(2026, 6, 1), date(2026, 6, 2)), "sessions:v8:2026-06-01:2026-06-02:all")

    def test_exact_window_cache_keys_are_distinct_from_date_keys(self):
        start = datetime(2026, 6, 1, 8, 30, tzinfo=timezone.utc)
        end = datetime(2026, 6, 1, 12, 45, tzinfo=timezone.utc)

        self.assertEqual(
            self.monitor_api.cache_keys_module.report_window_cache_key(start, end),
            "report-window:v3:2026-06-01T08%3A30%3A00Z:2026-06-01T12%3A45%3A00Z:all",
        )
        self.assertNotEqual(
            self.monitor_api.cache_keys_module.days_window_cache_key(start, end),
            self.monitor_api.days_cache_key(date(2026, 6, 1), date(2026, 6, 1)),
        )
        self.assertTrue(self.monitor_api.cache_keys_module.session_history_window_cache_key(start, end).startswith("sessions-window:v4:"))
        self.assertTrue(self.monitor_api.cache_keys_module.session_detail_window_cache_key("session-a", start, end).startswith("session-window:v4:session-a:"))

    def test_live_window_cache_end_is_bucketed_to_minute(self):
        end = datetime(2026, 6, 1, 12, 45, 42, tzinfo=timezone.utc)

        self.assertEqual(
            self.monitor_api.cache_keys_module.bucket_window_end_for_cache(end).isoformat(),
            "2026-06-01T12:45:00+00:00",
        )

    def test_day_row_from_report_includes_uncached_tokens(self):
        report = self.sample_usage_report()
        row = self.monitor_api.day_row_from_report(report, date(2026, 6, 1))
        self.assertEqual(row["uncached_input_tokens"], 900)

    def test_days_response_serializes_schema(self):
        response = self.client.get("/api/days?date_from=not-a-date")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "date_from must be YYYY-MM-DD")
