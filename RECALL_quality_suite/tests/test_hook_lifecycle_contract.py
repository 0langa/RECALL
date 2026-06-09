from __future__ import annotations

import json
import unittest

from _harness import hook_cmd, memory_cmd, run_json, run_text, temp_project


class HookLifecycleContractTests(unittest.TestCase):
    def test_user_prompt_submit_saves_explicit_memory_cue_and_ignores_incidental_word(self) -> None:
        with temp_project() as project:
            positive = run_json(hook_cmd("prompt_inspector.py"), input_payload={
                "cwd": str(project),
                "hook_event_name": "UserPromptSubmit",
                "prompt": "remember this: prefer local-only memory storage",
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

    def test_malformed_json_is_safe_noop(self) -> None:
        with temp_project() as project:
            completed = run_text(hook_cmd("pre_compact.py"), input_payload=None, check=True)
            # Empty stdin is allowed to no-op.
            self.assertEqual(json.loads(completed.stdout), {"continue": True})

            malformed = run_text(hook_cmd("pre_compact.py"), input_payload=None, check=True)
            self.assertEqual(json.loads(malformed.stdout), {"continue": True})

    def test_post_tool_use_compacts_success_output_without_dumping_raw_listing(self) -> None:
        with temp_project() as project:
            output = run_json(hook_cmd("post_tool_use.py"), input_payload={
                "cwd": str(project),
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

            result = run_json(memory_cmd(project, "query", "unittest tests", "--category", "commands"))
            stored = result["results"][0]["content"]
            self.assertIn("python -m unittest discover -s tests", stored)
            self.assertIn("exit_code: 0", stored)
            self.assertNotIn("README.md", stored)
            self.assertNotIn("secrets.txt", stored)
            self.assertLess(len(stored), 250)

    def test_post_tool_use_failure_goes_to_debug_history_with_redaction(self) -> None:
        with temp_project() as project:
            output = run_json(hook_cmd("post_tool_use.py"), input_payload={
                "cwd": str(project),
                "hook_event_name": "PostToolUse",
                "turn_id": "quality-failure",
                "tool_name": "Bash",
                "tool_input": {"command": "deploy"},
                "tool_response": {"exit_code": 1, "stdout": "", "stderr": "failed with token=dummy-secret-value"},
            })
            self.assertTrue(output["continue"])

            result = run_json(memory_cmd(project, "query", "deploy token failure", "--category", "debug_history"))
            stored = result["results"][0]
            self.assertIn("deploy", stored["content"])
            self.assertIn("[REDACTED]", stored["content"])
            self.assertEqual(stored["metadata"]["turn_id"], "quality-failure")

    def test_precompact_stop_and_sessionstart_roundtrip_context(self) -> None:
        with temp_project() as project:
            pre = run_json(hook_cmd("pre_compact.py"), input_payload={
                "cwd": str(project),
                "hook_event_name": "PreCompact",
                "turn_id": "quality-precompact",
                "trigger": "manual",
                "summary": "Implemented hook payload hardening and verified smoke tests.",
            })
            self.assertTrue(pre["continue"])

            stop = run_json(hook_cmd("stop.py"), input_payload={
                "cwd": str(project),
                "hook_event_name": "Stop",
                "turn_id": "quality-stop",
                "last_assistant_message": "Completed RECALL quality suite integration work.",
            })
            self.assertTrue(stop["continue"])

            session = run_json(hook_cmd("session_start.py"), input_payload={
                "cwd": str(project),
                "hook_event_name": "SessionStart",
                "source": "startup",
                "query": "quality suite integration hook payload hardening",
            })
            self.assertTrue(session["continue"])
            context = session.get("hookSpecificOutput", {}).get("additionalContext", "")
            self.assertIn("RECALL", context)
            self.assertIn("quality", context.lower())


if __name__ == "__main__":
    unittest.main()
