import json
import tempfile
import unittest
from pathlib import Path

import codex_usage
from codex_usage_models import ParseDiagnostics


def write_jsonl(path: Path, events: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")


class UsagePrefilterTests(unittest.TestCase):
    def test_usage_prefilter_skips_irrelevant_lines_without_changing_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            rollout = Path(tmp) / "rollout-test.jsonl"
            write_jsonl(
                rollout,
                [
                    {"type": "response_item", "payload": {"type": "message", "content": "noise"}},
                    {"type": "event_msg", "payload": {"type": "turn_context", "model": "gpt-5.5", "effort": "high"}},
                    {"type": "event_msg", "payload": {"type": "log", "message": "nothing to bill"}},
                    {
                        "timestamp": "2026-06-20T10:00:00Z",
                        "type": "event_msg",
                        "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 10, "output_tokens": 2}}},
                    },
                ],
            )
            diagnostics = ParseDiagnostics()
            file_size = rollout.stat().st_size

            records = codex_usage.read_records([rollout], None, None, diagnostics=diagnostics)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].model, "gpt-5.5")
        self.assertEqual(records[0].usage.total_tokens, 12)
        self.assertEqual(diagnostics.usage_lines_scanned, 4)
        self.assertEqual(diagnostics.usage_lines_prefiltered, 2)
        self.assertEqual(diagnostics.json_decode_attempts, 2)
        self.assertGreaterEqual(diagnostics.scan_bytes, file_size)
        self.assertGreaterEqual(diagnostics.usage_parse_ms, 0)

    def test_metadata_prefilter_keeps_session_and_tool_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            rollout = Path(tmp) / "rollout-test.jsonl"
            write_jsonl(
                rollout,
                [
                    {"type": "response_item", "payload": {"type": "message", "content": "noise"}},
                    {"type": "session_meta", "payload": {"id": "session-1", "cwd": "/tmp/project"}},
                    {"type": "event_msg", "payload": {"type": "user_message", "message": "please check this"}},
                    {"type": "event_msg", "payload": {"type": "function_call", "name": "exec_command", "status": "error"}},
                ],
            )
            diagnostics = ParseDiagnostics()

            metadata = codex_usage.parse_rollout_metadata(rollout, diagnostics)

        self.assertEqual(metadata.session_id, "session-1")
        self.assertEqual(metadata.project_name, "project")
        self.assertEqual(metadata.first_message, "please check this")
        self.assertEqual(metadata.tool_call_count, 1)
        self.assertEqual(metadata.tool_error_count, 1)
        self.assertEqual(diagnostics.metadata_lines_scanned, 4)
        self.assertEqual(diagnostics.metadata_lines_prefiltered, 1)


if __name__ == "__main__":
    unittest.main()
