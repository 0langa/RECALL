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


def runtime_events(root: str, session_id: str, turn_id: str) -> list[dict]:
    safe_session = session_id or "session"
    safe_turn = turn_id or "turn"
    path = Path(root) / ".codex_memory" / "runtime" / "turns" / safe_session / f"{safe_turn}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def activate_recall(root: str, session_id: str = "", turn_id: str = "") -> dict:
    return run_hook(
        "prompt_inspector.py",
        {
            "cwd": root,
            "session_id": session_id,
            "turn_id": turn_id,
            "hook_event_name": "UserPromptSubmit",
            "prompt": "[@recall](plugin://recall@recall-local) continue with RECALL active.",
        },
    )


class HookTests(unittest.TestCase):
    def test_prompt_inspector_saves_remembered_preference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = run_hook(
                "prompt_inspector.py",
                {
                    "cwd": tmp,
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "@recall remember this: prefer local-only memory storage",
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

    def test_prompt_invocation_injects_additional_context(self) -> None:
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
                    "--status",
                    "active",
                    "--summary",
                    "RECALL hook tests have a saved project state.",
                ],
                check=True,
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            output = run_hook(
                "prompt_inspector.py",
                {
                    "cwd": tmp,
                    "session_id": "session-context",
                    "turn_id": "turn-context",
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "@recall what is the current project state?",
                },
            )
            self.assertTrue(output["continue"])
            self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
            self.assertIn("RECALL hook tests", output["hookSpecificOutput"]["additionalContext"])

    def test_prompt_invocation_excludes_superseded_when_active_context_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "memory_manager.py"),
                    "--root",
                    tmp,
                    "add",
                    "requirements",
                    "Old startup requirement should not appear.",
                    "--summary",
                    "Old startup requirement.",
                    "--tag",
                    "startup",
                    "--status",
                    "superseded",
                ],
                check=True,
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "memory_manager.py"),
                    "--root",
                    tmp,
                    "add",
                    "requirements",
                    "Current startup requirement should appear.",
                    "--summary",
                    "Current startup requirement.",
                    "--tag",
                    "startup",
                    "--status",
                    "active",
                ],
                check=True,
                cwd=ROOT,
                capture_output=True,
                text=True,
            )

            output = run_hook(
                "prompt_inspector.py",
                {
                    "cwd": tmp,
                    "session_id": "session-startup",
                    "turn_id": "turn-startup",
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "@recall startup requirement",
                },
            )
            context = output["hookSpecificOutput"]["additionalContext"]

            self.assertIn("Curated RECALL project memory", context)
            self.assertIn("Current startup requirement", context)
            self.assertNotIn("Old startup requirement", context)

    def test_session_start_is_quiet_even_with_memories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "memory_manager.py"),
                    "--root",
                    tmp,
                    "add",
                    "project_state",
                    "SessionStart should not inject this automatically.",
                    "--summary",
                    "SessionStart should not inject this automatically.",
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
            self.assertEqual(output, {"continue": True})

    def test_recall_invocation_is_required_for_hook_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_hook(
                "post_tool_use.py",
                {
                    "cwd": tmp,
                    "session_id": "session-off",
                    "turn_id": "turn-off",
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "python -m unittest discover -s tests"},
                    "tool_response": {"exit_code": 0, "stdout": "Ran 9 tests in 1.2s\nOK", "stderr": ""},
                },
            )
            stop = run_hook(
                "stop.py",
                {
                    "cwd": tmp,
                    "session_id": "session-off",
                    "turn_id": "turn-off",
                    "hook_event_name": "Stop",
                    "last_assistant_message": "Completed tests and changed memory policy.",
                },
            )
            self.assertEqual(stop, {"continue": True})
            self.assertEqual(runtime_events(tmp, "session-off", "turn-off"), [])

    def test_malformed_hook_json_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = run_hook_raw("pre_compact.py", '{"cwd": "' + tmp.replace("\\", "\\\\"))
            self.assertEqual(output, {"continue": True})
            result = query_memory(tmp, "cwd", "session_summaries")
            self.assertEqual(result["results"], [])

    def test_post_tool_use_buffers_compact_successful_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            activate_recall(tmp, "session-test", "turn-test")
            output = run_hook(
                "post_tool_use.py",
                {
                    "cwd": tmp,
                    "session_id": "session-test",
                    "turn_id": "turn-test",
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "python -m unittest discover -s tests"},
                    "tool_response": {
                        "exit_code": 0,
                        "stdout": "line\n" * 200 + "Ran 9 tests in 1.2s\nOK",
                        "stderr": "",
                    },
                },
            )
            self.assertTrue(output["continue"])
            self.assertEqual(query_memory(tmp, "unittest command", "commands")["results"], [])
            events = runtime_events(tmp, "session-test", "turn-test")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["signal"], "test_pass")
            self.assertIn("python -m unittest", events[0]["command"])

    def test_post_tool_use_suppresses_exact_duplicate_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            activate_recall(tmp)
            payload = {
                "cwd": tmp,
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "python -m unittest discover -s tests"},
                "tool_response": {"exit_code": 0, "stdout": "Ran 49 tests in 1.0s\nOK", "stderr": ""},
            }
            first = run_hook("post_tool_use.py", payload)
            second = run_hook("post_tool_use.py", payload)
            events = runtime_events(tmp, "", "")

            self.assertTrue(first["continue"])
            self.assertEqual(second, {"continue": True})
            self.assertEqual(len(events), 2)
            self.assertEqual(query_memory(tmp, "python unittest", "commands")["results"], [])

    def test_post_tool_use_links_near_duplicate_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            activate_recall(tmp)
            base = {
                "cwd": tmp,
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "python -m unittest discover -s tests"},
            }
            run_hook(
                "post_tool_use.py",
                {**base, "tool_response": {"exit_code": 0, "stdout": "1 passed", "stderr": ""}},
            )
            run_hook(
                "post_tool_use.py",
                {**base, "tool_response": {"exit_code": 0, "stdout": "2 passed", "stderr": ""}},
            )
            events = runtime_events(tmp, "", "")

            self.assertEqual(len(events), 2)
            self.assertEqual(query_memory(tmp, "python unittest", "commands")["results"], [])

    def test_post_tool_use_successful_listing_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            activate_recall(tmp)
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
            self.assertEqual(output, {"continue": True})
            result = query_memory(tmp, "Get-ChildItem", "commands")
            self.assertEqual(result["results"], [])

    def test_pre_compact_uses_event_fields_not_raw_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            activate_recall(tmp, "", "turn-123")
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
            activate_recall(tmp, "", "turn-empty")
            output = run_hook(
                "pre_compact.py",
                {"cwd": tmp, "hook_event_name": "PreCompact", "turn_id": "turn-empty", "trigger": "manual"},
            )
            self.assertEqual(output, {"continue": True})
            result = query_memory(tmp, "turn-empty", "session_summaries")
            self.assertEqual(result["results"], [])

    def test_stop_dirty_buffer_requests_finalizer_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            activate_recall(tmp, "session-stop", "turn-stop")
            run_hook(
                "post_tool_use.py",
                {
                    "cwd": tmp,
                    "session_id": "session-stop",
                    "turn_id": "turn-stop",
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "python -m unittest discover -s tests"},
                    "tool_response": {"exit_code": 0, "stdout": "Ran 9 tests in 1.2s\nOK", "stderr": ""},
                },
            )
            output = run_hook(
                "stop.py",
                {
                    "cwd": tmp,
                    "session_id": "session-stop",
                    "hook_event_name": "Stop",
                    "turn_id": "turn-stop",
                    "last_assistant_message": "Completed Task 2 hook parsing and left storage healthy.",
                },
            )
            self.assertEqual(output["decision"], "block")
            self.assertIn("RECALL_FINALIZER_REQUEST", output["reason"])
            self.assertIn("save-turn-card", output["reason"])
            self.assertEqual(query_memory(tmp, "Task 2 hook parsing", "project_state")["results"], [])
            packet = Path(tmp) / ".codex_memory" / "runtime" / "finalizer_requests" / "session-stop-turn-stop.json"
            packet_json = json.loads(packet.read_text(encoding="utf-8"))
            self.assertIn("save-turn-card", packet_json["policy"]["allowed_commands"])

            second = run_hook(
                "stop.py",
                {
                    "cwd": tmp,
                    "session_id": "session-stop",
                    "hook_event_name": "Stop",
                    "turn_id": "turn-stop",
                    "last_assistant_message": "Completed Task 2 hook parsing and left storage healthy.",
                },
            )
            self.assertEqual(second, {"continue": True})

    def test_stop_active_finalizer_marks_finalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            activate_recall(tmp, "session-stop", "turn-stop")
            run_hook(
                "post_tool_use.py",
                {
                    "cwd": tmp,
                    "session_id": "session-stop",
                    "turn_id": "turn-stop",
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "python -m unittest discover -s tests"},
                    "tool_response": {"exit_code": 0, "stdout": "Ran 9 tests in 1.2s\nOK", "stderr": ""},
                },
            )
            run_hook(
                "stop.py",
                {
                    "cwd": tmp,
                    "session_id": "session-stop",
                    "hook_event_name": "Stop",
                    "turn_id": "turn-stop",
                    "last_assistant_message": "Completed tests.",
                },
            )
            output = run_hook(
                "stop.py",
                {
                    "cwd": tmp,
                    "session_id": "session-stop",
                    "hook_event_name": "Stop",
                    "turn_id": "turn-stop",
                    "stop_hook_active": True,
                    "last_assistant_message": "FINALIZER_CONTINUATION_VISIBLE_TEST",
                },
            )
            self.assertEqual(output, {"continue": True})
            packet = Path(tmp) / ".codex_memory" / "runtime" / "finalizer_requests" / "session-stop-turn-stop.json"
            self.assertEqual(json.loads(packet.read_text(encoding="utf-8"))["status"], "finalized")

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
            activate_recall(tmp, "", "turn-bash-failure")
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
            self.assertEqual(query_memory(tmp, "MissingTest boom", "debug_history")["results"], [])
            events = runtime_events(tmp, "", "turn-bash-failure")
            self.assertEqual(events[0]["signal"], "test_fail")
            self.assertIn("AssertionError", events[0]["details"])

    def test_post_tool_use_stores_apply_patch_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            activate_recall(tmp, "", "turn-patch")
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
            self.assertEqual(query_memory(tmp, "README apply_patch", "commands")["results"], [])
            events = runtime_events(tmp, "", "turn-patch")
            self.assertEqual(events[0]["signal"], "file_patch")
            self.assertIn("README.md", events[0]["details"])

    def test_post_tool_use_redacts_secret_like_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            activate_recall(tmp)
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
            self.assertEqual(result["results"], [])
            events = runtime_events(tmp, "", "")
            self.assertIn("[REDACTED]", events[0]["details"])


if __name__ == "__main__":
    unittest.main()
