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

    def test_compact_results_drop_metadata_but_keep_trust_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            metadata = memory_manager.build_card_metadata(
                summary="SQLite is the default backend.",
                source="skill",
                status="active",
                base={"recall_fingerprint": "a" * 64, "origin_provider": "kimi"},
            )
            memory_manager.add_record("decisions", "Use SQLite as the default backend.", metadata, tmp)

            compact = retrieval.query("default backend", root=tmp, verbose=False)
            item = compact["results"][0]
            self.assertNotIn("metadata", item)
            self.assertEqual(item["flag"], "current")
            self.assertEqual(item["status"], "active")
            self.assertEqual(item["summary"], "SQLite is the default backend.")
            self.assertIn("health", compact)

            verbose = retrieval.query("default backend", root=tmp, verbose=True)
            self.assertIn("metadata", verbose["results"][0])
            self.assertEqual(verbose["results"][0]["metadata"]["origin_provider"], "kimi")

    def test_retrieval_aging_threshold_is_configurable(self) -> None:
        import config as recall_config

        with tempfile.TemporaryDirectory() as tmp:
            record = seed(tmp, "project_state", "Main branch is green and release tagged.", "active")
            aged_metadata = dict(record.metadata or {})
            aged_metadata["last_confirmed"] = (
                datetime.now(timezone.utc) - timedelta(days=10)
            ).isoformat(timespec="seconds")
            storage.update_record(
                record.id,
                category=record.category,
                content=record.content,
                metadata=aged_metadata,
                embedding=record.embedding,
                root=tmp,
            )

            # 10 days old: current under the 30-day default...
            default_response = retrieval.query("main branch release", root=tmp, limit=5)
            self.assertEqual(default_response["results"][0]["flag"], "current")

            # ...but needs verification once the project tightens the window.
            cfg = recall_config.load_config(tmp)
            cfg["staleness"]["retrieval_aging_days"] = 5
            recall_config.save_config(cfg, tmp)
            tight_response = retrieval.query("main branch release", root=tmp, limit=5)
            self.assertEqual(tight_response["results"][0]["flag"], "needs_verification")

    def test_raw_secrets_in_legacy_store_are_redacted_on_read(self) -> None:
        import sqlite3

        with tempfile.TemporaryDirectory() as tmp:
            record = seed(tmp, "commands", "Deploy authenticates against the staging service.", "active")
            secret_content = "Deploy uses api_key = sk-proj-LEGACYRAWSECRETABCDEFGHIJ to authenticate."
            connection = sqlite3.connect(storage.db_path(tmp))
            try:
                connection.execute("UPDATE memories SET content = ? WHERE id = ?", (secret_content, record.id))
                connection.commit()
            finally:
                connection.close()

            for verbose in (False, True):
                response = retrieval.query("deploy authenticate", root=tmp, limit=5, verbose=verbose)
                item = next(entry for entry in response["results"] if entry["id"] == record.id)
                self.assertNotIn("sk-proj-LEGACYRAWSECRET", item["content"])
                self.assertIn("[REDACTED]", item["content"])

    def test_current_only_store_reports_clean_health(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            seed(tmp, "commands", "Run unit tests with python -m pytest tests -q.", "active")
            response = retrieval.query("run unit tests", root=tmp, limit=5)
            self.assertEqual(response["health"]["flag_counts"], {"current": 1})
            self.assertNotIn("next_action", response["health"])


if __name__ == "__main__":
    unittest.main()
