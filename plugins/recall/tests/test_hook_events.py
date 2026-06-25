from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from hook_events import HookEvent  # noqa: E402


class HookEventTests(unittest.TestCase):
    def test_codex_tool_payload_normalizes_to_compatibility_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = {
                "hook_event_name": "PostToolUse",
                "session_id": "session-codex",
                "turn_id": "turn-codex",
                "cwd": tmp,
                "tool_name": "Bash",
                "tool_input": {"command": "python -m pytest"},
                "tool_response": {"exit_code": 0, "stdout": "1 passed", "stderr": ""},
            }
            event = HookEvent.from_payload(payload, fallback_event="PostToolUse")
            compat = event.compatibility_payload()

            self.assertEqual(event.provider, "codex")
            self.assertEqual(event.event_name, "PostToolUse")
            self.assertEqual(event.session_id, "session-codex")
            self.assertEqual(event.turn_id, "turn-codex")
            self.assertEqual(event.command, "python -m pytest")
            self.assertIn("1 passed", event.output_text())
            self.assertEqual(compat["tool_response"]["exit_code"], 0)
            self.assertEqual(compat["origin_provider"], "codex")

    def test_kimi_failure_payload_gets_exit_code_and_provider_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = {
                "hook_event_name": "PostToolUseFailure",
                "session_id": "session-kimi",
                "cwd": tmp,
                "tool_name": "Bash",
                "tool_input": {"command": "python -m pytest tests/missing.py"},
                "error": "failed with AssertionError",
            }
            event = HookEvent.from_payload(payload, fallback_event="PostToolUse", provider="kimi")
            compat = event.compatibility_payload()
            metadata = event.provider_metadata(capture_channel="hook")

            self.assertEqual(event.provider, "kimi")
            self.assertEqual(event.event_name, "PostToolUseFailure")
            self.assertEqual(event.tool_response["exit_code"], 1)
            self.assertIn("AssertionError", event.output_text())
            self.assertEqual(compat["tool_response"]["exit_code"], 1)
            self.assertEqual(metadata["origin_provider"], "kimi")
            self.assertEqual(metadata["source_session"], "session-kimi")
            self.assertEqual(metadata["capture_channel"], "hook")


if __name__ == "__main__":
    unittest.main()
