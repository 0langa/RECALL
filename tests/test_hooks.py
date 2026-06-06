from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_hook(script: str, payload: dict) -> dict:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "hooks" / "scripts" / script)],
        input=json.dumps(payload),
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
