"""Direct SessionStart tests for scope, activation, overview, and size limits."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "hooks" / "scripts"))

import config as recall_config
from hook_io import normalize_hook_event
import memory_manager
import session_start
import storage
import turn_policy


def run_session_start(payload: dict, *args: str) -> dict:
    stdout = StringIO()
    with (
        patch.object(sys, "argv", ["session_start.py", *args]),
        patch.object(session_start, "read_hook_input", return_value=(payload, json.dumps(payload))),
        redirect_stdout(stdout),
    ):
        session_start.main()
    return json.loads(stdout.getvalue())


class SessionStartTests(unittest.TestCase):
    def test_store_overview_is_empty_safe_and_category_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage.init_store(tmp)
            self.assertIn("store is empty", session_start.store_overview(tmp).lower())
            memory_manager.add_record("requirements", "Keep local storage.", root=tmp)
            memory_manager.add_record("requirements", "Keep provider parity.", root=tmp)
            memory_manager.add_record("risks", "Avoid stale memory.", root=tmp)
            overview = session_start.store_overview(tmp)
            self.assertIn("3 memories", overview)
            self.assertIn("requirements (2)", overview)
        with patch.object(session_start.storage, "iter_records", side_effect=RuntimeError("broken")):
            self.assertEqual(session_start.store_overview("ignored"), "")

    def test_main_stays_quiet_until_activation_then_emits_scoped_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = {"cwd": tmp, "hook_event_name": "SessionStart"}
            self.assertEqual(run_session_start(payload), {"continue": True})

            recall_config.activate_project(tmp, activated_by="session-start-test")
            unknown_scope = run_session_start(payload)
            unknown_text = unknown_scope["hookSpecificOutput"]["additionalContext"]
            self.assertIn("Instruction order", unknown_text)
            self.assertNotIn("store is empty", unknown_text.lower())

            normalize_hook_event(
                {"cwd": tmp, "session_id": "session", "turn_id": "turn", "prompt": "Continue normal work."},
                fallback_event="UserPromptSubmit",
            )
            known_scope = run_session_start(payload)
            self.assertIn("store is empty", known_scope["hookSpecificOutput"]["additionalContext"].lower())

    def test_main_keeps_closed_private_scope_and_contract_size_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recall_config.activate_project(tmp, activated_by="session-start-test")
            private = normalize_hook_event(
                {"cwd": tmp, "session_id": "private", "turn_id": "turn", "prompt": "Do not use memory for this task."},
                fallback_event="UserPromptSubmit",
            )
            turn_policy.finish_turn(tmp, private.session_id, private.turn_id, provider=private.provider)
            disabled = run_session_start({"cwd": tmp, "hook_event_name": "SessionStart"})
            self.assertEqual(disabled["reason"], "task_no_memory")

            normalize_hook_event(
                {"cwd": tmp, "session_id": "normal", "turn_id": "turn", "prompt": "Continue normal work."},
                fallback_event="UserPromptSubmit",
            )
            with patch.object(session_start.recall_contract, "compact_contract_text", return_value="x" * 2500):
                limited = run_session_start({"cwd": tmp, "hook_event_name": "SessionStart"})
            text = limited["hookSpecificOutput"]["additionalContext"]
            self.assertEqual(len(text), session_start.MAX_INJECTED_CHARS)
            self.assertTrue(text.endswith("…"))

            turn_policy.finish_turn(tmp, "normal", "turn")
            with patch.object(session_start, "store_overview") as overview:
                run_session_start({"cwd": tmp, "hook_event_name": "SessionStart"})
            overview.assert_not_called()


if __name__ == "__main__":
    unittest.main()
