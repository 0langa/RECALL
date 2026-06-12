from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import memory_manager  # noqa: E402
import write_policy  # noqa: E402


class WritePolicyTests(unittest.TestCase):
    def test_low_signal_listing_command_is_ignored(self) -> None:
        decision = write_policy.classify_write(
            "commands",
            "Tool: Bash\nCommand: Get-ChildItem -Force\nResult: completed\nexit_code: 0",
            {"source": "post_tool_use", "command": "Get-ChildItem -Force"},
        )

        self.assertEqual(decision.action, "ignore")
        self.assertEqual(decision.reason, "low_signal_command")

    def test_exact_duplicate_updates_existing_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            metadata = memory_manager.build_card_metadata(
                source="post_tool_use",
                status="active",
                base={
                    "command": "python -m unittest",
                    "tool_name": "Bash",
                    "turn_id": "turn-1",
                    "auto_capture_policy": "test_result",
                },
            )
            first = memory_manager.add_record_if_useful("commands", "Command: python -m unittest\nOK", metadata, tmp)
            second = memory_manager.add_record_if_useful("commands", "Command: python -m unittest\nOK", metadata, tmp)
            result = memory_manager.query("python unittest", categories=["commands"], root=tmp)

            self.assertEqual(second["action"], "updated_existing")
            self.assertEqual(second["duplicate_id"], first["record"].id)
            self.assertEqual(len(result["results"]), 1)
            self.assertIn("last_confirmed", result["results"][0]["metadata"])

    def test_explicit_supersession_cue_marks_old_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = memory_manager.add_record(
                "decisions",
                "Use raw transcripts for memory.",
                memory_manager.build_card_metadata(status="active"),
                root=tmp,
            )
            new = memory_manager.add_record_if_useful(
                "decisions",
                f"Correction to memory #{old.id}: use structured cards.",
                memory_manager.build_card_metadata(
                    source="stop",
                    status="active",
                    base={"auto_capture_policy": "project_checkpoint"},
                ),
                tmp,
            )
            fetched_old = memory_manager.get_record(old.id, tmp)

            self.assertEqual(new["action"], "saved")
            self.assertEqual(fetched_old.metadata["status"], "superseded")
            self.assertEqual(fetched_old.metadata["superseded_by"], new["record"].id)


if __name__ == "__main__":
    unittest.main()
