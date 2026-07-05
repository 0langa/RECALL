"""Hygiene detection of secrets, raw logs, vague cards, aged snapshots, metadata gaps.

Fixtures intentionally seed BAD memories through the raw storage layer (which
only redacts on the normal write path) to simulate legacy or corrupted stores.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from embedder import embed  # noqa: E402
import memory_hygiene  # noqa: E402
import memory_manager  # noqa: E402
import storage  # noqa: E402


def utc(days_ago: float = 0.0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(timespec="seconds")


def seed_raw(tmp: str, category: str, content: str, metadata: dict, days_ago: float = 0.0):
    """Insert without engine-side redaction/policy, like a legacy import."""
    return storage.add_record(category, utc(days_ago), content, metadata, embed(content), tmp)


class HygieneQualityCheckTests(unittest.TestCase):
    def test_secret_shaped_memory_is_flagged_and_safe_apply_redacts_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = seed_raw(
                tmp,
                "commands",
                "Deploy authenticates against the staging service.",
                {"source": "skill", "status": "active"},
            )
            # The write path always redacts; emulate a pre-RECALL legacy store
            # that already contains a raw secret by editing SQLite directly.
            import sqlite3

            secret_content = "Deploy uses api_key = sk-proj-ABCDEFGHIJKLMNOPQRSTUVWX to authenticate."
            connection = sqlite3.connect(storage.db_path(tmp))
            try:
                connection.execute(
                    "UPDATE memories SET content = ? WHERE id = ?",
                    (secret_content, bad.id),
                )
                connection.commit()
            finally:
                connection.close()
            plan = memory_hygiene.hygiene_plan(tmp)
            secret_proposals = [p for p in plan["proposals"] if p["proposed_action"] == "redact_secret"]
            self.assertEqual(len(secret_proposals), 1)
            self.assertEqual(secret_proposals[0]["id"], bad.id)
            self.assertTrue(secret_proposals[0]["safe_to_apply"])

            scan = memory_hygiene.hygiene_scan(tmp)
            self.assertIn("secret-shaped", scan["next_action"])

            memory_hygiene.hygiene_apply(tmp, safe=True)
            repaired = storage.get_record(bad.id, tmp)
            self.assertNotIn("sk-proj-", repaired.content)
            self.assertIn("[REDACTED]", repaired.content)
            self.assertIn("redacted_at", repaired.metadata)

            # After repair the store no longer proposes secret redaction.
            follow_up = memory_hygiene.hygiene_plan(tmp)
            self.assertFalse([p for p in follow_up["proposals"] if p["proposed_action"] == "redact_secret"])

    def test_raw_log_dump_is_proposed_for_prune(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_lines = "\n".join(f"line {i}: assertion failed in module_{i}" for i in range(60))
            dump = seed_raw(
                tmp,
                "debug_history",
                "Traceback (most recent call last)\n" + log_lines,
                {"source": "skill", "status": "active"},
            )
            plan = memory_hygiene.hygiene_plan(tmp)
            actions = {p["id"]: p["proposed_action"] for p in plan["proposals"]}
            self.assertEqual(actions.get(dump.id), "prune")

    def test_vague_memory_requires_review_not_auto_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vague = seed_raw(tmp, "lessons_learned", "fixed the bug", {"source": "skill", "status": "active"})
            plan = memory_hygiene.hygiene_plan(tmp)
            proposal = next(p for p in plan["proposals"] if p["id"] == vague.id and p["proposed_action"] == "review_vague")
            self.assertFalse(proposal["safe_to_apply"])
            self.assertIn(vague.id, plan["requires_confirmation"])

    def test_aged_project_state_snapshot_goes_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = seed_raw(
                tmp,
                "project_state",
                "Release 0.9 in progress on branch feature/x; tests failing on Windows.",
                {"source": "skill", "status": "active"},
                days_ago=120,
            )
            fresh = seed_raw(
                tmp,
                "project_state",
                "Release 1.2 shipped; main green on all platforms.",
                {"source": "skill", "status": "active"},
            )
            plan = memory_hygiene.hygiene_plan(tmp)
            stale_ids = {p["id"] for p in plan["proposals"] if p["proposed_action"] == "stale"}
            self.assertIn(snapshot.id, stale_ids)
            self.assertNotIn(fresh.id, stale_ids)

            memory_hygiene.hygiene_apply(tmp, safe=True)
            self.assertEqual(storage.get_record(snapshot.id, tmp).metadata.get("status"), "stale")
            self.assertEqual(storage.get_record(fresh.id, tmp).metadata.get("status"), "active")

    def test_missing_provenance_metadata_is_flagged_for_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bare = seed_raw(tmp, "decisions", "Use SQLite WAL mode for concurrent hook access safety.", {})
            plan = memory_hygiene.hygiene_plan(tmp)
            proposal = next(
                p for p in plan["proposals"] if p["id"] == bare.id and p["proposed_action"] == "review_metadata"
            )
            self.assertFalse(proposal["safe_to_apply"])
            self.assertIn("source", proposal["reason"])

    def test_good_store_produces_no_proposals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_manager.add_record(
                "commands",
                "Unit tests: python -m pytest tests -q, takes about two minutes.",
                memory_manager.build_card_metadata(
                    summary="Verified unit test command.",
                    source="skill",
                    status="active",
                    importance=0.7,
                ),
                tmp,
            )
            plan = memory_hygiene.hygiene_plan(tmp)
            self.assertEqual(plan["proposals"], [])


if __name__ == "__main__":
    unittest.main()
