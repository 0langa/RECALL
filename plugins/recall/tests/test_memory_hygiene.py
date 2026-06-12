from __future__ import annotations

import tempfile
import unittest

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import memory_hygiene  # noqa: E402
import memory_manager  # noqa: E402


class MemoryHygieneTests(unittest.TestCase):
    def test_exact_automatic_duplicate_updates_existing_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            metadata = memory_manager.build_card_metadata(
                source="post_tool_use",
                status="active",
                tags=["tool-use", "bash"],
                base={
                    "tool_name": "Bash",
                    "command": "python -m unittest",
                    "auto_capture_policy": "test_result",
                },
            )
            first = memory_manager.add_record_if_useful("commands", "Command: python -m unittest\nOK", metadata, tmp)
            second = memory_manager.add_record_if_useful("commands", "Command: python -m unittest\nOK", metadata, tmp)
            result = memory_manager.query("python unittest", categories=["commands"], root=tmp)

            self.assertEqual(first["action"], "saved")
            self.assertEqual(second["action"], "updated_existing")
            self.assertEqual(second["duplicate_id"], first["record"].id)
            self.assertEqual(len(result["results"]), 1)
            self.assertIn("last_confirmed", result["results"][0]["metadata"])

    def test_near_duplicate_is_saved_with_related_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            metadata = memory_manager.build_card_metadata(
                source="post_tool_use",
                status="active",
                tags=["tool-use", "bash"],
                base={
                    "tool_name": "Bash",
                    "command": "python -m unittest",
                    "auto_capture_policy": "test_result",
                },
            )
            first = memory_manager.add_record_if_useful(
                "commands",
                "Tool: Bash\nCommand: python -m unittest discover -s tests\nOK",
                metadata,
                tmp,
            )
            second = memory_manager.add_record_if_useful(
                "commands",
                "Tool: Bash\nCommand: python -m unittest discover -s tests\nRan 49 tests\nOK",
                metadata,
                tmp,
            )

            self.assertEqual(second["action"], "saved_related")
            self.assertEqual(second["record"].metadata["related_memory_id"], first["record"].id)
            self.assertGreaterEqual(
                second["record"].metadata["related_similarity"],
                memory_hygiene.NEAR_DUPLICATE_THRESHOLD,
            )

    def test_explicit_add_record_keeps_duplicate_user_memories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_manager.add_record("requirements", "The user explicitly repeated this requirement.", root=tmp)
            memory_manager.add_record("requirements", "The user explicitly repeated this requirement.", root=tmp)
            result = memory_manager.query("explicitly repeated requirement", categories=["requirements"], root=tmp)

            self.assertEqual(len(result["results"]), 2)


if __name__ == "__main__":
    unittest.main()
