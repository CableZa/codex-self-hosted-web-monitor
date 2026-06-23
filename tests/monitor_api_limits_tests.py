from .monitor_api_base import *


class MonitorApiLimitsTests(MonitorApiTestBase):
    def test_account_limit_request_validation(self):
        response = self.client.put(
            "/api/account-limits",
            json={
                "account": "",
                "metric": "total_tokens",
                "cap_value": 1,
                "timezone": "UTC",
            },
        )

        self.assertEqual(response.status_code, 422)

        response = self.client.put(
            "/api/account-limits",
            json={
                "account": "work@example.com",
                "metric": "total_credits",
                "cap_value": 1.5,
                "timezone": "UTC",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cap_value must be a whole number")

    def test_account_limit_requires_confirmed_auth_snapshot(self):
        with patch.object(self.monitor_api, "invalidate_derived_cache", AsyncMock()) as invalidate_mock:
            with patch.object(self.monitor_api, "schedule_snapshot_refresh") as refresh_mock:
                response = self.client.put(
                    "/api/account-limits",
                    json={
                        "account": "work@example.com",
                        "metric": "total_credits",
                        "cap_value": 5000,
                        "timezone": "UTC",
                    },
                )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "account must match a confirmed auth snapshot")
        invalidate_mock.assert_not_awaited()
        refresh_mock.assert_not_called()

    def test_account_limit_put_get_and_alert_contract(self):
        asyncio.run(
            self.monitor_api.store.record_auth_snapshot(
                {
                    "observed_at": "2026-06-01T09:00:00+00:00",
                    "email": "work@example.com",
                    "source": "manual",
                }
            )
        )

        fake_status = {
            "id": 1,
            "account": "work@example.com",
            "metric": "total_credits",
            "cap_value": 5000,
            "current_value": 3000,
            "ratio": 0.6,
            "remaining_value": 2000,
            "window_start": "2026-05-29",
            "window_end": "2026-06-04",
            "window_start_at": "2026-05-29T00:00:00+00:00",
            "window_end_at": "2026-06-05T00:00:00+00:00",
            "reset_at": "2026-06-05T00:00:00+00:00",
            "reset_weekday": 4,
            "reset_time": "00:00",
            "timezone": "UTC",
            "thresholds": [0.7, 0.85],
            "crossed_thresholds": [],
            "next_threshold": 0.7,
            "exceeded": False,
            "enabled": True,
            "elapsed_days": 3,
            "remaining_days": 5,
            "safe_daily_spend": 400,
            "spend_rate_vs_target": 1.2,
            "projected_exhaustion_date": "2026-06-04",
            "projected_exhaustion_label": "Thursday",
            "burn_severity": "warning",
            "burn_advisories": [
                {
                    "id": "projected-exhaustion",
                    "severity": "warning",
                    "message": "At current pace you will run out by Thursday.",
                    "label": "Projected",
                    "value": "Thursday",
                }
            ],
        }

        with patch.object(self.monitor_api, "account_limit_status_for_limit", AsyncMock(return_value=fake_status)) as status_mock:
            with patch.object(self.monitor_api, "schedule_snapshot_refresh") as refresh_mock:
                with patch.object(self.monitor_api.cache, "clear", AsyncMock(side_effect=AssertionError("account limit save must not clear all cache"))):
                    with patch.object(self.monitor_api, "build_snapshot", side_effect=AssertionError("API account limit updates must not rebuild snapshots")):
                        response = self.client.put(
                            "/api/account-limits",
                            json={
                                "account": "Work@Example.com",
                                "metric": "total_credits",
                                "cap_value": 5000,
                                "reset_weekday": 4,
                                "reset_time": "00:00",
                                "timezone": "UTC",
                                "thresholds": [0.7, "0.85", 2, -1],
                            },
                        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["limit"]["account"], "work@example.com")
        self.assertEqual(response.json()["limit"]["metric"], "total_credits")
        self.assertIsNone(response.json()["status"])
        self.assertEqual(response.json()["status_state"], "refreshing")
        status_mock.assert_not_awaited()
        refresh_mock.assert_called_once()
        self.assertEqual(refresh_mock.call_args.args[0], "account_limit")

        account_generation = asyncio.run(self.monitor_api.account_limit_cache_generation())
        asyncio.run(self.monitor_api.cache_account_limit_statuses([fake_status], account_generation))
        with patch.object(self.monitor_api, "account_limit_status_for_limit", AsyncMock(return_value=fake_status)) as get_status_mock:
            response = self.client.get("/api/account-limits")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["limits"][0]["account"], "work@example.com")
        self.assertEqual(response.json()["statuses"][0]["next_threshold"], 0.7)
        self.assertEqual(response.json()["status_state"], "ready")
        get_status_mock.assert_not_awaited()

        payload = {
            "type": "account_limit_alert",
            "account": "work@example.com",
            "metric": "total_credits",
            "window_start": "2026-05-29T00:00:00+00:00",
            "window_end": "2026-06-05T00:00:00+00:00",
        }
        asyncio.run(self.monitor_api.store.record_account_limit_alert(payload, 0.7))
        burn_payload = {
            "type": "account_burn_alert",
            "account": "work@example.com",
            "metric": "total_credits",
            "severity": "warning",
            "advisory_id": "projected-exhaustion",
            "window_start": "2026-05-29T00:00:00+00:00",
            "window_end": "2026-06-05T00:00:00+00:00",
            "value": "Thursday",
        }
        asyncio.run(self.monitor_api.store.record_account_burn_alert(burn_payload))
        response = self.client.get("/api/alerts?limit=1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["type"], "account_burn_alert")

        response = self.client.get("/api/alerts?limit=0")
        self.assertEqual(response.status_code, 400)

    def test_account_limits_get_does_not_recompute_live_status_when_snapshot_is_warming(self):
        asyncio.run(
            self.monitor_api.store.record_auth_snapshot(
                {
                    "observed_at": "2026-06-01T09:00:00+00:00",
                    "email": "work@example.com",
                    "source": "manual",
                }
            )
        )
        asyncio.run(
            self.monitor_api.store.upsert_account_limit(
                {
                    "account": "work@example.com",
                    "metric": "total_credits",
                    "cap_value": 5000,
                    "reset_weekday": 4,
                    "reset_time": "09:00",
                    "timezone": "UTC",
                    "thresholds": [0.7, 0.85],
                    "enabled": True,
                }
            )
        )
        self.monitor_api.latest_snapshot = {"status": "warming", "cache_generation": 1}
        asyncio.run(self.monitor_api.cache.clear())
        fake_status = {
            "id": 1,
            "account": "work@example.com",
            "metric": "total_credits",
            "cap_value": 5000,
            "current_value": 3000,
            "ratio": 0.6,
            "remaining_value": 2000,
            "window_start": "2026-05-29",
            "window_end": "2026-06-04",
            "window_start_at": "2026-05-29T00:00:00+00:00",
            "window_end_at": "2026-06-05T00:00:00+00:00",
            "reset_at": "2026-06-05T00:00:00+00:00",
            "reset_weekday": 4,
            "reset_time": "00:00",
            "timezone": "UTC",
            "thresholds": [0.7, 0.85],
            "crossed_thresholds": [],
            "next_threshold": 0.7,
            "exceeded": False,
            "enabled": True,
            "elapsed_days": 3,
            "remaining_days": 5,
            "safe_daily_spend": 400,
            "spend_rate_vs_target": 1.2,
            "projected_exhaustion_date": "2026-06-04",
            "projected_exhaustion_label": "Thursday",
            "burn_severity": "warning",
            "burn_advisories": [],
        }

        with patch.object(self.monitor_api, "account_limit_status_for_limit", AsyncMock(return_value=fake_status)) as status_mock:
            response = self.client.get("/api/account-limits")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["statuses"], [])
        self.assertEqual(response.json()["status_state"], "warming")
        status_mock.assert_not_awaited()

    def test_account_limit_save_keeps_other_statuses_visible_while_snapshot_is_warming(self):
        for account in ("work@example.com", "beta@example.com"):
            asyncio.run(
                self.monitor_api.store.record_auth_snapshot(
                    {
                        "observed_at": "2026-06-01T09:00:00+00:00",
                        "email": account,
                        "source": "manual",
                    }
                )
            )
        asyncio.run(
            self.monitor_api.store.upsert_account_limit(
                {
                    "account": "beta@example.com",
                    "metric": "total_credits",
                    "cap_value": 3200,
                    "reset_weekday": 4,
                    "reset_time": "09:00",
                    "timezone": "UTC",
                    "thresholds": [0.7, 0.85],
                    "enabled": True,
                }
            )
        )
        self.monitor_api.latest_snapshot = {"status": "warming", "cache_generation": 1}
        asyncio.run(self.monitor_api.cache.clear())

        statuses_by_account = {
            "work@example.com": {
                "id": 2,
                "account": "work@example.com",
                "metric": "total_credits",
                "cap_value": 5000,
                "current_value": 3000,
                "ratio": 0.6,
                "remaining_value": 2000,
                "window_start": "2026-05-29",
                "window_end": "2026-06-04",
                "window_start_at": "2026-05-29T00:00:00+00:00",
                "window_end_at": "2026-06-05T00:00:00+00:00",
                "reset_at": "2026-06-05T00:00:00+00:00",
                "reset_weekday": 4,
                "reset_time": "00:00",
                "timezone": "UTC",
                "thresholds": [0.7, 0.85],
                "crossed_thresholds": [],
                "next_threshold": 0.7,
                "exceeded": False,
                "enabled": True,
                "elapsed_days": 3,
                "remaining_days": 5,
                "safe_daily_spend": 400,
                "spend_rate_vs_target": 1.2,
                "projected_exhaustion_date": "2026-06-04",
                "projected_exhaustion_label": "Thursday",
                "burn_severity": "warning",
                "burn_advisories": [],
            },
            "beta@example.com": {
                "id": 1,
                "account": "beta@example.com",
                "metric": "total_credits",
                "cap_value": 3200,
                "current_value": 1200,
                "ratio": 0.375,
                "remaining_value": 2000,
                "window_start": "2026-05-29",
                "window_end": "2026-06-04",
                "window_start_at": "2026-05-29T00:00:00+00:00",
                "window_end_at": "2026-06-05T00:00:00+00:00",
                "reset_at": "2026-06-05T00:00:00+00:00",
                "reset_weekday": 4,
                "reset_time": "00:00",
                "timezone": "UTC",
                "thresholds": [0.7, 0.85],
                "crossed_thresholds": [],
                "next_threshold": 0.7,
                "exceeded": False,
                "enabled": True,
                "elapsed_days": 3,
                "remaining_days": 5,
                "safe_daily_spend": 400,
                "spend_rate_vs_target": 0.8,
                "projected_exhaustion_date": None,
                "projected_exhaustion_label": "Not projected this window",
                "burn_severity": "ok",
                "burn_advisories": [],
            },
        }

        async def fake_status(limit, today=None):
            return statuses_by_account[str(limit["account"])]

        account_generation = asyncio.run(self.monitor_api.account_limit_cache_generation())
        asyncio.run(
            self.monitor_api.cache_account_limit_statuses(
                [statuses_by_account["beta@example.com"], statuses_by_account["work@example.com"]],
                account_generation,
            )
        )

        with patch.object(self.monitor_api, "account_limit_status_for_limit", AsyncMock(side_effect=fake_status)) as status_mock:
            with patch.object(self.monitor_api, "schedule_snapshot_refresh") as refresh_mock:
                response = self.client.put(
                    "/api/account-limits",
                    json={
                        "account": "work@example.com",
                        "metric": "total_credits",
                        "cap_value": 5000,
                        "reset_weekday": 4,
                        "reset_time": "00:00",
                        "timezone": "UTC",
                        "thresholds": [0.7, 0.85],
                    },
                )

        self.assertEqual(response.status_code, 200)
        refresh_mock.assert_called_once()
        self.assertIsNone(response.json()["status"])
        self.assertEqual(response.json()["status_state"], "refreshing")
        status_mock.assert_not_awaited()

        with patch.object(self.monitor_api, "account_limit_status_for_limit", AsyncMock(side_effect=fake_status)) as get_status_mock:
            response = self.client.get("/api/account-limits")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            sorted(status["account"] for status in response.json()["statuses"]),
            ["beta@example.com"],
        )
        self.assertEqual(response.json()["status_state"], "refreshing")
        get_status_mock.assert_not_awaited()

    def test_refresh_snapshot_after_change_skips_stale_generation(self):
        self.monitor_api.requested_snapshot_generation = 4

        with patch.object(self.monitor_api.store, "cache_generation", AsyncMock(return_value=4)):
            with patch.object(self.monitor_api, "build_snapshot", AsyncMock(return_value={"generated_at": "2026-06-03T08:00:00+00:00"})) as build_mock:
                with patch.object(self.monitor_api, "publish_latest_snapshot", AsyncMock(return_value=False)) as publish_mock:
                    asyncio.run(self.monitor_api.refresh_snapshot_after_change("account_limit", 3))

        build_mock.assert_not_awaited()
        publish_mock.assert_not_awaited()

    def test_seed_latest_account_limit_statuses_skips_stale_generation(self):
        self.monitor_api.requested_snapshot_generation = 4
        self.monitor_api.latest_snapshot = {"status": "warming", "cache_generation": 4}

        seeded = self.monitor_api.seed_latest_account_limit_statuses(
            [{"account": "work@example.com", "ratio": 0.6}],
            expected_generation=3,
        )

        self.assertFalse(seeded)
        self.assertNotIn("account_limits", self.monitor_api.latest_snapshot)

    def test_account_limit_save_skips_seed_when_cache_generation_advanced_elsewhere(self):
        asyncio.run(
            self.monitor_api.store.record_auth_snapshot(
                {
                    "observed_at": "2026-06-01T09:00:00+00:00",
                    "email": "work@example.com",
                    "source": "manual",
                }
            )
        )
        fake_status = {
            "id": 1,
            "account": "work@example.com",
            "metric": "total_credits",
            "cap_value": 5000,
            "current_value": 3000,
            "ratio": 0.6,
            "remaining_value": 2000,
            "window_start": "2026-05-29",
            "window_end": "2026-06-04",
            "window_start_at": "2026-05-29T00:00:00+00:00",
            "window_end_at": "2026-06-05T00:00:00+00:00",
            "reset_at": "2026-06-05T00:00:00+00:00",
            "reset_weekday": 4,
            "reset_time": "00:00",
            "timezone": "UTC",
            "thresholds": [0.7, 0.85],
            "crossed_thresholds": [],
            "next_threshold": 0.7,
            "exceeded": False,
            "enabled": True,
            "elapsed_days": 3,
            "remaining_days": 5,
            "safe_daily_spend": 400,
            "spend_rate_vs_target": 1.2,
            "projected_exhaustion_date": "2026-06-04",
            "projected_exhaustion_label": "Thursday",
            "burn_severity": "warning",
            "burn_advisories": [],
        }

        with patch.object(self.monitor_api, "account_limit_cache_generation", AsyncMock(return_value=1)):
            with patch.object(self.monitor_api, "cached_account_limit_statuses", AsyncMock(return_value=[fake_status])):
                with patch.object(self.monitor_api, "invalidate_derived_cache", AsyncMock(return_value=3)):
                    with patch.object(self.monitor_api, "account_limit_status_for_limit", AsyncMock(return_value=fake_status)) as status_mock:
                        with patch.object(self.monitor_api, "seed_latest_account_limit_statuses") as seed_mock:
                            with patch.object(self.monitor_api, "schedule_snapshot_refresh") as refresh_mock:
                                response = self.client.put(
                                    "/api/account-limits",
                                    json={
                                        "account": "work@example.com",
                                        "metric": "total_credits",
                                        "cap_value": 5000,
                                        "reset_weekday": 4,
                                        "reset_time": "00:00",
                                        "timezone": "UTC",
                                        "thresholds": [0.7, 0.85],
                                    },
                                )

        self.assertEqual(response.status_code, 200)
        status_mock.assert_not_awaited()
        seed_mock.assert_not_called()
        refresh_mock.assert_called_once_with("account_limit", 3)

    def test_manual_auth_snapshot_creates_configured_auto_limit_defaults(self):
        os.environ["AUTO_ACCOUNT_LIMIT_EMAIL_SUFFIXES"] = "@auto-limit.example"
        self.addCleanup(lambda: os.environ.pop("AUTO_ACCOUNT_LIMIT_EMAIL_SUFFIXES", None))

        response = self.client.post(
            "/api/auth-snapshots",
            json={
                "observed_at": "2026-06-03T08:00:00+00:00",
                "email": "person@auto-limit.example",
                "source": "manual",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["inserted"])

        response = self.client.get("/api/account-limits")

        self.assertEqual(response.status_code, 200)
        created = next(limit for limit in response.json()["limits"] if limit["account"] == "person@auto-limit.example")
        self.assertEqual(created["metric"], "total_credits")
        self.assertEqual(created["cap_value"], 400)
        self.assertEqual(created["reset_weekday"], 4)
        self.assertEqual(created["reset_time"], "00:00")
        self.assertEqual(created["timezone"], "UTC")
        self.assertEqual(created["enabled"], 1)

    def test_manual_auth_snapshot_does_not_create_auto_limit_without_configured_suffix(self):
        response = self.client.post(
            "/api/auth-snapshots",
            json={
                "observed_at": "2026-06-03T08:00:00+00:00",
                "email": "person@auto-limit.example",
                "source": "manual",
            },
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.get("/api/account-limits")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["limits"], [])

    def test_manual_auth_snapshot_does_not_overwrite_existing_auto_limit(self):
        os.environ["AUTO_ACCOUNT_LIMIT_EMAIL_SUFFIXES"] = "@auto-limit.example"
        self.addCleanup(lambda: os.environ.pop("AUTO_ACCOUNT_LIMIT_EMAIL_SUFFIXES", None))

        asyncio.run(
            self.monitor_api.store.upsert_account_limit(
                {
                    "account": "person@auto-limit.example",
                    "metric": "total_credits",
                    "cap_value": 250,
                    "reset_weekday": 2,
                    "reset_time": "09:30",
                    "timezone": "UTC",
                    "thresholds": [0.7, 0.85, 0.95, 1.0],
                    "enabled": False,
                }
            )
        )
        response = self.client.post(
            "/api/auth-snapshots",
            json={
                "observed_at": "2026-06-03T08:00:00+00:00",
                "email": "person@auto-limit.example",
                "source": "manual",
            },
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.get("/api/account-limits")

        self.assertEqual(response.status_code, 200)
        existing = next(limit for limit in response.json()["limits"] if limit["account"] == "person@auto-limit.example")
        self.assertEqual(existing["cap_value"], 250)
        self.assertEqual(existing["reset_weekday"], 2)
        self.assertEqual(existing["reset_time"], "09:30")
        self.assertEqual(existing["timezone"], "UTC")
        self.assertEqual(existing["enabled"], 0)

    def test_account_limits_get_preserves_unconfirmed_custom_limit(self):
        asyncio.run(
            self.monitor_api.store.upsert_account_limit(
                {
                    "account": "legacy@example.com",
                    "metric": "total_credits",
                    "cap_value": 250,
                    "reset_weekday": 4,
                    "reset_time": "09:00",
                    "timezone": "UTC",
                    "thresholds": [0.7, 0.85, 0.95, 1.0],
                    "enabled": False,
                }
            )
        )

        self.monitor_api.latest_snapshot = {}
        response = self.client.get("/api/account-limits")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["limits"][0]["account"], "legacy@example.com")
        self.assertEqual(response.json()["statuses"], [])

    def test_account_limits_get_is_read_only(self):
        with patch.object(self.monitor_api, "ensure_default_account_limits_from_snapshots", side_effect=AssertionError("GET /api/account-limits must stay read-only")):
            with patch.object(self.monitor_api, "account_limit_statuses", side_effect=AssertionError("GET /api/account-limits must not recompute statuses")):
                response = self.client.get("/api/account-limits")

        self.assertEqual(response.status_code, 200)

    def test_account_limit_statuses_keep_previous_window_before_reset_time(self):
        asyncio.run(
            self.monitor_api.store.upsert_account_limit(
                {
                    "account": "work@example.com",
                    "metric": "total_credits",
                    "cap_value": 500,
                    "reset_weekday": 4,
                    "reset_time": "09:00",
                    "timezone": "UTC",
                    "thresholds": [0.7, 0.85, 0.95, 1.0],
                    "enabled": True,
                }
            )
        )
        fake_now = datetime(2026, 5, 29, 8, 0, tzinfo=ZoneInfo("UTC"))

        with patch.object(self.monitor_api.limits_module, "now_local", return_value=fake_now):
            with patch.object(
                self.monitor_api.alerts_module,
                "usage_report_for_window",
                AsyncMock(return_value={"totals": {"total_credits": 100}}),
            ) as report_mock:
                statuses = asyncio.run(self.monitor_api.account_limit_statuses(date(2026, 5, 29)))

        self.assertEqual(statuses[0]["window_start_at"], "2026-05-22T09:00:00+00:00")
        self.assertEqual(statuses[0]["window_end_at"], "2026-05-29T09:00:00+00:00")
        self.assertEqual(statuses[0]["window_end"], "2026-05-29")
        self.assertEqual(statuses[0]["remaining_days"], 1)
        self.assertEqual(statuses[0]["safe_daily_spend"], 400)
        self.assertEqual(report_mock.await_args.args[0].isoformat(), "2026-05-22T09:00:00+00:00")
        self.assertEqual(report_mock.await_args.args[1].isoformat(), "2026-05-29T08:00:00+00:00")

    def test_materialize_common_ranges_keeps_previous_window_before_reset_time(self):
        asyncio.run(
            self.monitor_api.store.upsert_account_limit(
                {
                    "account": "work@example.com",
                    "metric": "total_credits",
                    "cap_value": 500,
                    "reset_weekday": 4,
                    "reset_time": "09:00",
                    "timezone": "UTC",
                    "thresholds": [0.7, 0.85, 0.95, 1.0],
                    "enabled": True,
                }
            )
        )
        fake_now = datetime(2026, 5, 29, 8, 0, tzinfo=ZoneInfo("UTC"))

        with patch.object(self.monitor_api.limits_module, "now_local", return_value=fake_now):
            with patch.object(self.monitor_api.usage_module, "usage_report", AsyncMock(return_value={"totals": {}})):
                with patch.object(self.monitor_api.usage_module, "ensure_daily_cache_for_range", AsyncMock()):
                    with patch.object(self.monitor_api.usage_module, "days_report", AsyncMock(return_value={"rows": []})):
                        with patch.object(
                            self.monitor_api.usage_module,
                            "usage_report_for_window",
                            AsyncMock(return_value={"totals": {}}),
                        ) as usage_window_mock:
                            with patch.object(
                                self.monitor_api.usage_module,
                                "days_report_for_window",
                                AsyncMock(return_value={"rows": []}),
                            ) as days_window_mock:
                                with patch.object(self.monitor_api.usage_module, "session_history_report_for_window", AsyncMock(return_value={"sessions": []})):
                                    asyncio.run(self.monitor_api.materialize_common_ranges(date(2026, 5, 29)))

        self.assertEqual(usage_window_mock.await_args.args[0].isoformat(), "2026-05-22T09:00:00+00:00")
        self.assertEqual(usage_window_mock.await_args.args[1].isoformat(), "2026-05-29T08:00:00+00:00")
        self.assertEqual(days_window_mock.await_args.args[0].isoformat(), "2026-05-22T09:00:00+00:00")
        self.assertEqual(days_window_mock.await_args.args[1].isoformat(), "2026-05-29T08:00:00+00:00")

    def test_build_snapshot_passes_real_datetime_into_account_limit_flows(self):
        snapshot_now = datetime(2026, 5, 29, 0, 30, tzinfo=ZoneInfo("UTC"))

        with patch.object(self.monitor_api.alerts_module, "now_local", return_value=snapshot_now):
            with patch.object(self.monitor_api.alerts_module, "usage_report", AsyncMock(return_value={"totals": {}, "warnings": []})):
                with patch.object(self.monitor_api.store, "settings", AsyncMock(return_value={"pricing_mode": "credits"})):
                    with patch.object(self.monitor_api.alerts_module, "check_alerts", AsyncMock(return_value=[])):
                        with patch.object(self.monitor_api.alerts_module, "migrate_account_limits_to_credits", AsyncMock()) as migrate_mock:
                            with patch.object(self.monitor_api.alerts_module, "account_limit_statuses", AsyncMock(return_value=[])) as statuses_mock:
                                with patch.object(self.monitor_api.alerts_module, "check_account_limit_alerts", AsyncMock(return_value=[])):
                                    with patch.object(self.monitor_api.alerts_module, "check_account_burn_alerts", AsyncMock(return_value=[])):
                                        with patch.object(self.monitor_api.cache, "status", AsyncMock(return_value={"ok": True})):
                                            asyncio.run(self.monitor_api.build_snapshot())

        migrate_mock.assert_awaited_once_with(snapshot_now)
        statuses_mock.assert_awaited_once_with(snapshot_now)

    def test_run_scanner_followup_passes_real_datetime_into_materialization(self):
        snapshot_now = datetime(2026, 5, 29, 0, 30, tzinfo=ZoneInfo("UTC"))

        with patch.object(self.monitor_api, "now_local", return_value=snapshot_now):
            with patch.object(self.monitor_api, "days_report", AsyncMock()) as days_mock:
                with patch.object(self.monitor_api, "maybe_send_summaries", AsyncMock()) as summaries_mock:
                    with patch.object(self.monitor_api, "materialize_common_ranges", AsyncMock()) as materialize_mock:
                        asyncio.run(self.monitor_api.run_scanner_followup({"version": "test"}))

        days_mock.assert_awaited_once_with(date(2026, 4, 29), date(2026, 5, 29))
        summaries_mock.assert_awaited_once_with({"version": "test"})
        materialize_mock.assert_awaited_once_with(snapshot_now)

    def test_scanner_iteration_keeps_snapshot_on_followup_failure(self):
        snapshot = {"version": "0.11.0", "generated_at": "2026-06-03T08:00:00+00:00"}

        with patch.object(self.monitor_api, "sync_scanner_state", AsyncMock()) as sync_mock:
            with patch.object(self.monitor_api, "build_snapshot", AsyncMock(return_value=snapshot)) as build_mock:
                with patch.object(self.monitor_api, "publish_latest_snapshot", AsyncMock()) as publish_mock:
                    with patch.object(self.monitor_api, "run_scanner_followup", AsyncMock(side_effect=RuntimeError("followup failed"))):
                        with patch.object(self.monitor_api.logger, "exception") as exception_mock:
                            asyncio.run(self.monitor_api.run_scanner_iteration())

        sync_mock.assert_awaited_once()
        build_mock.assert_awaited_once()
        publish_mock.assert_awaited_once_with(snapshot, 1)
        messages = [call.args[0] for call in exception_mock.call_args_list]
        self.assertIn("scanner_followup_failed", messages)
        self.assertNotIn("scanner_loop_failed", messages)

    def test_publish_latest_snapshot_recovers_stale_local_generation(self):
        generation = asyncio.run(self.monitor_api.store.cache_generation())
        self.monitor_api.requested_snapshot_generation = generation - 1

        published = asyncio.run(
            self.monitor_api.publish_latest_snapshot(
                {"version": "test", "generated_at": "2026-06-03T08:00:00+00:00"},
                generation,
            )
        )

        self.assertTrue(published)
        self.assertEqual(self.monitor_api.requested_snapshot_generation, generation)
        self.assertEqual(self.monitor_api.latest_snapshot["cache_generation"], generation)

    def test_publish_latest_snapshot_skips_when_shared_generation_advances(self):
        expected_generation = asyncio.run(self.monitor_api.store.cache_generation())
        current_generation = asyncio.run(self.monitor_api.store.bump_cache_generation("test"))
        self.monitor_api.requested_snapshot_generation = expected_generation

        published = asyncio.run(
            self.monitor_api.publish_latest_snapshot(
                {"version": "test", "generated_at": "2026-06-03T08:00:00+00:00"},
                expected_generation,
            )
        )

        self.assertFalse(published)
        self.assertEqual(self.monitor_api.requested_snapshot_generation, current_generation)
        self.assertNotEqual(self.monitor_api.latest_snapshot.get("cache_generation"), expected_generation)

    def test_invalidate_derived_cache_marks_warming_snapshot_reason(self):
        generation = asyncio.run(self.monitor_api.invalidate_derived_cache("account_limit"))

        self.assertEqual(self.monitor_api.latest_snapshot["status"], "warming")
        self.assertEqual(self.monitor_api.latest_snapshot["cache_generation"], generation)
        self.assertEqual(self.monitor_api.latest_snapshot["update_reason"], "account_limit")

    def test_scanner_iteration_invalidates_once_when_auth_and_limits_change(self):
        with patch.object(self.monitor_api, "record_current_auth_snapshot", AsyncMock(return_value={"_inserted": True})) as record_mock:
            with patch.object(self.monitor_api.store, "auth_snapshots", AsyncMock(return_value=[{"email": "person@auto-limit.example"}])) as snapshots_mock:
                with patch.object(self.monitor_api, "ensure_default_account_limits_from_snapshots", AsyncMock(return_value=[{"_inserted": True}])) as ensure_mock:
                    with patch.object(self.monitor_api, "invalidate_derived_cache", AsyncMock()) as invalidate_mock:
                        reasons = asyncio.run(self.monitor_api.sync_scanner_state())

        record_mock.assert_awaited_once()
        snapshots_mock.assert_awaited_once_with(limit=1000)
        ensure_mock.assert_awaited_once_with([{"email": "person@auto-limit.example"}])
        invalidate_mock.assert_awaited_once_with("auth_snapshot+default_account_limits")
        self.assertEqual(reasons, ["auth_snapshot", "default_account_limits"])

    def test_compute_usage_report_skips_historic_materialization_in_api_only_mode(self):
        prices = {"models": {"gpt-5.5": {"input": 1.0, "cached_input": 0.1, "output": 2.0}}, "updated": "test"}

        async def fake_aggregate_rows(period_start, _period_end, _snapshots, account_filter=None, start_at=None, end_at=None, unknown_account_mapping=""):
            account = sorted(account_filter)[0] if account_filter else "work@example.com"
            return (
                [
                    {
                        "day": period_start.isoformat(),
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
                        "reasoning_output_usd": 0.0,
                        "total_usd": 0.00301,
                        "input_credits": 1.0,
                        "cached_input_credits": 0.1,
                        "output_credits": 2.0,
                        "reasoning_output_credits": 0.0,
                        "total_credits": 3.1,
                        "long_context_applied": False,
                        "events": 1,
                        "sessions": {"session-1"},
                        "files": {"rollout.jsonl"},
                    }
                ],
                [],
            )

        with patch.object(self.monitor_usage, "now_local", return_value=datetime(2026, 6, 3, 12, tzinfo=timezone.utc)):
            with patch.object(self.monitor_usage.store, "settings", AsyncMock(return_value={"unknown_account_mapping": ""})):
                with patch.object(self.monitor_usage.store, "auth_snapshots", AsyncMock(return_value=[])):
                    with patch.object(self.monitor_usage.codex_usage, "load_prices", return_value=prices):
                        with patch.object(self.monitor_usage, "ensure_historic_usage_aggregates", side_effect=AssertionError("API-only reports must not persist historic aggregates")):
                            with patch.object(self.monitor_usage.store, "usage_aggregate_rows", side_effect=AssertionError("API-only reports must not read persisted historic aggregates on miss")):
                                with patch.object(self.monitor_usage.store, "usage_aggregate_warnings", side_effect=AssertionError("API-only reports must not read persisted historic aggregate warnings on miss")):
                                    with patch.object(self.monitor_usage, "aggregate_rows_for_period", AsyncMock(side_effect=fake_aggregate_rows)) as aggregate_mock:
                                        with patch.object(self.monitor_usage, "fetch_usd_zar", AsyncMock(return_value={"rate": 18.5, "source": "test", "day": "2026-06-03"})):
                                            report = asyncio.run(self.monitor_usage.compute_usage_report(date(2026, 6, 1), date(2026, 6, 3)))

        self.assertEqual(report["totals"]["total_tokens"], 2400)
        self.assertEqual(aggregate_mock.await_count, 2)
