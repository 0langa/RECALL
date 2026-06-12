from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import memory_manager  # noqa: E402
import memory_review  # noqa: E402


class MemoryReviewTests(unittest.TestCase):
    def test_review_summarizes_counts_and_relationships(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = memory_manager.add_record(
                "requirements",
                "Memory cards must stay concise.",
                memory_manager.build_card_metadata(status="active", summary="Concise memory cards.", tags=["review"]),
                root=tmp,
            )
            second = memory_manager.add_record(
                "requirements",
                "Older memory cards were verbose.",
                memory_manager.build_card_metadata(
                    status="superseded",
                    summary="Verbose older cards.",
                    tags=["review"],
                ),
                root=tmp,
            )
            memory_manager.merge_records(first.id, [second.id], tmp)

            review = memory_review.review_memory(tmp, statuses=["active"], limit=5)

            self.assertEqual(review["total"], 2)
            self.assertEqual(review["matched"], 1)
            self.assertEqual(review["shown"], 1)
            self.assertEqual(review["status_counts"]["superseded"], 1)
            self.assertEqual(review["memories"][0]["id"], first.id)
            self.assertIn(second.id, review["memories"][0]["relationships"]["merged_from"])
            self.assertEqual(review["quality"]["relationship_record_count"], 2)
            self.assertGreaterEqual(review["quality"]["signal_to_noise_estimate"], 1.0)

    def test_review_filters_category_and_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_manager.add_record(
                "commands",
                "Run tests.",
                memory_manager.build_card_metadata(status="active", source="post_tool_use"),
                root=tmp,
            )
            memory_manager.add_record(
                "risks",
                "Payload drift.",
                memory_manager.build_card_metadata(status="open", source="skill"),
                root=tmp,
            )

            review = memory_review.review_memory(tmp, categories=["commands"], source="post_tool_use")

            self.assertEqual(review["matched"], 1)
            self.assertEqual(review["shown"], 1)
            self.assertEqual(review["memories"][0]["category"], "commands")
            self.assertEqual(review["filtered_source_counts"]["post_tool_use"], 1)

    def test_review_quality_surfaces_generic_summaries_and_noise_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            noisy = memory_manager.add_record(
                "commands",
                "Tool: Bash Command: Get-Content README.md Result: completed",
                memory_manager.build_card_metadata(
                    summary="Bash result captured.",
                    source="post_tool_use",
                    status="active",
                ),
                root=tmp,
            )
            memory_manager.add_record(
                "project_state",
                "RECALL should prefer high-value durable cards.",
                memory_manager.build_card_metadata(
                    summary="Prefer high-value durable cards.",
                    source="finalizer",
                    status="active",
                ),
                root=tmp,
            )

            review = memory_review.review_memory(tmp, limit=10)
            audit = memory_review.audit_memory(tmp, limit=10)

            self.assertEqual(review["quality"]["generic_summary_count"], 1)
            self.assertEqual(review["quality"]["active_noise_candidates"], 1)
            self.assertEqual(review["quality"]["source_kind_counts"]["automatic"], 1)
            self.assertEqual(review["quality"]["source_kind_counts"]["synthesized"], 1)
            self.assertEqual(review["quality"]["top_noisy_commands"][0]["pattern"], "Get-Content")
            self.assertEqual(review["quality"]["recommended_cleanup_command"], "python ./scripts/recall_skill.py archive-noise")
            self.assertTrue(review["memories"][0]["noise_candidate"] or review["memories"][1]["noise_candidate"])
            self.assertEqual(audit["shown"], 1)
            self.assertEqual(audit["noise_candidates"][0]["id"], noisy.id)


if __name__ == "__main__":
    unittest.main()
