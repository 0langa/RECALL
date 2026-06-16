from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from _harness import hook_cmd, memory_cmd, run_json, run_text, skill_cmd, temp_project


class HookLifecycleContractTests(unittest.TestCase):
    def runtime_events(self, project: Path, session_id: str, turn_id: str) -> list[dict]:
        path = project / ".codex_memory" / "runtime" / "turns" / (session_id or "session") / f"{turn_id or 'turn'}.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def activate_recall(self, project, session_id: str = "", turn_id: str = "") -> None:
        memory_init = memory_cmd(project, "init")
        subprocess.run(memory_init, text=True, capture_output=True, check=True)
        output = run_json(hook_cmd("prompt_inspector.py"), input_payload={
            "cwd": str(project),
            "session_id": session_id,
            "turn_id": turn_id,
            "hook_event_name": "UserPromptSubmit",
            "prompt": "[@recall](plugin://recall@recall-local) continue with RECALL active.",
        })
        self.assertTrue(output["continue"])

    def test_user_prompt_submit_saves_explicit_memory_cue_and_ignores_incidental_word(self) -> None:
        with temp_project() as project:
            initialized = run_json(hook_cmd("prompt_inspector.py"), input_payload={
                "cwd": str(project),
                "hook_event_name": "UserPromptSubmit",
                "prompt": "@recall initialize this project",
            })
            self.assertTrue(initialized["continue"])
            positive = run_json(hook_cmd("prompt_inspector.py"), input_payload={
                "cwd": str(project),
                "hook_event_name": "UserPromptSubmit",
                "prompt": "@recall remember this: prefer local-only memory storage",
            })
            self.assertTrue(positive["continue"])

            result = run_json(memory_cmd(project, "query", "local-only memory", "--category", "preferences", "--summary"))
            self.assertIn("local-only", result["summary"])

            negative = run_json(hook_cmd("prompt_inspector.py"), input_payload={
                "cwd": str(project),
                "hook_event_name": "UserPromptSubmit",
                "prompt": "Make a fake project so there is more that can actually be remembered.",
            })
            self.assertEqual(negative, {"continue": True})

            review = run_json(memory_cmd(project, "query", "fake project actually remembered", "--category", "preferences"))
            self.assertEqual(len(review["results"]), 1)
            self.assertNotIn("fake project", review["results"][0]["content"])

    def test_hooks_are_idle_until_recall_is_explicitly_invoked(self) -> None:
        with temp_project() as project:
            post = run_json(hook_cmd("post_tool_use.py"), input_payload={
                "cwd": str(project),
                "session_id": "idle-session",
                "turn_id": "idle-turn",
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "python -m unittest discover -s tests"},
                "tool_response": {"exit_code": 0, "stdout": "Ran 10 tests in 0.12s\nOK", "stderr": ""},
            })
            stop = run_json(hook_cmd("stop.py"), input_payload={
                "cwd": str(project),
                "session_id": "idle-session",
                "turn_id": "idle-turn",
                "hook_event_name": "Stop",
                "last_assistant_message": "Completed RECALL quality work.",
            })
            session = run_json(hook_cmd("session_start.py"), input_payload={
                "cwd": str(project),
                "hook_event_name": "SessionStart",
                "source": "startup",
                "query": "quality suite integration hook payload hardening",
            })

            self.assertEqual(post, {"continue": True})
            self.assertEqual(stop, {"continue": True})
            self.assertEqual(session, {"continue": True})
            result = run_json(memory_cmd(project, "query", "unittest quality work", "--category", "commands"))
            self.assertEqual(result["results"], [])

    def test_malformed_json_is_safe_noop(self) -> None:
        with temp_project() as project:
            completed = run_text(hook_cmd("pre_compact.py"), input_payload=None, check=True)
            # Empty stdin is allowed to no-op.
            self.assertEqual(json.loads(completed.stdout), {"continue": True})

            malformed = run_text(hook_cmd("pre_compact.py"), input_payload=None, check=True)
            self.assertEqual(json.loads(malformed.stdout), {"continue": True})

    def test_post_tool_use_compacts_success_output_without_dumping_raw_listing(self) -> None:
        with temp_project() as project:
            self.activate_recall(project, "quality-success", "quality-success-turn")
            output = run_json(hook_cmd("post_tool_use.py"), input_payload={
                "cwd": str(project),
                "session_id": "quality-success",
                "turn_id": "quality-success-turn",
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "python -m unittest discover -s tests"},
                "tool_response": {
                    "exit_code": 0,
                    "stdout": "Ran 10 tests in 0.12s\n0 failures\nFiles checked: README.md\nsecrets.txt",
                    "stderr": "",
                },
            })
            self.assertTrue(output["continue"])
            result = run_json(memory_cmd(project, "query", "unit test validation", "--category", "commands"))
            self.assertEqual(result["results"], [])
            events = self.runtime_events(project, "quality-success", "quality-success-turn")
            self.assertEqual(len(events), 1)
            self.assertIn("Ran 10 tests", events[0]["summary"])
            self.assertNotIn("README.md", events[0]["details"])
            self.assertNotIn("secrets.txt", events[0]["details"])

    def test_post_tool_use_failure_goes_to_debug_history_with_redaction(self) -> None:
        with temp_project() as project:
            self.activate_recall(project, "", "quality-failure")
            output = run_json(hook_cmd("post_tool_use.py"), input_payload={
                "cwd": str(project),
                "hook_event_name": "PostToolUse",
                "turn_id": "quality-failure",
                "tool_name": "Bash",
                "tool_input": {"command": "deploy"},
                "tool_response": {"exit_code": 1, "stdout": "", "stderr": "failed with token=dummy-secret-value"},
            })
            self.assertTrue(output["continue"])
            result = run_json(memory_cmd(project, "query", "deploy failure", "--category", "debug_history"))
            self.assertEqual(result["results"], [])
            events = self.runtime_events(project, "", "quality-failure")
            self.assertEqual(len(events), 1)
            self.assertIn("[REDACTED]", events[0]["details"])

    def test_precompact_stop_and_sessionstart_roundtrip_context(self) -> None:
        with temp_project() as project:
            run_text(memory_cmd(project, "init"))
            run_json(skill_cmd(project, "configure-capture", "standard"))
            self.activate_recall(project, "", "quality-precompact")
            pre = run_json(hook_cmd("pre_compact.py"), input_payload={
                "cwd": str(project),
                "hook_event_name": "PreCompact",
                "turn_id": "quality-precompact",
                "trigger": "manual",
                "summary": "Implemented hook payload hardening and verified smoke tests.",
            })
            self.assertTrue(pre["continue"])

            activated = run_json(hook_cmd("prompt_inspector.py"), input_payload={
                "cwd": str(project),
                "hook_event_name": "UserPromptSubmit",
                "turn_id": "quality-stop",
                "prompt": "@recall You must preserve quality suite integration hook payload hardening context.",
            })
            self.assertTrue(activated["continue"])
            stop = run_json(hook_cmd("stop.py"), input_payload={
                "cwd": str(project),
                "hook_event_name": "Stop",
                "turn_id": "quality-stop",
                "last_assistant_message": "Completed RECALL quality suite integration work.",
            })
            self.assertTrue(stop["continue"])
            self.assertNotIn("decision", stop)
            self.assertNotIn("reason", stop)
            self.assertNotIn("RECALL_FINALIZER_REQUEST", json.dumps(stop))
            self.assertEqual(self.runtime_events(project, "", "quality-stop"), [])

            direct = run_json(memory_cmd(
                project,
                "query",
                "quality suite integration hook payload hardening",
                "--category",
                "requirements",
            ))
            self.assertEqual(len(direct["results"]), 1)
            self.assertEqual(direct["results"][0]["metadata"]["status"], "validated")


if __name__ == "__main__":
    unittest.main()
