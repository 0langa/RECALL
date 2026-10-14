"""Codex hook wire responses must not expose RECALL's internal result fields."""
from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import config as recall_config
import turn_policy
from tests.test_hooks import run_hook


class HookOutputContractTests(unittest.TestCase):
    def test_disabled_lifecycle_uses_common_output_without_memory_access(self):
        # Official release contract, checked 2026-10-01:
        # https://learn.chatgpt.com/docs/hooks#common-output-fields
        # These fields are valid for all five events, including PreCompact,
        # which does not accept the decision-specific "reason" field.
        expected = {"continue": True, "systemMessage": "RECALL is disabled for this turn."}
        hooks = (
            ("UserPromptSubmit", "prompt_inspector.py"),
            ("SessionStart", "session_start.py"),
            ("PostToolUse", "post_tool_use.py"),
            ("PreCompact", "pre_compact.py"),
            ("Stop", "stop.py"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            recall_config.activate_project(tmp)
            marker = "PRIVATE-HOOK-CONTRACT-CONTENT"
            payload = {
                "cwd": tmp, "session_id": "contract-session", "turn_id": "private-turn",
                "provider": "codex", "prompt": "Do not use memory for this task. " + marker,
                "tool_name": "Bash", "tool_input": {"command": "python -m pytest"},
                "tool_response": {"exit_code": 1, "stderr": "FAILED " + marker},
                "summary": marker, "last_assistant_message": marker,
            }
            with ExitStack() as stack:
                for target in (
                    "storage.iter_records", "storage.write_transaction",
                    "retrieval.assess_relevance", "turn_buffer.mark_active", "turn_buffer.append_event",
                ):
                    stack.enter_context(patch(target, side_effect=AssertionError("private memory access")))
                for event, script in hooks:
                    with self.subTest(event=event):
                        output = run_hook(script, {**payload, "hook_event_name": event})
                        self.assertEqual(output, expected)
                        self.assertTrue(turn_policy.policy_status(
                            tmp, "contract-session", "private-turn", provider="codex",
                        )["disabled"])
                # Closing the turn must retain its policy for late deliveries.
                for event, script in hooks[2:]:
                    with self.subTest(replay=event):
                        self.assertEqual(run_hook(script, {**payload, "hook_event_name": event}), expected)
            for path in recall_config.memory_dir(tmp).rglob("*"):
                if path.is_file():
                    self.assertNotIn(marker.encode(), path.read_bytes(), str(path))

    def test_non_hook_callers_keep_machine_readable_disabled_result(self):
        self.assertEqual(turn_policy.disabled_result(), {
            "action": "disabled", "reason": "task_no_memory", "memory_action": "disabled",
        })


if __name__ == "__main__":
    unittest.main()
