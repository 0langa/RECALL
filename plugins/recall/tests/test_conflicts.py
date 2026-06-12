from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import memory_manager  # noqa: E402
import memory_review  # noqa: E402
from services import lifecycle_service  # noqa: E402


class ConflictGovernanceTests(unittest.TestCase):
    def test_confirmations_promote_active_memory_to_validated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = memory_manager.add_record(
                "decisions",
                "SQLite is the default backend.",
                memory_manager.build_card_metadata(status="active", confidence=0.9),
                tmp,
            )
            memory_manager.confirm_record(record.id, tmp, "session-a")
            confirmed = memory_manager.confirm_record(record.id, tmp, "session-b")
            self.assertEqual(confirmed.metadata["status"], "validated")
            self.assertGreaterEqual(confirmed.metadata["trust"], 0.85)

    def test_conflicting_claim_slots_form_review_cluster(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = memory_manager.add_record(
                "decisions",
                "Capture mode is standard.",
                memory_manager.build_card_metadata(
                    status="active",
                    base={"claim_key": "capture_mode", "claim_value": "standard"},
                ),
                tmp,
            )
            second = memory_manager.add_record(
                "decisions",
                "Capture mode is off.",
                memory_manager.build_card_metadata(
                    status="active",
                    base={"claim_key": "capture_mode", "claim_value": "off"},
                ),
                tmp,
            )
            clusters = lifecycle_service.find_conflicts(tmp)
            self.assertEqual(len(clusters), 1)
            self.assertEqual(set(clusters[0]["record_ids"]), {first.id, second.id})
            self.assertEqual(clusters[0]["resolution"], "review_required")

    def test_two_contradictory_claims_cannot_both_be_validated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = memory_manager.add_record(
                "requirements",
                "Python 3.11 is required.",
                memory_manager.build_card_metadata(
                    status="active",
                    base={"claim_key": "python_version", "claim_value": "3.11"},
                ),
                tmp,
            )
            second = memory_manager.add_record(
                "requirements",
                "Python 3.12 is required.",
                memory_manager.build_card_metadata(
                    status="active",
                    base={"claim_key": "python_version", "claim_value": "3.12"},
                ),
                tmp,
            )
            lifecycle_service.promote(first.id, tmp)
            with self.assertRaisesRegex(ValueError, "contradicts validated memory"):
                lifecycle_service.promote(second.id, tmp)

    def test_conflict_resolution_supersedes_losers_and_audit_reports_clusters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = memory_manager.add_record(
                "decisions",
                "Use JSONL by default.",
                memory_manager.build_card_metadata(
                    status="active",
                    base={"claim_key": "storage_backend", "claim_value": "jsonl"},
                ),
                tmp,
            )
            current = memory_manager.add_record(
                "decisions",
                "Use SQLite by default.",
                memory_manager.build_card_metadata(
                    status="active",
                    base={"claim_key": "storage_backend", "claim_value": "sqlite"},
                ),
                tmp,
            )
            before = memory_review.audit_memory(tmp)
            result = lifecycle_service.resolve_conflict(current.id, [old.id], tmp, "SQLite is current.")
            after = memory_review.audit_memory(tmp)
            self.assertEqual(len(before["conflict_clusters"]), 1)
            self.assertEqual(result["winner"].metadata["status"], "validated")
            self.assertEqual(result["losers"][0].metadata["status"], "superseded")
            self.assertEqual(after["conflict_clusters"], [])


if __name__ == "__main__":
    unittest.main()
