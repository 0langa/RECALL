"""Retrieval health flags: stale/superseded/deprecated/conflicting marking."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import memory_manager  # noqa: E402
import retrieval  # noqa: E402
import storage  # noqa: E402


ALL_STATUSES = ["validated", "active", "open", "resolved", "stale", "superseded", "deprecated", "hypothesis"]


def seed(tmp: str, category: str, content: str, status: str, extra: dict | None = None):
    metadata = memory_manager.build_card_metadata(source="skill", status=status, base=extra or {})
    return memory_manager.add_record(category, content, metadata, tmp)


class RetrievalFlagTests(unittest.TestCase):
    def test_results_carry_health_flags_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            current = seed(tmp, "decisions", "Retrieval scoring uses local hash embeddings.", "active")
            stale = seed(tmp, "decisions", "Retrieval scoring uses remote embeddings.", "stale")
            superseded = seed(tmp, "decisions", "Retrieval scoring uses cosine only similarity.", "superseded")
            hypothesis = seed(tmp, "decisions", "Retrieval scoring may add rerank pass.", "hypothesis")

            response = retrieval.query(
                "retrieval scoring embeddings",
                root=tmp,
                statuses=ALL_STATUSES,
                limit=10,
            )
            flags = {item["id"]: item["flag"] for item in response["results"]}
            self.assertEqual(flags[current.id], "current")
            self.assertEqual(flags[stale.id], "stale")
            self.assertEqual(flags[superseded.id], "superseded")
            self.assertEqual(flags[hypothesis.id], "needs_verification")

            reasons = {item["id"]: item.get("flag_reason") for item in response["results"]}
            self.assertIsNone(reasons[current.id])
            self.assertTrue(reasons[stale.id])

            health = response["health"]
            self.assertGreaterEqual(health["flag_counts"].get("stale", 0), 1)
            self.assertIn("next_action", health)

    def test_conflicting_claims_are_marked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            seed(
                tmp,
                "project_state",
                "Latest score is 90.12.",
                "active",
                {"claim_key": "score", "claim_value": "90.12"},
            )
            seed(
                tmp,
                "project_state",
                "Latest score is 95.91.",
                "active",
                {"claim_key": "score", "claim_value": "95.91"},
            )
            response = retrieval.query("latest score", root=tmp, limit=10)
            conflicting = [item for item in response["results"] if item["flag"] == "conflicting"]
            self.assertEqual(len(conflicting), 2)
            self.assertIn("reconcile", response["health"]["next_action"])

    def test_old_snapshot_categories_need_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = seed(tmp, "project_state", "Main branch is clean and release is tagged.", "active")
            old_timestamp = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat(timespec="seconds")
            aged_metadata = dict(record.metadata or {})
            aged_metadata["last_confirmed"] = old_timestamp
            storage.update_record(
                record.id,
                category=record.category,
                content=record.content,
                metadata=aged_metadata,
                embedding=record.embedding,
                root=tmp,
            )
            response = retrieval.query(
                "main branch release state",
                root=tmp,
                statuses=ALL_STATUSES,
                limit=5,
            )
            item = next(entry for entry in response["results"] if entry["id"] == record.id)
            self.assertEqual(item["flag"], "needs_verification")
            self.assertIn("days old", item["flag_reason"])

    def test_current_only_store_reports_clean_health(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            seed(tmp, "commands", "Run unit tests with python -m pytest tests -q.", "active")
            response = retrieval.query("run unit tests", root=tmp, limit=5)
            self.assertEqual(response["health"]["flag_counts"], {"current": 1})
            self.assertNotIn("next_action", response["health"])


if __name__ == "__main__":
    unittest.main()
