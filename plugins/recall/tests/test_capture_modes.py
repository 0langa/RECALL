"""capture_mode enforcement: standard / minimal / manual / off.

The mode contract lives in capture_policy.py and is enforced inside the hook
scripts, not in agent instructions. Retrieval stays governed by recall_mode.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import capture_policy  # noqa: E402
import config as recall_config  # noqa: E402


FAILING_TOOL_OUTPUT = "Traceback (most recent call last)\nAssertionError: expected 3 got 2\nexit_code: 1"


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


def run_manager(root: str, *args: str) -> dict:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "memory_manager.py"), "--root", root, *args],
        text=True,
        capture_output=True,
        check=True,
        cwd=ROOT,
    )
    return json.loads(completed.stdout)


def activate(tmp: str, mode: str) -> None:
    Path(tmp, "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0.1.0'\n", encoding="utf-8")
    recall_config.activate_project(tmp)
    recall_config.set_capture_mode(mode, tmp)


class ToolCaptureModeTests(unittest.TestCase):
    def classify(self, mode: str):
        return capture_policy.classify_tool_capture(
            root=None,
            payload={},
            tool_name="Bash",
            command="python -m pytest tests -q",
            content=FAILING_TOOL_OUTPUT,
            mode=mode,
        )

    def test_standard_captures_per_tool_evidence(self) -> None:
        decision = self.classify("standard")
        self.assertIsNotNone(decision)
        self.assertEqual(decision.category, "debug_history")

    def test_minimal_manual_and_off_skip_per_tool_evidence(self) -> None:
        for mode in ("minimal", "manual", "off"):
            self.assertIsNone(self.classify(mode), f"mode={mode} must not buffer per-tool evidence")


class SessionSummaryModeTests(unittest.TestCase):
    def test_precompact_summary_runs_in_standard_and_minimal_only(self) -> None:
        expectations = {"standard": True, "minimal": True, "manual": False, "off": False}
        for mode, expected in expectations.items():
            with tempfile.TemporaryDirectory() as tmp:
                activate(tmp, mode)
                self.assertEqual(
                    capture_policy.should_store_precompact(tmp),
                    expected,
                    f"mode={mode}",
                )

    def test_stop_notes_follow_auto_capture_modes(self) -> None:
        note = "Decision: keep the storage backend on SQLite for concurrency."
        for mode, expected in {"standard": True, "minimal": True, "manual": False, "off": False}.items():
            with tempfile.TemporaryDirectory() as tmp:
                activate(tmp, mode)
                self.assertEqual(
                    capture_policy.should_store_stop_note(tmp, note),
                    expected,
                    f"mode={mode}",
                )


class ExplicitCueModeTests(unittest.TestCase):
    def test_off_blocks_explicit_remember_and_explains_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            activate(tmp, "off")
            output = run_hook(
                "prompt_inspector.py",
                {
                    "cwd": tmp,
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "@recall remember this: prefer tabs over spaces",
                },
            )
            context = output["hookSpecificOutput"]["additionalContext"]
            self.assertIn("capture is off", context)
            self.assertIn("configure-capture", context)
            result = run_manager(tmp, "query", "tabs over spaces", "--category", "preferences")
            self.assertEqual(result["results"], [])

    def test_manual_still_saves_explicit_remember(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            activate(tmp, "manual")
            output = run_hook(
                "prompt_inspector.py",
                {
                    "cwd": tmp,
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "@recall remember this: requirements: Releases require green quality gates.",
                },
            )
            self.assertIn("saved memory", output["hookSpecificOutput"]["additionalContext"])
            result = run_manager(tmp, "query", "green quality gates", "--category", "requirements")
            self.assertEqual(len(result["results"]), 1)

    def test_explicit_capture_allowed_matches_contract(self) -> None:
        for mode, expected in {"standard": True, "minimal": True, "manual": True, "off": False}.items():
            with tempfile.TemporaryDirectory() as tmp:
                activate(tmp, mode)
                self.assertEqual(capture_policy.explicit_capture_allowed(tmp), expected, f"mode={mode}")


class PromptSignalModeTests(unittest.TestCase):
    def test_manual_mode_does_not_buffer_automatic_prompt_signals(self) -> None:
        prompt = "The retry logic must never exceed three attempts; that is a hard requirement."
        for mode, expects_events in {"standard": True, "manual": False}.items():
            with tempfile.TemporaryDirectory() as tmp:
                activate(tmp, mode)
                run_hook(
                    "prompt_inspector.py",
                    {
                        "cwd": tmp,
                        "session_id": "s1",
                        "turn_id": "t1",
                        "hook_event_name": "UserPromptSubmit",
                        "prompt": prompt,
                    },
                )
                import turn_buffer

                events = turn_buffer.load_events(tmp, "s1", "t1")
                durable = [e for e in events if e.get("durable_candidate")]
                if expects_events:
                    self.assertTrue(durable, f"mode={mode} should buffer prompt signals")
                else:
                    self.assertFalse(durable, f"mode={mode} must not buffer prompt signals")


if __name__ == "__main__":
    unittest.main()
