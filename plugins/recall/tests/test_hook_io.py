"""Direct tests for hook payload normalization and compact output helpers."""
from __future__ import annotations

from io import BytesIO, StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "hooks" / "scripts"))

import hook_io


class _BinaryInput:
    def __init__(self, value: bytes) -> None:
        self.buffer = BytesIO(value)


class HookIoTests(unittest.TestCase):
    def test_read_hook_input_accepts_utf8_bom_and_rejects_non_objects(self) -> None:
        raw = '\ufeff{"cwd":"C:/project","prompt":"Gr\u00fc\u00dfe"}'.encode("utf-8")
        with patch.object(sys, "stdin", _BinaryInput(raw)):
            payload, text = hook_io.read_hook_input()
        self.assertEqual(payload["prompt"], "Gr\u00fc\u00dfe")
        self.assertTrue(text.startswith("{"))

        for source, expected in (("", ({}, "")), ("[1]", ({}, "[1]")), ("not-json", ({}, "not-json"))):
            with self.subTest(source=source), patch.object(sys, "stdin", StringIO(source)):
                self.assertEqual(hook_io.read_hook_input(), expected)

    def test_root_cwd_and_scalar_helpers_keep_project_identity_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / ".git").mkdir()
            child = project / "src"
            child.mkdir()
            self.assertEqual(hook_io.root_from_payload({"cwd": str(child)}), str(project.resolve()))
            self.assertEqual(hook_io.root_from_payload({}, str(child)), str(child.resolve()))
            self.assertIsNone(hook_io.root_from_payload({"cwd": ""}))
            self.assertEqual(hook_io.cwd_from_payload({"cwd": str(child)}), str(child.resolve()))
            self.assertEqual(hook_io.cwd_from_payload({}, str(project)), str(project.resolve()))
            self.assertIsNone(hook_io.cwd_from_payload({}))

        payload = {"hook_event_name": "Stop", "first": " ", "second": " value "}
        self.assertEqual(hook_io.event_name(payload, "Fallback"), "Stop")
        self.assertEqual(hook_io.string_field(payload, "first", "second"), "value")
        self.assertEqual(hook_io.string_field(payload, "missing"), "")
        self.assertEqual(hook_io.first_present("", " answer ", "later"), "answer")
        self.assertEqual(hook_io.first_present("", " "), "")

    def test_message_and_json_compaction_handle_native_payload_shapes(self) -> None:
        messages = [
            {"role": "assistant", "content": " done "},
            {"role": "user", "content": [{"type": "text", "text": "one"}, {"text": "two"}]},
            {"role": "tool", "content": "ignored"},
            "ignored",
        ]
        self.assertEqual(hook_io.strings_from_messages(messages), ["done", "one\ntwo"])
        self.assertEqual(hook_io.strings_from_messages({}), [])
        self.assertEqual(hook_io.compact_json(None), "")
        self.assertEqual(hook_io.compact_json({"b": 2, "a": 1}), '{"a": 1, "b": 2}')
        self.assertEqual(hook_io.compact_json({1, 2}), "{1, 2}")
        self.assertTrue(hook_io.compact_json("abcdef", 3).endswith("[truncated]"))

    def test_event_accessors_and_output_helpers_use_normalized_event_data(self) -> None:
        payload = {
            "session_id": "session",
            "turn_id": "turn",
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "python -m pytest"},
            "tool_response": {"exit_code": 0, "stdout": "1 passed"},
        }
        self.assertEqual(hook_io.tool_command(payload), "python -m pytest")
        self.assertIn("1 passed", hook_io.tool_response_text(payload, json.dumps(payload)))
        self.assertTrue(hook_io.idempotency_key(payload, "PostToolUse"))
        self.assertIn("summary", hook_io.pre_compact_text({"summary": "keep summary"}, ""))
        self.assertEqual(hook_io.stop_text({"last_assistant_message": "complete"}, ""), "complete")

        patch_text = "*** Update File: one.py\n*** Add File: two.py\n*** Update File: one.py"
        self.assertEqual(hook_io.patch_targets(patch_text), ["one.py", "two.py"])
        self.assertEqual(
            hook_io.additional_context("SessionStart", "contract"),
            {
                "continue": True,
                "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "contract"},
            },
        )


if __name__ == "__main__":
    unittest.main()
