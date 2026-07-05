"""Session-recency suppression: auto-injection skips cards written this session."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import memory_manager  # noqa: E402
import session_context  # noqa: E402


def seed(tmp: str, content: str, *, session_id: str | None) -> None:
    base = {"session_id": session_id} if session_id else {}
    memory_manager.add_record(
        "decisions",
        content,
        memory_manager.build_card_metadata(
            summary=content[:120], source="skill", status="active", importance=0.9, base=base,
        ),
        tmp,
    )


def run_prompt_hook(root: str, prompt: str, session_id: str) -> dict:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "hooks" / "scripts" / "prompt_inspector.py")],
        input=json.dumps({
            "cwd": root,
            "session_id": session_id,
            "turn_id": "t1",
            "hook_event_name": "UserPromptSubmit",
            "prompt": prompt,
        }),
        text=True,
        capture_output=True,
        check=True,
        cwd=ROOT,
    )
    return json.loads(completed.stdout)


class SessionRecencyTests(unittest.TestCase):
    def test_same_session_records_are_dropped_from_auto_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            seed(tmp, "Retry budget for outbound calls is capped at three attempts.", session_id="s1")

            same_session = session_context.build_session_context(
                tmp, "outbound retry budget", 8, exclude_session_id="s1",
            )
            self.assertEqual(same_session, "")

            next_session = session_context.build_session_context(
                tmp, "outbound retry budget", 8, exclude_session_id="s2",
            )
            self.assertIn("three attempts", next_session)

            unfiltered = session_context.build_session_context(tmp, "outbound retry budget", 8)
            self.assertIn("three attempts", unfiltered)

    def test_older_records_still_inject_while_fresh_ones_are_suppressed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            seed(tmp, "Exports use zstandard compression by accepted decision.", session_id="old-session")
            seed(tmp, "Retry budget is capped at three attempts per outbound call.", session_id="s1")
            context = session_context.build_session_context(
                tmp, "compression decision retry budget", 8, exclude_session_id="s1",
            )
            self.assertIn("zstandard", context)
            self.assertNotIn("three attempts", context)

    def test_prompt_hook_suppresses_same_session_but_not_next_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0.1.0'\n", encoding="utf-8")
            import config as recall_config

            recall_config.activate_project(tmp)
            seed(tmp, "The retry budget requirement caps outbound calls at three attempts.", session_id="s1")

            same = run_prompt_hook(tmp, "What is our retry budget requirement for outbound calls?", "s1")
            self.assertNotIn("hookSpecificOutput", same)

            fresh = run_prompt_hook(tmp, "What is our retry budget requirement for outbound calls?", "s2")
            context = (fresh.get("hookSpecificOutput") or {}).get("additionalContext", "")
            self.assertIn("three attempts", context)

    def test_explicit_recall_is_not_filtered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0.1.0'\n", encoding="utf-8")
            import config as recall_config

            recall_config.activate_project(tmp)
            seed(tmp, "The retry budget requirement caps outbound calls at three attempts.", session_id="s1")

            explicit = run_prompt_hook(tmp, "@recall what is our retry budget requirement?", "s1")
            context = (explicit.get("hookSpecificOutput") or {}).get("additionalContext", "")
            self.assertIn("three attempts", context)


if __name__ == "__main__":
    unittest.main()
