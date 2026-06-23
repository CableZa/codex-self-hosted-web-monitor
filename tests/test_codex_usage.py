import contextlib
import json
import io
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import codex_usage
from codex_usage_models import ParseDiagnostics


def write_rollout(path, events):
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")


def token_event(timestamp, usage):
    return {
        "timestamp": timestamp,
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {
                "last_token_usage": usage,
                "total_token_usage": usage,
            },
        },
    }


class CodexUsageTests(unittest.TestCase):
    def test_parses_usage_with_current_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rollout = root / "rollout-test.jsonl"
            write_rollout(
                rollout,
                [
                    {
                        "timestamp": "2026-05-27T10:00:00Z",
                        "type": "session_meta",
                        "payload": {"id": "session-1", "cwd": "/Users/example/work/codex-self-hosted-web-monitor"},
                    },
                    {
                        "timestamp": "2026-05-27T10:00:01Z",
                        "type": "turn_context",
                        "payload": {"model": "gpt-5.5", "effort": "high"},
                    },
                    token_event(
                        "2026-05-27T10:00:02Z",
                        {
                            "input_tokens": 100000,
                            "cached_input_tokens": 20000,
                            "output_tokens": 10000,
                            "reasoning_output_tokens": 4000,
                            "total_tokens": 110000,
                        },
                    ),
                ],
            )

            with contextlib.redirect_stderr(io.StringIO()):
                records = list(codex_usage.parse_rollout(rollout))

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].model, "gpt-5.5")
        self.assertEqual(records[0].effort, "high")
        self.assertEqual(records[0].session_id, "session-1")
        self.assertEqual(records[0].usage.uncached_input_tokens, 80000)

    def test_parses_cumulative_total_usage_as_deltas(self):
        with tempfile.TemporaryDirectory() as tmp:
            rollout = Path(tmp) / "rollout-test.jsonl"
            write_rollout(
                rollout,
                [
                    {"timestamp": "2026-05-27T10:00:00Z", "type": "turn_context", "payload": {"model": "gpt-5.5"}},
                    {
                        "timestamp": "2026-05-27T10:00:01Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {"total_token_usage": {"input_tokens": 100, "cached_input_tokens": 10, "output_tokens": 20, "total_tokens": 120}},
                        },
                    },
                    {
                        "timestamp": "2026-05-27T10:00:02Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {"total_token_usage": {"input_tokens": 180, "cached_input_tokens": 30, "output_tokens": 50, "total_tokens": 230}},
                        },
                    },
                ],
            )

            records = list(codex_usage.parse_rollout(rollout))

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].usage.input_tokens, 100)
        self.assertEqual(records[1].usage.input_tokens, 80)
        self.assertEqual(records[1].usage.cached_input_tokens, 20)
        self.assertEqual(records[1].usage.output_tokens, 30)
        self.assertEqual(records[1].usage.total_tokens, 110)

    def test_parse_diagnostics_count_parser_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            rollout = Path(tmp) / "rollout-test.jsonl"
            rollout.write_text(
                "\n".join(
                    [
                        "{bad json",
                        json.dumps({"timestamp": "2026-05-27T10:00:00Z", "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 10, "total_tokens": 10}}}}),
                        json.dumps({"timestamp": "2026-05-27T10:00:01Z", "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 10, "total_tokens": 10}}}}),
                        json.dumps({"timestamp": "2026-05-27T10:00:02Z", "type": "event_msg", "payload": ["bad"]}),
                        json.dumps(token_event("2026-05-27T10:00:03Z", {"input_tokens": 5, "total_tokens": 5})),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            diagnostics = ParseDiagnostics()
            with contextlib.redirect_stderr(io.StringIO()):
                records = codex_usage.read_records([rollout], None, None, diagnostics=diagnostics)

        self.assertEqual(len(records), 2)
        self.assertEqual(diagnostics.invalid_json_events, 0)
        self.assertEqual(diagnostics.non_object_payload_events, 0)
        self.assertEqual(diagnostics.usage_lines_prefiltered, 2)
        self.assertEqual(diagnostics.cumulative_total_usage_events, 2)
        self.assertEqual(diagnostics.zero_usage_events, 1)
        self.assertEqual(diagnostics.last_token_usage_events, 1)
        self.assertEqual(diagnostics.usage_records, 2)

    def test_parses_headless_exec_usage_aliases_and_numeric_timestamps(self):
        with tempfile.TemporaryDirectory() as tmp:
            rollout = Path(tmp) / "run.jsonl"
            write_rollout(
                rollout,
                [
                    {
                        "type": "turn.completed",
                        "timestamp": 1_767_312_000_000,
                        "model": "gpt-5.5",
                        "usage": {
                            "prompt_tokens": "120",
                            "cached_tokens": "20",
                            "completion_tokens": "30",
                        },
                    },
                    {
                        "type": "result",
                        "data": {
                            "created_at": 1_767_312_001,
                            "model_name": "gpt-5.5-mini",
                            "usage": {
                                "input": 50,
                                "cache_read_input_tokens": 5,
                                "output": 12,
                                "reasoning_tokens": 3,
                            },
                        },
                    },
                ],
            )

            records = list(codex_usage.parse_rollout(rollout))

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].timestamp.isoformat(), "2026-01-02T00:00:00+00:00")
        self.assertEqual(records[0].model, "gpt-5.5")
        self.assertEqual(records[0].usage.input_tokens, 120)
        self.assertEqual(records[0].usage.cached_input_tokens, 20)
        self.assertEqual(records[0].usage.output_tokens, 30)
        self.assertEqual(records[0].usage.total_tokens, 150)
        self.assertEqual(records[1].model, "gpt-5.5-mini")
        self.assertEqual(records[1].usage.total_tokens, 65)

    def test_discovery_deduplicates_active_and_archived_relative_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions = root / "sessions"
            archive = root / "archived_sessions"
            sessions.mkdir()
            archive.mkdir()
            active = sessions / "session.jsonl"
            archived_duplicate = archive / "session.jsonl"
            archived_only = archive / "archived-only.jsonl"
            active.write_text("", encoding="utf-8")
            archived_duplicate.write_text("", encoding="utf-8")
            archived_only.write_text("", encoding="utf-8")

            discovered = codex_usage.discover_session_files([sessions, archive])

        self.assertEqual(discovered, [active, archived_only])

    def test_parse_rollout_skips_subagent_replayed_parent_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            rollout = Path(tmp) / "subagent.jsonl"
            write_rollout(
                rollout,
                [
                    {
                        "timestamp": "2026-05-27T10:00:00Z",
                        "type": "session_meta",
                        "payload": {"id": "subagent", "source": {"subagent": {"thread_spawn": {"parent_thread_id": "parent"}}}},
                    },
                    {
                        "timestamp": "2026-05-27T10:00:00Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "total_token_usage": {"input_tokens": 1000, "cached_input_tokens": 100, "output_tokens": 200, "total_tokens": 1200}
                            },
                        },
                    },
                    {
                        "timestamp": "2026-05-27T10:00:00Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "total_token_usage": {"input_tokens": 1500, "cached_input_tokens": 150, "output_tokens": 300, "total_tokens": 1800}
                            },
                        },
                    },
                    {
                        "timestamp": "2026-05-27T10:01:00Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "total_token_usage": {"input_tokens": 1600, "cached_input_tokens": 160, "output_tokens": 330, "total_tokens": 1930},
                                "model": "gpt-5.5",
                            },
                        },
                    },
                ],
            )

            records = list(codex_usage.parse_rollout(rollout))

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].usage.input_tokens, 100)
        self.assertEqual(records[0].usage.cached_input_tokens, 10)
        self.assertEqual(records[0].usage.output_tokens, 30)
        self.assertEqual(records[0].usage.total_tokens, 130)

    def test_parses_session_metadata_from_user_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rollout = root / "rollout-test.jsonl"
            write_rollout(
                rollout,
                [
                    {
                        "timestamp": "2026-05-27T10:00:00Z",
                        "type": "session_meta",
                        "payload": {"id": "session-1", "cwd": "/Users/example/work/codex-self-hosted-web-monitor"},
                    },
                    {
                        "timestamp": "2026-05-27T10:00:01Z",
                        "type": "event_msg",
                        "payload": {"type": "user_message", "message": "Build the dashboard\nwith session labels"},
                    },
                    {
                        "timestamp": "2026-05-27T10:00:02Z",
                        "type": "event_msg",
                        "payload": {"type": "user_message", "message": "Ship it"},
                    },
                ],
            )

            metadata = codex_usage.parse_rollout_metadata(rollout)

        self.assertEqual(metadata.session_id, "session-1")
        self.assertEqual(metadata.first_message, "Build the dashboard with session labels")
        self.assertEqual(metadata.last_message, "Ship it")
        self.assertEqual(metadata.project_path, "/Users/example/work/codex-self-hosted-web-monitor")
        self.assertEqual(metadata.project_name, "codex-self-hosted-web-monitor")

    def test_session_metadata_ignores_agents_context_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rollout = root / "rollout-test.jsonl"
            write_rollout(
                rollout,
                [
                    {
                        "timestamp": "2026-05-27T10:00:00Z",
                        "type": "session_meta",
                        "payload": {"id": "session-1"},
                    },
                    {
                        "timestamp": "2026-05-27T10:00:01Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": "# AGENTS.md instructions for /repo <INSTRUCTIONS> never respond with em dashes </INSTRUCTIONS>"}],
                        },
                    },
                    {
                        "timestamp": "2026-05-27T10:00:02Z",
                        "type": "event_msg",
                        "payload": {"type": "user_message", "message": "please add better session labels"},
                    },
                    {
                        "timestamp": "2026-05-27T10:00:03Z",
                        "type": "event_msg",
                        "payload": {"type": "user_message", "message": "ship the patch"},
                    },
                ],
            )

            metadata = codex_usage.parse_rollout_metadata(rollout)

        self.assertEqual(metadata.first_message, "please add better session labels")
        self.assertEqual(metadata.last_message, "ship the patch")

    def test_cost_subtracts_cached_input_and_does_not_double_charge_reasoning(self):
        usage = codex_usage.TokenUsage(
            input_tokens=100000,
            cached_input_tokens=20000,
            output_tokens=10000,
            reasoning_output_tokens=4000,
            total_tokens=110000,
        )
        rates = {"input": 5.0, "cached_input": 0.5, "output": 30.0, "reasoning_output": 30.0}

        cost = codex_usage.cost_for_usage(usage, rates)

        self.assertAlmostEqual(cost.input_usd, 0.4)
        self.assertAlmostEqual(cost.cached_input_usd, 0.01)
        self.assertAlmostEqual(cost.output_usd, 0.3)
        self.assertAlmostEqual(cost.reasoning_output_usd, 0.0)
        self.assertAlmostEqual(cost.total_usd, 0.71)
        self.assertAlmostEqual(cost.input_credits, 10.0)
        self.assertAlmostEqual(cost.cached_input_credits, 0.25)
        self.assertAlmostEqual(cost.output_credits, 7.5)
        self.assertAlmostEqual(cost.total_credits, 17.75)

    def test_cost_uses_explicit_codex_credit_rates(self):
        usage = codex_usage.TokenUsage(
            input_tokens=1_000_000,
            cached_input_tokens=0,
            output_tokens=1_000_000,
            total_tokens=2_000_000,
        )
        rates = {
            "input": 0.75,
            "cached_input": 0.075,
            "output": 4.5,
            "input_credits": 18.75,
            "cached_input_credits": 1.875,
            "output_credits": 113.0,
        }

        cost = codex_usage.cost_for_usage(usage, rates)

        self.assertAlmostEqual(cost.input_credits, 18.75)
        self.assertAlmostEqual(cost.output_credits, 113.0)
        self.assertAlmostEqual(cost.total_credits, 131.75)

    def test_cost_charges_reasoning_only_when_total_shows_extra_tokens(self):
        usage = codex_usage.TokenUsage(
            input_tokens=100,
            cached_input_tokens=0,
            output_tokens=10,
            reasoning_output_tokens=5,
            total_tokens=115,
        )
        rates = {"input": 0.0, "cached_input": 0.0, "output": 10.0, "reasoning_output": 20.0}

        cost = codex_usage.cost_for_usage(usage, rates)

        self.assertAlmostEqual(cost.output_usd, 0.0001)
        self.assertAlmostEqual(cost.reasoning_output_usd, 0.0001)

    def test_token_and_cost_dict_shapes_and_long_context_pricing(self):
        usage = codex_usage.TokenUsage(
            input_tokens=2000,
            cached_input_tokens=3000,
            output_tokens=1000,
            reasoning_output_tokens=100,
            total_tokens=3100,
        )
        rates = {
            "input": 1.0,
            "cached_input": 0.1,
            "output": 2.0,
            "reasoning_output": 3.0,
            "long_context": {"input_threshold": 1000, "input_multiplier": 2, "output_multiplier": 3},
        }

        cost = codex_usage.cost_for_usage(usage, rates)

        self.assertEqual(
            usage.as_dict(),
            {
                "input_tokens": 2000,
                "cached_input_tokens": 3000,
                "uncached_input_tokens": 0,
                "output_tokens": 1000,
                "reasoning_output_tokens": 100,
                "total_tokens": 3100,
            },
        )
        self.assertTrue(cost.long_context_applied)
        self.assertAlmostEqual(cost.cached_input_usd, 0.0004)
        self.assertAlmostEqual(cost.output_usd, 0.006)
        self.assertAlmostEqual(cost.reasoning_output_usd, 0.0009)
        self.assertAlmostEqual(cost.cached_input_credits, 0.005)
        self.assertAlmostEqual(cost.output_credits, 0.05)
        self.assertAlmostEqual(cost.reasoning_output_credits, 0.005)
        self.assertGreaterEqual(
            set(cost.as_dict()),
            {
                "input_usd",
                "cached_input_usd",
                "output_usd",
                "reasoning_output_usd",
                "total_usd",
                "input_credits",
                "cached_input_credits",
                "output_credits",
                "reasoning_output_credits",
                "total_credits",
                "long_context_applied",
            },
        )

    def test_report_groups_by_day_and_model(self):
        prices = {
            "models": {
                "gpt-5.5": {"input": 5.0, "cached_input": 0.5, "output": 30.0},
                "gpt-5.4-mini": {"input": 0.75, "cached_input": 0.075, "output": 4.5},
            }
        }
        records = [
            codex_usage.UsageRecord(
                timestamp=codex_usage.parse_timestamp("2026-05-27T10:00:00Z"),
                day="2026-05-27",
                model="gpt-5.5",
                effort="high",
                session_id="a",
                path="a.jsonl",
                usage=codex_usage.TokenUsage(input_tokens=1000, output_tokens=1000, total_tokens=2000),
            ),
            codex_usage.UsageRecord(
                timestamp=codex_usage.parse_timestamp("2026-05-28T10:00:00Z"),
                day="2026-05-28",
                model="gpt-5.4-mini",
                effort="low",
                session_id="b",
                path="b.jsonl",
                usage=codex_usage.TokenUsage(input_tokens=1000, output_tokens=1000, total_tokens=2000),
            ),
        ]

        report = codex_usage.build_report(
            records,
            prices,
            files_scanned=2,
            roots=[Path("sessions")],
            start_day=date(2026, 5, 27),
            end_day=date(2026, 5, 28),
        )

        self.assertEqual(report["totals"]["events"], 2)
        self.assertGreater(report["totals"]["total_credits"], 0)
        self.assertEqual([row["day"] for row in report["by_day"]], ["2026-05-28", "2026-05-27"])
        self.assertEqual({row["model"] for row in report["by_model"]}, {"gpt-5.5", "gpt-5.4-mini"})
        self.assertEqual({row["effort"] for row in report["by_effort"]}, {"high", "low"})

    def test_unknown_model_is_warned_and_zero_cost(self):
        prices = {"models": {}}
        records = [
            codex_usage.UsageRecord(
                timestamp=codex_usage.parse_timestamp("2026-05-27T10:00:00Z"),
                day="2026-05-27",
                model="missing-model",
                effort="unknown",
                session_id="a",
                path="a.jsonl",
                usage=codex_usage.TokenUsage(input_tokens=1000, output_tokens=1000, total_tokens=2000),
            )
        ]

        report = codex_usage.build_report(records, prices, 1, [Path("sessions")], None, None)

        self.assertEqual(report["totals"]["total_usd"], 0.0)
        self.assertEqual(report["totals"]["total_credits"], 0.0)
        self.assertIn("No price found for model 'missing-model'", report["warnings"][0])

    def test_report_groups_and_filters_by_account(self):
        prices = {"models": {"gpt-5.5": {"input": 1.0, "cached_input": 0.1, "output": 2.0}}}
        records = [
            codex_usage.UsageRecord(
                timestamp=codex_usage.parse_timestamp("2026-05-27T10:00:00Z"),
                day="2026-05-27",
                model="gpt-5.5",
                effort="high",
                session_id="a",
                path="a.jsonl",
                usage=codex_usage.TokenUsage(input_tokens=1000, output_tokens=1000, total_tokens=2000),
            ),
            codex_usage.UsageRecord(
                timestamp=codex_usage.parse_timestamp("2026-05-28T10:00:00Z"),
                day="2026-05-28",
                model="gpt-5.5",
                effort="high",
                session_id="b",
                path="b.jsonl",
                usage=codex_usage.TokenUsage(input_tokens=2000, output_tokens=2000, total_tokens=4000),
            ),
        ]

        def account_resolver(record):
            return "work@example.com" if record.day == "2026-05-27" else "personal@example.com"

        report = codex_usage.build_report(
            records,
            prices,
            files_scanned=2,
            roots=[Path("sessions")],
            start_day=date(2026, 5, 27),
            end_day=date(2026, 5, 28),
            account_resolver=account_resolver,
            account_filter={"personal@example.com"},
        )

        self.assertEqual(report["usage_events"], 1)
        self.assertEqual(report["totals"]["total_tokens"], 4000)
        self.assertEqual(report["by_account"][0]["account"], "personal@example.com")
        self.assertEqual(report["by_day_account"][0]["day"], "2026-05-28")

    def test_snapshot_model_uses_base_price(self):
        prices = {"models": {"gpt-5.4-mini": {"input": 0.75, "cached_input": 0.075, "output": 4.5}}}

        priced_model, rates = codex_usage.lookup_rates("gpt-5.4-mini-2026-03-17", prices)

        self.assertEqual(priced_model, "gpt-5.4-mini")
        self.assertIsNotNone(rates)

    def test_model_aliases_are_applied_before_snapshot_suffix(self):
        prices = {
            "aliases": {"gpt-5.5-latest": "gpt-5.5", "gpt-5.5-special": "gpt-5.5"},
            "models": {"gpt-5.5": {"input": 1, "cached_input": 0.1, "output": 2}},
        }

        self.assertEqual(codex_usage.lookup_rates("gpt-5.5-latest", prices)[0], "gpt-5.5")
        self.assertEqual(codex_usage.lookup_rates("gpt-5.5-special-2026-03-17", prices)[0], "gpt-5.5")

    def test_report_for_period_uses_supplied_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rollout = root / "rollout-test.jsonl"
            write_rollout(
                rollout,
                [
                    {
                        "timestamp": "2026-05-27T10:00:01Z",
                        "type": "context",
                        "payload": {
                            "model": "gpt-5.5",
                            "collaboration_mode": {"settings": {"reasoning_effort": "xhigh"}},
                        },
                    },
                    token_event(
                        "2026-05-27T10:00:02Z",
                        {"input_tokens": 1000, "output_tokens": 2000, "total_tokens": 3000},
                    ),
                ],
            )
            prices_path = root / "prices.json"
            prices_path.write_text(
                json.dumps({"models": {"gpt-5.5": {"input": 1, "cached_input": 0.1, "output": 2}}}),
                encoding="utf-8",
            )

            report = codex_usage.report_for_period(
                date(2026, 5, 27),
                date(2026, 5, 27),
                prices_path=prices_path,
                session_roots=[root],
            )

        self.assertEqual(report["totals"]["input_tokens"], 1000)
        self.assertEqual(report["totals"]["output_tokens"], 2000)
        self.assertEqual(report["by_effort"][0]["effort"], "xhigh")

    def test_filters_session_files_by_rollout_date_with_padding(self):
        files = [
            Path("sessions/2026/05/26/rollout-2026-05-26T10-00-00-a.jsonl"),
            Path("sessions/2026/05/27/rollout-2026-05-27T10-00-00-b.jsonl"),
            Path("sessions/2026/05/28/rollout-2026-05-28T10-00-00-c.jsonl"),
            Path("sessions/2026/05/30/rollout-2026-05-30T10-00-00-d.jsonl"),
        ]

        filtered = codex_usage.filter_session_files_by_period(
            files,
            date(2026, 5, 27),
            date(2026, 5, 28),
        )

        self.assertEqual(filtered, files[:3])

    def test_keeps_unknown_session_file_dates(self):
        unknown = Path("sessions/rollout-test.jsonl")

        filtered = codex_usage.filter_session_files_by_period(
            [unknown],
            date(2026, 5, 27),
            date(2026, 5, 28),
        )

        self.assertEqual(filtered, [unknown])

    def test_parse_rollout_skips_malformed_events_without_aborting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rollout = root / "rollout-test.jsonl"
            rollout.write_text(
                "\n".join(
                    [
                        "[]",
                        json.dumps({"payload": ["bad"]}),
                        json.dumps(token_event("not-a-date", {"input_tokens": 1})),
                        json.dumps(token_event("2026-05-27T10:00:02Z", {"input_tokens": "bad"})),
                        json.dumps(token_event("2026-05-27T10:00:02Z", None)),
                        json.dumps(token_event("2026-05-27T10:00:03Z", {"input_tokens": 2, "total_tokens": 2})),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with contextlib.redirect_stderr(io.StringIO()):
                records = list(codex_usage.parse_rollout(rollout))

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].usage.input_tokens, 2)

    def test_parse_rollout_warning_strings_stay_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            rollout = Path(tmp) / "rollout-test.jsonl"
            rollout.write_text(
                "\n".join(
                    [
                        "{bad json",
                        "[]",
                        json.dumps({"payload": [1]}),
                        json.dumps(token_event("2026-05-27T10:00:03Z", {"input_tokens": "bad"})),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                records = list(codex_usage.parse_rollout(rollout))

        self.assertEqual(records, [])
        warnings = stderr.getvalue().splitlines()
        self.assertIn(
            f"warning: skipped malformed usage event in {rollout}:4: input_tokens must be an integer",
            warnings,
        )

    def test_discovery_session_day_and_read_record_date_filtering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "sessions" / "2026" / "05" / "27"
            nested.mkdir(parents=True)
            rollout = nested / "rollout-2026-05-27T10-00-00-a.jsonl"
            write_rollout(
                rollout,
                [
                    token_event("2026-05-27T10:00:00Z", {"input_tokens": 1, "total_tokens": 1}),
                    token_event("2026-05-28T10:00:00Z", {"input_tokens": 2, "total_tokens": 2}),
                ],
            )

            discovered = codex_usage.discover_session_files([root / "sessions", root / "sessions"])
            records = codex_usage.read_records(discovered, date(2026, 5, 28), date(2026, 5, 28))

        self.assertEqual(discovered, [rollout])
        self.assertEqual(codex_usage.session_file_day(rollout), date(2026, 5, 27))
        self.assertEqual(codex_usage.session_file_day(Path("bad/2026/13/99/rollout-test.jsonl")), None)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].day, "2026-05-28")

    def test_account_resolver_does_not_mutate_records(self):
        prices = {"models": {"gpt-5.5": {"input": 1.0, "cached_input": 0.1, "output": 2.0}}}
        record = codex_usage.UsageRecord(
            timestamp=codex_usage.parse_timestamp("2026-05-27T10:00:00Z"),
            day="2026-05-27",
            model="gpt-5.5",
            effort="high",
            session_id="a",
            path="a.jsonl",
            usage=codex_usage.TokenUsage(input_tokens=1000, total_tokens=1000),
        )

        report = codex_usage.build_report(
            [record],
            prices,
            files_scanned=1,
            roots=[Path("sessions")],
            start_day=None,
            end_day=None,
            account_resolver=lambda _: "work@example.com",
        )

        self.assertEqual(record.account, "unknown")
        self.assertEqual(report["by_account"][0]["account"], "work@example.com")

    def test_csv_includes_account_groups(self):
        report = {
            "totals": {"sessions": 1, "events": 1, "input_tokens": 1, "cached_input_tokens": 0, "uncached_input_tokens": 1, "output_tokens": 0, "reasoning_output_tokens": 0, "total_tokens": 1, "total_usd": 0, "long_context_applied": False},
            "by_day": [],
            "by_model": [],
            "by_effort": [],
            "by_account": [{"account": "work@example.com", "sessions": 1, "events": 1, "input_tokens": 1, "cached_input_tokens": 0, "uncached_input_tokens": 1, "output_tokens": 0, "reasoning_output_tokens": 0, "total_tokens": 1, "total_usd": 0, "long_context_applied": False}],
            "by_day_model": [],
            "by_day_account": [{"day": "2026-05-27", "account": "work@example.com", "sessions": 1, "events": 1, "input_tokens": 1, "cached_input_tokens": 0, "uncached_input_tokens": 1, "output_tokens": 0, "reasoning_output_tokens": 0, "total_tokens": 1, "total_usd": 0, "long_context_applied": False}],
            "by_model_effort": [],
        }
        stream = io.StringIO()

        codex_usage.write_csv(report, stream)

        output = stream.getvalue()
        self.assertIn("account", output.splitlines()[0])
        self.assertIn("work@example.com", output)

    def test_cli_argument_normalization_and_json_output(self):
        report = {
            "generated_at": "2026-06-03T08:00:00Z",
            "period": {"from": "2026-06-03", "to": "2026-06-03"},
            "source_roots": [],
            "files_scanned": 0,
            "usage_events": 0,
            "totals": codex_usage.Aggregate().as_dict(),
            "by_day": [],
            "by_model": [],
            "by_effort": [],
            "by_account": [],
            "by_day_model": [],
            "by_day_account": [],
            "by_model_effort": [],
            "warnings": [],
            "pricing_metadata": {},
        }
        self.assertEqual(codex_usage.normalize_argv(["--days", "all"]), ["summary", "--days", "all"])
        self.assertEqual(codex_usage.normalize_argv(["prices"]), ["prices"])

        with patch.object(codex_usage, "report_for_period", return_value=report) as report_for_period:
            with patch.object(codex_usage, "write_json") as write_json:
                exit_code = codex_usage.main(["--days", "all", "--format", "json"])

        self.assertEqual(exit_code, 0)
        self.assertIsNone(report_for_period.call_args.args[0])
        self.assertIsNone(report_for_period.call_args.args[1])
        self.assertEqual(write_json.call_args.args[0]["usage_events"], 0)

    def test_cli_rejects_bad_days_and_reversed_periods(self):
        with self.assertRaisesRegex(SystemExit, "--from must be before or equal to --to"):
            args = codex_usage.make_parser().parse_args(
                ["summary", "--from", "2026-06-03", "--to", "2026-06-01"]
            )
            codex_usage.resolve_period(args)

        with self.assertRaises(Exception) as context:
            codex_usage.parse_days("0")
        self.assertIn("days must be positive", str(context.exception))


if __name__ == "__main__":
    unittest.main()
