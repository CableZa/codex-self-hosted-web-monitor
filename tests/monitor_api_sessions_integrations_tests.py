from .monitor_api_base import *


class MonitorApiSessionsIntegrationsTests(MonitorApiTestBase):
    def test_usage_bucket_aggregation_and_report_construction(self):
        bucket = self.monitor_api.empty_usage_bucket()
        self.monitor_api.add_aggregate_row(
            bucket,
            {
                "input_tokens": 100,
                "cached_input_tokens": 10,
                "output_tokens": 20,
                "reasoning_output_tokens": 5,
                "total_tokens": 125,
                "total_usd": 0.01,
                "total_credits": 1.5,
                "long_context_applied": True,
                "events": 2,
                "sessions": '["s1", "s2"]',
                "files": ["a.jsonl"],
            },
        )

        row = self.monitor_api.bucket_as_report_row(bucket)
        self.assertEqual(row["uncached_input_tokens"], 90)
        self.assertTrue(row["long_context_applied"])
        self.assertEqual(row["sessions"], 2)

        report = self.monitor_api.report_from_aggregate_rows(
            [
                {
                    "day": "2026-06-03",
                    "account": "work@example.com",
                    "model": "gpt-5.5",
                    "effort": "high",
                    **bucket,
                }
            ],
            {"models": {}, "updated": "test"},
            date(2026, 6, 3),
            date(2026, 6, 3),
            ["warning"],
            [],
        )

        self.assertEqual(report["totals"]["total_tokens"], 125)
        self.assertEqual(report["by_day_account"][0]["account"], "work@example.com")

    def test_session_history_aggregation_groups_by_session_and_model(self):
        report = self.sample_session_history_report()

        self.assertEqual(report["usage_events"], 3)
        self.assertEqual(len(report["sessions"]), 2)
        first_session = report["sessions"][0]
        self.assertEqual(first_session["session_id"], "session-b")
        self.assertEqual(first_session["display_title"], "Fix the parser")
        self.assertEqual(first_session["by_model"][0]["model"], "gpt-5.5")
        second_session = report["sessions"][1]
        self.assertEqual(second_session["session_id"], "session-a")
        self.assertEqual(second_session["first_message"], "Build the dashboard")
        self.assertEqual(second_session["last_message"], "Check the review")
        self.assertEqual(second_session["project_name"], "dashboard")
        self.assertEqual(second_session["project_path"], "/repo/dashboard")
        self.assertEqual(second_session["cache_hit_ratio"], round(400 / 3000, 4))
        self.assertEqual(second_session["efficiency_grade"], "S")
        self.assertEqual(second_session["waste_findings"][0]["id"], "right-sizing")
        self.assertIn("cache reuse", second_session["summary"])
        self.assertEqual(second_session["accounts"], ["work@example.com"])
        self.assertEqual([row["model"] for row in second_session["by_model"]], ["gpt-5.5", "gpt-5.4-mini"])
        self.assertGreater(second_session["duration_seconds"], 0)
        self.assertEqual(report["by_project"][0]["project"], "dashboard")
        self.assertEqual(report["by_project"][0]["sessions"], 1)
        self.assertEqual(report["by_project"][0]["files"], 1)
        self.assertEqual(report["cache_report"]["cache_efficiency"], round(400 / 3500, 4))
        self.assertEqual(len(report["account_switches"]), 1)
        self.assertEqual(report["account_switches"][0]["from_account"], "old@example.com")
        self.assertEqual(report["account_switches"][0]["to_account"], "work@example.com")

    def test_session_thresholds_change_reasons_and_cache_report(self):
        thresholds = self.monitor_usage.session_signal_thresholds({
            "session_high_input_tokens": "1000000",
            "session_high_uncached_input_tokens": "1000000",
            "session_low_cache_min_uncached_tokens": "1000000",
            "session_low_cache_max_reuse_ratio": "0.1",
            "session_large_total_tokens": "1000000",
            "session_high_output_tokens": "1000000",
            "session_long_context_pricing_signal_enabled": "false",
        })

        report = self.monitor_usage.session_history_report_from_records(
            self.sample_session_records(),
            {
                "models": {
                    "gpt-5.5": {"input": 1, "cached_input": 0.1, "output": 2},
                    "gpt-5.4-mini": {"input": 1, "cached_input": 0.1, "output": 2},
                }
            },
            {},
            2,
            [Path("sessions")],
            date(2026, 6, 1),
            date(2026, 6, 1),
            [],
            thresholds=thresholds,
        )

        self.assertEqual(report["cache_report"]["inefficient_sessions"], 0)
        self.assertEqual(report["sessions"][0]["long_context_reasons"], [])

    def test_session_detail_aggregation_includes_timeline(self):
        report = self.sample_session_detail_report()

        self.assertEqual(report["session_id"], "session-a")
        self.assertEqual(report["display_title"], "Build the dashboard")
        self.assertEqual(report["usage_events"], 2)
        self.assertEqual(report["duration_seconds"], 300)
        self.assertEqual(len(report["timeline"]), 2)
        self.assertEqual(report["timeline"][0]["priced_model"], "gpt-5.5")
        self.assertEqual(report["timeline"][1]["priced_model"], "gpt-5.4-mini")

    def test_account_switch_audit_uses_local_day_boundaries(self):
        with patch.dict(self.monitor_usage.account_switches_from_snapshots.__globals__, {"DEFAULT_TZ": "Africa/Johannesburg"}):
            switches = self.monitor_usage.account_switches_from_snapshots(
                [
                    {"observed_at": "2026-05-31T21:30:00Z", "email": "old@example.com"},
                    {"observed_at": "2026-05-31T22:30:00Z", "email": "new@example.com"},
                ],
                date(2026, 6, 1),
                date(2026, 6, 1),
            )

        self.assertEqual(len(switches), 1)
        self.assertEqual(switches[0]["from_account"], "old@example.com")
        self.assertEqual(switches[0]["to_account"], "new@example.com")

    def test_sessions_routes_contract(self):
        history = self.sample_session_history_report()
        detail = self.sample_session_detail_report()

        calls = []

        async def fake_session_history_report(start, end, account_filter=None):
            calls.append((start, end, account_filter))
            return history

        async def fake_session_detail_report(start, end, session_id, account_filter=None):
            calls.append((start, end, session_id, account_filter))
            return detail

        with patch.object(self.monitor_api, "session_history_report", side_effect=fake_session_history_report):
            response = self.client.get("/api/sessions?date_from=2026-06-01&date_to=2026-06-01&accounts=work@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls[0], (date(2026, 6, 1), date(2026, 6, 1), {"work@example.com"}))
        self.assertEqual(response.json()["sessions"][0]["session_id"], "session-b")

        with patch.object(self.monitor_api, "session_detail_report", side_effect=fake_session_detail_report):
            response = self.client.get("/api/sessions/session-a?date_from=2026-06-01&date_to=2026-06-01")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls[1], (date(2026, 6, 1), date(2026, 6, 1), "session-a", None))
        self.assertEqual(response.json()["session_id"], "session-a")
        self.assertEqual(response.json()["display_title"], "Build the dashboard")
        self.assertEqual(response.json()["usage_events"], 2)

        with patch.object(self.monitor_api, "session_detail_report", return_value=None):
            response = self.client.get("/api/sessions/missing?date_from=2026-06-01&date_to=2026-06-01")
        self.assertEqual(response.status_code, 404)

    def test_usage_diagnostics_route_contract(self):
        diagnostics = {
            "generated_at": "2026-06-01T10:00:00Z",
            "period": {"from": "2026-06-01", "to": "2026-06-01"},
            "source_roots": ["sessions"],
            "scan": {"filtered_files": 2, "usage_records": 3},
            "parser": {"invalid_json_events": 0, "malformed_usage_events": 0},
            "pricing": {"unpriced_models": [], "model_aliases": [], "long_context_events": 0},
            "attribution": {"unknown_account_events": 0, "account_filter": ["work@example.com"]},
            "activity": {"tool_calls": 4, "tool_errors": 1},
            "confidence_grade": "high",
            "confidence_reasons": ["No parser, pricing, or attribution issues were detected."],
            "warnings": [],
        }
        calls = []

        async def fake_usage_diagnostics_report(start, end, account_filter=None):
            calls.append((start, end, account_filter))
            return diagnostics

        with patch.object(self.monitor_api, "usage_diagnostics_report", side_effect=fake_usage_diagnostics_report):
            response = self.client.get("/api/usage-diagnostics?date_from=2026-06-01&date_to=2026-06-01&accounts=work@example.com")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls[0], (date(2026, 6, 1), date(2026, 6, 1), {"work@example.com"}))
        self.assertEqual(response.json()["confidence_grade"], "high")

    def test_usage_diagnostics_report_is_cached(self):
        diagnostics = {
            "generated_at": "2026-06-01T00:00:00Z",
            "period": {"from": "2026-06-01", "to": "2026-06-01"},
            "source_roots": ["sessions"],
            "scan": {"filtered_files": 2, "usage_records": 3},
            "parser": {"invalid_json_events": 0},
            "pricing": {},
            "attribution": {},
            "activity": {},
            "confidence_grade": "high",
            "confidence_reasons": [],
            "warnings": [],
        }
        import codex_monitor.api_usage_diagnostics as diagnostics_module

        with patch.object(diagnostics_module, "compute_usage_diagnostics_report", AsyncMock(return_value=diagnostics)) as compute_mock:
            first = asyncio.run(diagnostics_module.usage_diagnostics_report(date(2026, 6, 1), date(2026, 6, 1)))
            second = asyncio.run(diagnostics_module.usage_diagnostics_report(date(2026, 6, 1), date(2026, 6, 1)))

        self.assertFalse(first["cache"]["hit"])
        self.assertTrue(second["cache"]["hit"])
        self.assertEqual(compute_mock.await_count, 1)

    def test_sessions_exact_window_routes_contract(self):
        history = self.sample_session_history_report()
        detail = self.sample_session_detail_report()
        calls = []

        async def fake_session_history_report_for_window(start_at, end_at, account_filter=None):
            calls.append((start_at, end_at, account_filter))
            history["period"] = {"from": start_at.isoformat(), "to": end_at.isoformat()}
            return history

        async def fake_session_detail_report_for_window(start_at, end_at, session_id, account_filter=None):
            calls.append((start_at, end_at, session_id, account_filter))
            detail["period"] = {"from": start_at.isoformat(), "to": end_at.isoformat()}
            return detail

        with patch.object(self.monitor_api, "session_history_report_for_window", side_effect=fake_session_history_report_for_window):
            response = self.client.get("/api/sessions?start_at=2026-06-01T08:30&end_at=2026-06-01T12:45&accounts=work@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls[0], (
            datetime(2026, 6, 1, 8, 30, tzinfo=ZoneInfo("UTC")),
            datetime(2026, 6, 1, 12, 45, tzinfo=ZoneInfo("UTC")),
            {"work@example.com"},
        ))

        with patch.object(self.monitor_api, "session_detail_report_for_window", side_effect=fake_session_detail_report_for_window):
            response = self.client.get("/api/sessions/session-a?start_at=2026-06-01T08:30&end_at=2026-06-01T12:45")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls[1], (
            datetime(2026, 6, 1, 8, 30, tzinfo=ZoneInfo("UTC")),
            datetime(2026, 6, 1, 12, 45, tzinfo=ZoneInfo("UTC")),
            "session-a",
            None,
        ))

        with patch.object(self.monitor_api, "session_detail_report_for_window", return_value=None):
            response = self.client.get("/api/sessions/missing?start_at=2026-06-01T08:30&end_at=2026-06-01T12:45")
        self.assertEqual(response.status_code, 404)

    def test_fx_disabled_uses_fallback_without_http_client(self):
        self.monitor_api.shared_http_client = FakeHttpClient(get_error=AssertionError("should not fetch"))

        result = asyncio.run(
            self.monitor_api.fetch_usd_zar({"usd_zar_fallback_rate": "18.50"}, date(2026, 6, 3))
        )

        self.assertEqual(result, {"rate": 18.5, "source": "disabled", "day": "2026-06-03"})

    def test_fx_live_uses_http_client_and_falls_back(self):
        self.monitor_api.usage_module.FX_LIVE_ENABLED = True
        self.monitor_api.shared_http_client = FakeHttpClient(
            get_response=FakeResponse(payload={"rates": {"ZAR": 19.25}})
        )

        result = asyncio.run(
            self.monitor_api.fetch_usd_zar({"usd_zar_fallback_rate": "18.50"}, date(2026, 6, 3))
        )

        self.assertEqual(result, {"rate": 19.25, "source": "open.er-api.com", "day": "2026-06-03"})

        self.monitor_api.shared_http_client = FakeHttpClient(
            get_error=httpx.ConnectError("offline", request=httpx.Request("GET", "https://example.test"))
        )
        result = asyncio.run(
            self.monitor_api.fetch_usd_zar({"usd_zar_fallback_rate": "18.50"}, date(2026, 6, 4))
        )

        self.assertEqual(result, {"rate": 18.5, "source": "fallback", "day": "2026-06-04"})

    def test_fx_uses_cached_non_fallback_rate(self):
        self.monitor_api.usage_module.FX_LIVE_ENABLED = True
        day = date(2026, 6, 3)
        asyncio.run(self.monitor_api.store.save_fx_rate(day, 19.25, "test-source"))
        self.monitor_api.shared_http_client = FakeHttpClient(get_error=AssertionError("should not fetch"))

        result = asyncio.run(
            self.monitor_api.fetch_usd_zar({"usd_zar_fallback_rate": "18.50"}, day)
        )

        self.assertEqual(result, {"rate": 19.25, "source": "test-source", "day": "2026-06-03"})

    def test_webhook_success_and_failure_use_http_client(self):
        self.monitor_api.shared_http_client = FakeHttpClient(post_response=FakeResponse(status_code=204))

        result = asyncio.run(
            self.monitor_api.send_webhook({"webhook_url": "https://example.test/hook"}, {"type": "test"})
        )

        self.assertEqual(result, {"sent": True, "status": 204})

        self.monitor_api.shared_http_client = FakeHttpClient(
            post_error=httpx.ConnectError("offline", request=httpx.Request("POST", "https://example.test"))
        )
        result = asyncio.run(
            self.monitor_api.send_webhook({"webhook_url": "https://example.test/hook"}, {"type": "test"})
        )

        self.assertFalse(result["sent"])
        self.assertIn("offline", result["reason"])

if __name__ == "__main__":
    unittest.main()
