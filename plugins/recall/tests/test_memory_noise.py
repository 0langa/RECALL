from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import memory_manager
import memory_noise


class MemoryNoiseTests(unittest.TestCase):
    def test_archive_noise_dry_run_matches_read_only_post_tool_use_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            noisy = memory_manager.add_record(
                "commands",
                "Tool: Bash Command: Get-Content README.md Result: completed",
                memory_manager.build_card_metadata(
                    summary="Bash result captured.",
                    source="post_tool_use",
                    status="active",
                ),
                tmp,
            )
            failure = memory_manager.add_record(
                "debug_history",
                "Tool: Bash Command: pytest Result: failed with AssertionError",
                memory_manager.build_card_metadata(
                    summary="Test failure captured.",
                    source="post_tool_use",
                    status="active",
                ),
                tmp,
            )

            report = memory_noise.archive_noise(tmp)

            self.assertEqual(report["mode"], "dry-run")
            self.assertEqual(report["matched"], 1)
            self.assertEqual(report["memories"][0]["id"], noisy.id)
            self.assertEqual(memory_manager.get_record(noisy.id, tmp).metadata["status"], "active")
            self.assertEqual(memory_manager.get_record(failure.id, tmp).metadata["status"], "active")

    def test_archive_noise_apply_archives_only_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            noisy = memory_manager.add_record(
                "commands",
                "Tool: Bash Command: git status --short Result: completed",
                memory_manager.build_card_metadata(
                    summary="Bash result captured.",
                    source="post_tool_use",
                    status="active",
                ),
                tmp,
            )
            useful = memory_manager.add_record(
                "project_state",
                "RECALL switched to explicit opt-in activation.",
                memory_manager.build_card_metadata(
                    summary="RECALL switched to explicit opt-in activation.",
                    source="finalizer",
                    status="active",
                ),
                tmp,
            )

            report = memory_noise.archive_noise(tmp, apply=True)

            self.assertEqual(report["mode"], "apply")
            self.assertEqual(report["matched"], 1)
            self.assertEqual(report["archived"], 1)
            self.assertEqual(memory_manager.get_record(noisy.id, tmp).metadata["status"], "archived")
            self.assertEqual(memory_manager.get_record(useful.id, tmp).metadata["status"], "active")


if __name__ == "__main__":
    unittest.main()
