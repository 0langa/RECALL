from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_hook(script: str, payload: dict) -> dict:
    return run_hook_raw(script, json.dumps(payload))


def run_hook_raw(script: str, raw: str) -> dict:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "hooks" / "scripts" / script)],
        input=raw,
        text=True,
        capture_output=True,
        check=True,
        cwd=ROOT,
    )
    return json.loads(completed.stdout)


def query_memory(root: str, query: str, category: str) -> dict:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "memory_manager.py"),
            "--root",
            root,
            "query",
            query,
            "--category",
            category,
        ],
        text=True,
        capture_output=True,
        check=True,
        cwd=ROOT,
    )
    return json.loads(completed.stdout)


class HookTests(unittest.TestCase):
    def test_prompt_inspector_saves_remembered_preference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = run_hook(
                "prompt_inspector.py",
                {
                    "cwd": tmp,
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "remember this: prefer local-only memory storage",
                },
            )
            self.assertTrue(output["continue"])
            self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")

            query = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "memory_manager.py"),
                    "--root",
                    tmp,
                    "query",
                    "local memory",
                    "--category",
                    "preferences",
                    "--summary",
                ],
                text=True,
                capture_output=True,
                check=True,
                cwd=ROOT,
            )
            result = json.loads(query.stdout)
            self.assertIn("local-only", result["summary"])

    def test_prompt_inspector_ignores_incidental_remembered_word(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = run_hook(
                "prompt_inspector.py",
                {
                    "cwd": tmp,
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "Make a fake project so there is more that can actually be remembered.",
                },
            )
            self.assertEqual(output, {"continue": True})
            result = query_memory(tmp, "actually remembered", "preferences")
            self.assertEqual(result["results"], [])

    def test_session_start_injects_additional_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "memory_manager.py"),
                    "--root",
                    tmp,
                    "add",
                    "project_state",
                    "RECALL hook tests have a saved project state.",
                ],
                check=True,
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            output = run_hook(
                "session_start.py",
                {"cwd": tmp, "hook_event_name": "SessionStart", "source": "startup"},
            )
            self.assertTrue(output["continue"])
            self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "SessionStart")
            self.assertIn("RECALL hook tests", output["hookSpecificOutput"]["additionalContext"])

    def test_session_start_without_memories_is_quiet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = run_hook(
                "session_start.py",
                {"cwd": tmp, "hook_event_name": "SessionStart", "source": "startup"},
            )
            self.assertEqual(output, {"continue": True})

    def test_malformed_hook_json_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = run_hook_raw("pre_compact.py", '{"cwd": "' + tmp.replace("\\", "\\\\"))
            self.assertEqual(output, {"continue": True})
            result = query_memory(tmp, "cwd", "session_summaries")
            self.assertEqual(result["results"], [])

    def test_post_tool_use_stores_compact_successful_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = run_hook(
                "post_tool_use.py",
                {
                    "cwd": tmp,
                    "hook_event_name": "PostToolUse",
                    "tool_input": {"command": "python -m unittest discover -s tests"},
                    "tool_response": {
                        "exit_code": 0,
                        "stdout": "line\n" * 200 + "Ran 9 tests in 1.2s\nOK",
                        "stderr": "",
                    },
                },
            )
            self.assertTrue(output["continue"])
            query = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "memory_manager.py"),
                    "--root",
                    tmp,
                    "query",
                    "unittest command",
                    "--category",
                    "commands",
                ],
                text=True,
                capture_output=True,
                check=True,
                cwd=ROOT,
            )
            result = json.loads(query.stdout)
            stored = result["results"][0]["content"]
            self.assertIn("python -m unittest", stored)
            self.assertLess(len(stored), 900)

    def test_post_tool_use_successful_listing_avoids_raw_output_dump(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = run_hook(
                "post_tool_use.py",
                {
                    "cwd": tmp,
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "Get-ChildItem -Force"},
                    "tool_response": {
                        "exit_code": 0,
                        "stdout": "\x1b[32;1mMode\x1b[0m Name\n-a--- 1000 README.md\n-a--- 2000 secrets.txt",
                        "stderr": "",
                    },
                },
            )
            self.assertTrue(output["continue"])
            result = query_memory(tmp, "Get-ChildItem", "commands")
            stored = result["results"][0]["content"]
            self.assertIn("Get-ChildItem -Force", stored)
            self.assertIn("exit_code: 0", stored)
            self.assertNotIn("README.md", stored)
            self.assertNotIn("\x1b", stored)
            self.assertLess(len(stored), 220)

    def test_pre_compact_uses_event_fields_not_raw_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = run_hook(
                "pre_compact.py",
                {
                    "cwd": tmp,
                    "hook_event_name": "PreCompact",
                    "turn_id": "turn-123",
                    "trigger": "auto",
                    "summary": "Implemented the release smoke harness and verified plugin validation.",
                },
            )
            self.assertTrue(output["continue"])
            result = query_memory(tmp, "release smoke harness", "session_summaries")
            stored = result["results"][0]
            self.assertIn("release smoke harness", stored["content"])
            self.assertNotIn("hook_event_name", stored["content"])
            self.assertEqual(stored["metadata"]["trigger"], "auto")
            self.assertEqual(stored["metadata"]["turn_id"], "turn-123")

    def test_pre_compact_empty_payload_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = run_hook(
                "pre_compact.py",
                {"cwd": tmp, "hook_event_name": "PreCompact", "turn_id": "turn-empty", "trigger": "manual"},
            )
            self.assertEqual(output, {"continue": True})
            result = query_memory(tmp, "turn-empty", "session_summaries")
            self.assertEqual(result["results"], [])

    def test_stop_saves_last_assistant_message_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = run_hook(
                "stop.py",
                {
                    "cwd": tmp,
                    "hook_event_name": "Stop",
                    "turn_id": "turn-stop",
                    "last_assistant_message": "Completed Task 2 hook parsing and left storage healthy.",
                },
            )
            self.assertTrue(output["continue"])
            result = query_memory(tmp, "Task 2 hook parsing", "project_state")
            stored = result["results"][0]
            self.assertIn("hook parsing", stored["content"])
            self.assertNotIn("last_assistant_message", stored["content"])
            self.assertEqual(stored["metadata"]["turn_id"], "turn-stop")

    def test_stop_empty_last_message_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = run_hook(
                "stop.py",
                {"cwd": tmp, "hook_event_name": "Stop", "turn_id": "turn-stop", "last_assistant_message": None},
            )
            self.assertEqual(output, {"continue": True})
            result = query_memory(tmp, "turn-stop", "project_state")
            self.assertEqual(result["results"], [])

    def test_post_tool_use_stores_compact_bash_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = run_hook(
                "post_tool_use.py",
                {
                    "cwd": tmp,
                    "hook_event_name": "PostToolUse",
                    "turn_id": "turn-bash-failure",
                    "tool_name": "Bash",
                    "tool_input": {"command": "python -m unittest tests.test_missing"},
                    "tool_response": {
                        "exit_code": 1,
                        "stdout": "",
                        "stderr": "FAILED tests/test_missing.py::MissingTest - AssertionError: boom",
                    },
                },
            )
            self.assertTrue(output["continue"])
            result = query_memory(tmp, "MissingTest boom", "debug_history")
            stored = result["results"][0]
            self.assertIn("python -m unittest tests.test_missing", stored["content"])
            self.assertIn("AssertionError", stored["content"])
            self.assertEqual(stored["metadata"]["tool_name"], "Bash")
            self.assertEqual(stored["metadata"]["turn_id"], "turn-bash-failure")

    def test_post_tool_use_stores_apply_patch_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = run_hook(
                "post_tool_use.py",
                {
                    "cwd": tmp,
                    "hook_event_name": "PostToolUse",
                    "turn_id": "turn-patch",
                    "tool_name": "apply_patch",
                    "tool_input": {"command": "*** Begin Patch\n*** Update File: README.md\n@@\n+ok\n*** End Patch"},
                    "tool_response": {"success": True, "stdout": "Done!"},
                },
            )
            self.assertTrue(output["continue"])
            result = query_memory(tmp, "README apply_patch", "commands")
            stored = result["results"][0]
            self.assertIn("apply_patch", stored["content"])
            self.assertIn("README.md", stored["content"])
            self.assertLess(len(stored["content"]), 500)

    def test_post_tool_use_redacts_secret_like_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_hook(
                "post_tool_use.py",
                {
                    "cwd": tmp,
                    "hook_event_name": "PostToolUse",
                    "tool_input": {"command": "deploy"},
                    "tool_response": {"exit_code": 1, "stderr": "failed with token=dummy-secret-value"},
                },
            )
            query = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "memory_manager.py"),
                    "--root",
                    tmp,
                    "query",
                    "deploy failed token",
                    "--category",
                    "debug_history",
                ],
                text=True,
                capture_output=True,
                check=True,
                cwd=ROOT,
            )
            result = json.loads(query.stdout)
            self.assertIn("[REDACTED]", result["results"][0]["content"])


if __name__ == "__main__":
    unittest.main()
