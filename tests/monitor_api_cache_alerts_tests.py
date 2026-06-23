from .monitor_api_base import *


class MonitorApiCacheAlertsTests(MonitorApiTestBase):
    def test_rate_card_shape(self):
        response = self.client.get("/api/rate-card")

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(
            set(response.json()),
            {"unit", "source", "updated", "fast_mode_detectable", "fast_mode_note", "rows"},
        )

    def test_test_webhook_shape_without_configured_url(self):
        response = self.client.post("/api/test-webhook")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"sent": False, "status": None, "reason": "webhook_url not configured"})

    def test_cache_keys_ttls_account_parsing_and_day_rows(self):
        day = date(2026, 6, 3)

        self.assertEqual(self.monitor_api.snapshot_cache_key(day), "snapshot:v7:2026-06-03")
        self.assertEqual(
            self.monitor_api.report_cache_key(day, day, {"beta@example.com", "alpha@example.com"}),
            "report:v9:2026-06-03:2026-06-03:alpha@example.com,beta@example.com",
        )
        self.assertEqual(
            self.monitor_api.days_cache_key(day, day, {"work@example.com"}),
            "days:v9:2026-06-03:2026-06-03:work@example.com",
        )
        self.assertEqual(self.monitor_api.day_cache_key(day), "day:v8:2026-06-03:all")
        self.assertEqual(
            self.monitor_api.cache_keys_module.session_detail_cache_key("s/a", day, day, {"work@example.com"}),
            "session:v8:s%2Fa:2026-06-03:2026-06-03:work@example.com",
        )
        self.assertEqual(
            self.monitor_api.parse_accounts_param(" a@example.com, ,b@example.com "),
            {"a@example.com", "b@example.com"},
        )
        self.assertEqual(self.monitor_api.parse_thresholds('["0.85", 0.7, 3, "bad", 0.7]'), [0.7, 0.85])

        with patch.object(self.monitor_api.cache_keys_module, "now_local", return_value=datetime(2026, 6, 3, tzinfo=timezone.utc)):
            self.assertEqual(self.monitor_api.ttl_for_range(day, day), self.monitor_api.TODAY_CACHE_TTL_SECONDS)
            self.assertEqual(
                self.monitor_api.ttl_for_range(date(2026, 6, 1), date(2026, 6, 2)),
                self.monitor_api.HISTORIC_CACHE_TTL_SECONDS,
            )

        report = self.sample_usage_report(day, day)
        row = self.monitor_api.day_row_from_report(report, day)
        self.assertEqual(row["day"], "2026-06-03")
        self.assertEqual(row["total_tokens"], 1200)
        self.assertEqual(self.monitor_api.empty_day_row(date(2026, 6, 4))["total_tokens"], 0)

    def test_summary_and_days_include_weekly_and_monthly_rollups(self):
        prices = {"models": {"gpt-5.5": {"input": 1.0, "cached_input": 0.1, "output": 2.0}}, "updated": "test"}
        rows = [
            {
                "day": "2026-06-01",
                "account": "work@example.com",
                "model": "gpt-5.5",
                "effort": "high",
                "input_tokens": 100,
                "cached_input_tokens": 10,
                "output_tokens": 20,
                "reasoning_output_tokens": 0,
                "total_tokens": 120,
                "input_usd": 0,
                "cached_input_usd": 0,
                "output_usd": 0,
                "reasoning_output_usd": 0,
                "total_usd": 0,
                "input_credits": 1,
                "cached_input_credits": 0.1,
                "output_credits": 2,
                "reasoning_output_credits": 0,
                "total_credits": 3.1,
                "events": 1,
                "sessions": {"session-a"},
                "files": {"a.jsonl"},
            },
            {
                "day": "2026-06-02",
                "account": "work@example.com",
                "model": "gpt-5.5",
                "effort": "high",
                "input_tokens": 200,
                "cached_input_tokens": 20,
                "output_tokens": 40,
                "reasoning_output_tokens": 0,
                "total_tokens": 240,
                "input_usd": 0,
                "cached_input_usd": 0,
                "output_usd": 0,
                "reasoning_output_usd": 0,
                "total_usd": 0,
                "input_credits": 2,
                "cached_input_credits": 0.2,
                "output_credits": 4,
                "reasoning_output_credits": 0,
                "total_credits": 6.2,
                "events": 1,
                "sessions": {"session-a"},
                "files": {"b.jsonl"},
            },
        ]

        report = self.monitor_service.report_from_aggregate_rows(rows, prices, date(2026, 6, 1), date(2026, 6, 2), [], [])
        days = self.monitor_api.days_response(
            date(2026, 6, 1),
            date(2026, 6, 2),
            report["by_day"],
            {"rate": 18.5, "source": "test", "day": "2026-06-02"},
            False,
            90,
        )

        self.assertEqual(report["by_week"][0]["week"], "2026-06-01")
        self.assertEqual(report["by_week"][0]["total_tokens"], 360)
        self.assertEqual(report["by_week"][0]["sessions"], 1)
        self.assertEqual(report["by_month"][0]["month"], "2026-06")
        self.assertEqual(report["by_month"][0]["start_day"], "2026-06-01")
        self.assertEqual(report["by_month"][0]["end_day"], "2026-06-30")
        self.assertEqual(days["weeks"][0]["day"], "2026-06-01")
        self.assertEqual(days["weeks"][0]["total_tokens"], 360)
        self.assertEqual(days["months"][0]["day"], "2026-06")

    def test_zero_usage_reports_are_not_cached_but_historic_day_rows_are(self):
        day = date(2026, 6, 3)
        empty_report = self.monitor_service.report_from_aggregate_rows(
            [],
            {"models": {}, "updated": "test"},
            day,
            day,
            [],
            [],
        )
        empty_report = self.monitor_api.add_zar(empty_report, 18.5)
        empty_report["exchange_rate"] = {"rate": 18.5, "source": "test", "day": day.isoformat()}
        empty_report["accounts"] = []

        async def fake_compute_usage_report(start, end, account_filter=None):
            return dict(empty_report)

        with patch.object(self.monitor_api.usage_module, "now_local", return_value=datetime(2026, 6, 3, tzinfo=timezone.utc)):
            with patch.object(self.monitor_api.usage_module, "compute_usage_report", side_effect=fake_compute_usage_report):
                response = asyncio.run(self.monitor_api.usage_report(day, day))

        self.assertFalse(self.monitor_api.usage_report_has_activity(response))
        generation = asyncio.run(self.monitor_api.store.cache_generation())
        self.assertIsNone(asyncio.run(self.monitor_api.cache.get(self.monitor_api.versioned_cache_key(generation, self.monitor_api.report_cache_key(day, day)))))

        days = self.monitor_api.days_response(
            day,
            day,
            [self.monitor_api.empty_day_row(day)],
            {"rate": 18.5, "source": "test", "day": day.isoformat()},
            False,
            90,
        )
        self.assertFalse(self.monitor_api.days_report_has_activity(days))
        asyncio.run(self.monitor_api.cache_day_rows_from_report(empty_report, day, day, generation=generation))
        cached_day = asyncio.run(self.monitor_api.cache.get(self.monitor_api.versioned_cache_key(generation, self.monitor_api.day_cache_key(day))))
        self.assertIsNotNone(cached_day)
        self.assertEqual(cached_day["events"], 0)

    def test_zero_usage_active_window_is_cached_briefly_by_bucketed_key(self):
        day = date(2026, 6, 3)
        start_at = datetime(2026, 6, 3, 0, 0, tzinfo=timezone.utc)
        first_end_at = datetime(2026, 6, 3, 12, 45, 12, tzinfo=timezone.utc)
        second_end_at = datetime(2026, 6, 3, 12, 45, 50, tzinfo=timezone.utc)
        empty_report = self.monitor_service.report_from_aggregate_rows(
            [],
            {"models": {}, "updated": "test"},
            day,
            day,
            [],
            [],
        )
        empty_report = self.monitor_api.add_zar(empty_report, 18.5)
        empty_report["exchange_rate"] = {"rate": 18.5, "source": "test", "day": day.isoformat()}
        empty_report["accounts"] = []

        with patch.object(self.monitor_api.usage_module, "now_local", return_value=datetime(2026, 6, 3, 13, 0, tzinfo=timezone.utc)):
            with patch.object(self.monitor_api.cache_keys_module, "now_local", return_value=datetime(2026, 6, 3, 13, 0, tzinfo=timezone.utc)):
                with patch.object(self.monitor_api.usage_module, "compute_usage_report_for_window", AsyncMock(return_value=dict(empty_report))) as compute_mock:
                    asyncio.run(self.monitor_api.usage_report_for_window(start_at, first_end_at))
                    response = asyncio.run(self.monitor_api.usage_report_for_window(start_at, second_end_at))

        self.assertFalse(self.monitor_api.usage_report_has_activity(response))
        self.assertTrue(response["cache"]["hit"])
        compute_mock.assert_awaited_once()

    def test_nonzero_token_zero_cost_usage_is_cacheable(self):
        day = date(2026, 6, 3)
        report = self.monitor_service.report_from_aggregate_rows(
            [
                {
                    "day": day.isoformat(),
                    "account": "work@example.com",
                    "model": "missing-model",
                    "effort": "high",
                    "input_tokens": 1000,
                    "cached_input_tokens": 0,
                    "output_tokens": 0,
                    "reasoning_output_tokens": 0,
                    "total_tokens": 1000,
                    "input_usd": 0,
                    "cached_input_usd": 0,
                    "output_usd": 0,
                    "reasoning_output_usd": 0,
                    "total_usd": 0,
                    "input_credits": 0,
                    "cached_input_credits": 0,
                    "output_credits": 0,
                    "reasoning_output_credits": 0,
                    "total_credits": 0,
                    "long_context_applied": False,
                    "events": 1,
                    "sessions": {"session-1"},
                    "files": {"rollout.jsonl"},
                }
            ],
            {"models": {}, "updated": "test"},
            day,
            day,
            [],
            [],
        )
        report = self.monitor_api.add_zar(report, 18.5)
        self.assertTrue(self.monitor_api.usage_report_has_activity(report))

        generation = asyncio.run(self.monitor_api.store.cache_generation())
        asyncio.run(self.monitor_api.cache_day_rows_from_report(report, day, day, generation=generation))
        cached = asyncio.run(self.monitor_api.cache.get(self.monitor_api.versioned_cache_key(generation, self.monitor_api.day_cache_key(day))))

        self.assertIsNotNone(cached)
        self.assertEqual(cached["total_tokens"], 1000)
        self.assertEqual(cached["total_credits"], 0)

    def test_empty_historic_days_are_marked_materialized(self):
        day = date(2026, 6, 3)

        async def fake_aggregate_rows_for_period(*_args, **_kwargs):
            return [], ["No Codex usage files were found under: /codex/sessions."]

        with patch.object(self.monitor_api.usage_module, "aggregate_rows_for_period", side_effect=fake_aggregate_rows_for_period):
            asyncio.run(self.monitor_api.ensure_historic_usage_aggregates("v4:test:test", day, day, []))

        days = asyncio.run(self.monitor_api.store.usage_aggregate_days("v4:test:test", day, day))
        self.assertEqual(days, {day.isoformat()})

    def test_missing_codex_files_and_auth_warnings_are_logged_and_reported(self):
        with tempfile.TemporaryDirectory() as codex_home:
            os.environ["CODEX_HOME"] = codex_home
            self.addCleanup(lambda: os.environ.pop("CODEX_HOME", None))

            with self.assertLogs("codex_monitor", level="WARNING") as logs:
                report = asyncio.run(self.monitor_api.compute_usage_report(date(2026, 6, 3), date(2026, 6, 3)))

        messages = "\n".join(logs.output)
        self.assertIn("codex_usage_roots_missing", messages)
        self.assertIn("codex_auth_file_missing", messages)
        self.assertTrue(any("Codex usage directories were not found" in warning for warning in report["warnings"]))
        self.assertTrue(any("Codex auth file was not found" in warning for warning in report["warnings"]))

    def test_existing_codex_dirs_without_rollouts_warn(self):
        with tempfile.TemporaryDirectory() as codex_home:
            root = Path(codex_home)
            (root / "sessions").mkdir()
            (root / "archived_sessions").mkdir()
            os.environ["CODEX_HOME"] = codex_home
            self.addCleanup(lambda: os.environ.pop("CODEX_HOME", None))

            with self.assertLogs("codex_monitor", level="WARNING") as logs:
                report = asyncio.run(self.monitor_api.compute_usage_report(date(2026, 6, 3), date(2026, 6, 3)))

        self.assertIn("codex_usage_files_missing", "\n".join(logs.output))
        self.assertTrue(any("No Codex usage files were found" in warning for warning in report["warnings"]))

    def test_budget_status_and_alert_payload_shapes(self):
        credit_settings = {
            "pricing_mode": "credits",
            "daily_budget_credits": "10",
            "weekly_budget_credits": "100",
            "monthly_budget_credits": "500",
            "daily_budget_zar": "50",
            "weekly_budget_zar": "250",
            "monthly_budget_zar": "1000",
            "dashboard_url": "http://127.0.0.1:8787",
        }
        reports = {
            "today": {"totals": {"total_credits": 12, "total_zar": 20, "total_usd": 1, "total_tokens": 100}},
            "week": {"totals": {"total_credits": 50, "total_zar": 80}},
            "month": {"totals": {"total_credits": 150, "total_zar": 200}},
        }

        self.assertEqual(self.monitor_api.budget_statuses(credit_settings, reports, date(2026, 6, 3)), [])

        settings = {**credit_settings, "pricing_mode": "zar"}
        statuses = self.monitor_api.budget_statuses(settings, reports, date(2026, 6, 3))
        self.assertEqual(statuses[0].period, "today")
        self.assertFalse(statuses[0].exceeded)
        self.assertEqual(statuses[0].unit, "zar")

        payload = self.monitor_api.alert_payload(statuses[0], reports["today"], settings)
        self.assertGreaterEqual(
            set(payload),
            {"type", "period", "budget_credits", "current_credits", "percent_used", "dashboard_url", "created_at"},
        )
        self.assertEqual(payload["percent_used"], 40.0)

    def test_account_burn_alert_payload_shape(self):
        status = self.monitor_api.AccountLimitStatus(
            id=1,
            account="work@example.com",
            metric="total_credits",
            cap_value=5000,
            current_value=4600,
            ratio=0.92,
            remaining_value=400,
            window_start=date(2026, 5, 29),
            window_end=date(2026, 6, 4),
            window_start_at="2026-05-29T00:00:00+00:00",
            window_end_at="2026-06-05T00:00:00+00:00",
            reset_at="2026-06-05T00:00:00+00:00",
            reset_weekday=4,
            reset_time="00:00",
            timezone="UTC",
            thresholds=[0.7, 0.85, 0.95, 1.0],
            crossed_thresholds=[0.7, 0.85],
            next_threshold=0.95,
            exceeded=False,
            enabled=True,
            elapsed_days=6,
            remaining_days=2,
            safe_daily_spend=200,
            spend_rate_vs_target=1.5,
            projected_exhaustion_date="2026-06-04",
            projected_exhaustion_label="Thursday",
            burn_severity="warning",
            burn_advisories=[],
        )
        advisory = {
            "id": "projected-exhaustion",
            "severity": "warning",
            "message": "At current pace you will run out by Thursday.",
            "label": "Projected",
            "value": "Thursday",
        }
        settings = {"dashboard_url": "http://127.0.0.1:8787"}

        payload = self.monitor_api.account_burn_alert_payload(status, advisory, settings)

        self.assertGreaterEqual(
            set(payload),
            {
                "type",
                "account",
                "severity",
                "advisory_id",
                "value",
                "projected_exhaustion_date",
                "safe_daily_spend",
                "dashboard_url",
            },
        )
        self.assertEqual(payload["type"], "account_burn_alert")

    def test_account_resolver_uses_latest_prior_snapshot(self):
        snapshots = [
            {"observed_at": "2026-06-01T10:00:00Z", "email": "first@example.com", "source": "manual"},
            {"observed_at": "2026-06-02T10:00:00Z", "email": "second@example.com", "source": "manual"},
        ]
        record = self.monitor_api.codex_usage.UsageRecord(
            timestamp=self.monitor_api.parse_snapshot_time("2026-06-02T12:00:00Z"),
            day="2026-06-02",
            model="gpt-5.5",
            effort="high",
            session_id="s",
            path="rollout.jsonl",
            usage=self.monitor_api.codex_usage.TokenUsage(),
        )

        resolver = self.monitor_api.account_resolver_from_snapshots(snapshots)

        self.assertEqual(resolver(record), "second@example.com")
        record.timestamp = self.monitor_api.parse_snapshot_time("2026-06-01T09:00:00Z")
        self.assertEqual(resolver(record), "unknown")

    def test_api_reports_bucket_records_by_configured_timezone(self):
        record = self.monitor_api.codex_usage.UsageRecord(
            timestamp=self.monitor_api.parse_snapshot_time("2026-05-31T22:30:00Z"),
            day="2026-05-31",
            model="gpt-5.5",
            effort="high",
            session_id="s",
            path="rollout-2026-05-31.jsonl",
            usage=self.monitor_api.codex_usage.TokenUsage(input_tokens=100, total_tokens=100),
        )

        with patch.object(self.monitor_usage, "DEFAULT_TZ", "Africa/Johannesburg"):
            self.assertEqual(self.monitor_usage.app_day_for_record(record), "2026-06-01")
            filtered = self.monitor_usage.filter_records_for_app_period([record], date(2026, 6, 1), date(2026, 6, 1))
            self.assertEqual(filtered, [record])

            rows, _warnings = self.monitor_api.aggregate_rows_from_records(filtered, {"models": {}, "updated": "test"})
            self.assertEqual(rows[0]["day"], "2026-06-01")
            buckets, _warnings = self.monitor_usage.aggregate_session_buckets_from_records(filtered, {"models": {}, "updated": "test"})
            detail = self.monitor_usage.session_detail_from_bucket(buckets["s"])
            self.assertEqual(detail["timeline"][0]["day"], "2026-06-01")

    def test_multi_day_session_usage_is_bucketed_by_event_day(self):
        prices = {"models": {"gpt-5.5": {"input": 5.0, "cached_input": 0.5, "output": 30.0}}, "updated": "test"}
        records = [
            self.monitor_api.codex_usage.UsageRecord(
                timestamp=self.monitor_api.parse_snapshot_time("2026-06-01T21:30:00Z"),
                day="2026-06-01",
                model="gpt-5.5",
                effort="high",
                session_id="s",
                path="rollout.jsonl",
                usage=self.monitor_api.codex_usage.TokenUsage(input_tokens=100, output_tokens=10, total_tokens=110),
            ),
            self.monitor_api.codex_usage.UsageRecord(
                timestamp=self.monitor_api.parse_snapshot_time("2026-06-01T22:30:00Z"),
                day="2026-06-01",
                model="gpt-5.5",
                effort="high",
                session_id="s",
                path="rollout.jsonl",
                usage=self.monitor_api.codex_usage.TokenUsage(input_tokens=200, output_tokens=20, total_tokens=220),
            ),
        ]

        with patch.object(self.monitor_usage, "DEFAULT_TZ", "Africa/Johannesburg"):
            filtered_day_two = self.monitor_usage.filter_records_for_app_period(records, date(2026, 6, 2), date(2026, 6, 2))
            self.assertEqual(filtered_day_two, [records[1]])

            rows, _warnings = self.monitor_api.aggregate_rows_from_records(records, prices)
            by_day = {row["day"]: row for row in rows}
            self.assertEqual(by_day["2026-06-01"]["input_tokens"], 100)
            self.assertEqual(by_day["2026-06-02"]["input_tokens"], 200)

            history = self.monitor_usage.session_history_report_from_records(
                records,
                prices,
                {},
                files_scanned=1,
                roots=[Path("sessions")],
                start_day=date(2026, 6, 1),
                end_day=date(2026, 6, 2),
                warnings=[],
            )
            self.assertEqual(len(history["sessions"]), 1)
            self.assertEqual(history["sessions"][0]["input_tokens"], 300)
            detail = self.monitor_usage.session_detail_from_bucket(
                self.monitor_usage.aggregate_session_buckets_from_records(records, prices)[0]["s"]
            )
            self.assertEqual([event["day"] for event in detail["timeline"]], ["2026-06-01", "2026-06-02"])
