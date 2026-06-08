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
                memory_manager.build_card_metadata(status="superseded", summary="Verbose older cards.", tags=["review"]),
                root=tmp,
            )
            memory_manager.merge_records(first.id, [second.id], tmp)

            review = memory_review.review_memory(tmp, statuses=["active"], limit=5)

            self.assertEqual(review["total"], 2)
            self.assertEqual(review["shown"], 1)
            self.assertEqual(review["status_counts"]["superseded"], 1)
            self.assertEqual(review["memories"][0]["id"], first.id)
            self.assertIn(second.id, review["memories"][0]["relationships"]["merged_from"])

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

            self.assertEqual(review["shown"], 1)
            self.assertEqual(review["memories"][0]["category"], "commands")


if __name__ == "__main__":
    unittest.main()
