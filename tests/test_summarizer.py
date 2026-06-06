from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from summarizer import summarize_records, summarize_texts  # noqa: E402


class SummarizerTests(unittest.TestCase):
    def test_summarize_texts_respects_token_budget_hard_cap(self) -> None:
        summary = summarize_texts(
            [
                "Alpha beta gamma delta epsilon zeta eta theta.",
                "Important migration detail must survive.",
            ],
            token_budget=6,
        )
        self.assertLessEqual(len(summary.split()), 6)

    def test_summarize_records_preserves_category_and_timestamp(self) -> None:
        records = [
            {
                "category": "requirements",
                "timestamp": "2026-06-06T01:00:00+00:00",
                "content": "RECALL must keep injected summaries traceable.",
            }
        ]
        summary = summarize_records(records, token_budget=30)
        self.assertIn("[requirements @ 2026-06-06T01:00:00+00:00]", summary)
        self.assertIn("traceable", summary)


if __name__ == "__main__":
    unittest.main()
