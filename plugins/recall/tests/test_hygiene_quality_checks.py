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


F07_FROZEN_CLEAR_NOISE_CASES = (
    ("question", "decisions", "finalizer", "The capture option changed. What does that mean?"),
    ("uncertainty", "decisions", "finalizer", "Actually no idea whether the CI configuration still works."),
    ("attachment-wrapper", "decisions", "finalizer", "Files mentioned by the user: attachment.png. My request: audit this feature."),
    ("idea-request", "decisions", "finalizer", "Give me some ideas for a sample project for an interview."),
    ("job-request", "decisions", "finalizer", "Your job is to clean up a local workspace for this session."),
    ("one-time-output", "decisions", "finalizer", "Write the release notes for version 0.1.0 and use the requested markers."),
    ("speculation", "decisions", "finalizer", "I have a feeling that a recent package change caused this issue."),
    ("research-request", "decisions", "finalizer", "Please find out whether these migration files still serve a purpose."),
    ("task-request", "decisions", "finalizer", "Your task is to repair the paths in the migration tools."),
    ("session-control", "decisions", "finalizer", "Pause when convenient so I can restart the PC."),
    ("commit-permission", "decisions", "finalizer", "Actually commit only the files changed during this session."),
    ("delegated-wrapper", "decisions", "finalizer", "You are a delegated worker. Read-only analyze job: read README.md."),
    ("question-phrase", "decisions", "finalizer", "I would like to know what this actually means in this context."),
    ("raw-exploration", "debug_history", "finalizer", "Tool: Bash\nCommand: which compiler\nexit_code: 1\nCommand failed."),
    ("greeting", "project_state", "user_prompt", "Hello!"),
    ("thanks", "project_state", "user_prompt", "Thanks"),
    ("continue", "project_state", "user_prompt", "Continue"),
    ("acknowledgement", "project_state", "user_prompt", "Okay."),
    ("yes", "project_state", "user_prompt", "Yes"),
    ("no", "project_state", "user_prompt", "No"),
    ("go-on", "project_state", "user_prompt", "Go on"),
)


class HygieneQualityCheckTests(unittest.TestCase):
    def test_secret_repair_is_visible_before_duplicate_flood(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(12):
                seed_raw(tmp, "requirements", f"Release checks must pass before tagging variant {i}.",
                         {"source": "fixture", "status": "active"})
            bad = seed_raw(tmp, "decisions", "Legacy imported deployment credentials.",
                           {"source": "fixture", "status": "active"})
            import sqlite3
            connection = sqlite3.connect(storage.db_path(tmp))
            try:
                connection.execute("UPDATE memories SET content = ? WHERE id = ?",
                                   ("api_key=sk-proj-ABCDEFGHIJKLMNOPQRSTUVWX", bad.id))
                connection.commit()
            finally:
                connection.close()
            plan = memory_hygiene.hygiene_plan(tmp, output_limit=1, action_limit=1)
            self.assertEqual(plan["proposals"][0]["proposed_action"], "redact_secret")
            self.assertEqual(plan["operations"][0]["id"], bad.id)
            result = memory_hygiene.hygiene_apply(tmp, safe=True, plan=plan)
            self.assertEqual(result["applied_count"], 1)
            self.assertNotIn("sk-proj-", storage.get_record(bad.id, tmp).content)

    def test_clear_conversation_noise_is_review_only_and_failure_history_stays_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            noise = [seed_raw(tmp, "project_state", content, {"source": "user_prompt", "status": "active"})
                     for content in ("Hello!", "Thanks", "Continue", "What is SQLite?")]
            failure = seed_raw(tmp, "debug_history", "Traceback (most recent call last)\n" +
                               "\n".join(f"line {i}: assertion failed in module_{i}" for i in range(60)),
                               {"source": "post_tool_use", "status": "active"})
            plan = memory_hygiene.hygiene_plan(tmp)
            review = {p["id"] for p in plan["proposals"] if p["proposed_action"] == "review_noise"}
            self.assertEqual(review, {record.id for record in noise})
            memory_hygiene.hygiene_apply(tmp, safe=True, plan=plan)
            for record in [*noise, failure]:
                self.assertEqual(storage.get_record(record.id, tmp).metadata["status"], "active")

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

    def test_raw_failure_log_dump_requires_review_and_keeps_history(self) -> None:
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
            self.assertEqual(actions.get(dump.id), "review_failure_history")
            memory_hygiene.hygiene_apply(tmp, safe=True, plan=plan)
            self.assertEqual(storage.get_record(dump.id, tmp).metadata["status"], "active")

    def test_non_failure_output_dump_is_still_proposed_for_prune(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dump = seed_raw(tmp, "commands", "\n".join(f"row {i}: ordinary output entry repeated" for i in range(60)),
                            {"source": "fixture", "status": "active"})
            plan = memory_hygiene.hygiene_plan(tmp)
            self.assertIn(dump.id, [op["id"] for op in plan["operations"] if op["proposed_action"] == "prune"])

    def test_f07_frozen_noise_mapping_returns_21_review_only_proposals(self) -> None:
        self.assertEqual(len(F07_FROZEN_CLEAR_NOISE_CASES), 21)
        for case_id, category, source, text in F07_FROZEN_CLEAR_NOISE_CASES:
            with self.subTest(case_id=case_id):
                record = storage.MemoryRecord(1, category, utc(), text, {"source": source, "status": "active"})
                proposal = memory_hygiene._review_noise_proposal(record)
                self.assertIsNotNone(proposal)
                self.assertFalse(proposal.safe_to_apply)

    def test_interpreted_exploration_failure_is_not_noise(self) -> None:
        record = storage.MemoryRecord(1, "debug_history", utc(),
            "Tool: Bash\nCommand: which compiler\nCommand failed. Root cause: the SDK bin path was missing. "
            "Fixed by repairing the tool configuration.", {"source": "finalizer", "status": "active"})
        self.assertIsNone(memory_hygiene._review_noise_proposal(record))

    def test_unclassified_command_failure_does_not_become_stale(self) -> None:
        record = storage.MemoryRecord(
            1,
            "commands",
            utc(),
            "Tool: Bash\nCommand: rg release path\nCommand failed.",
            {"source": "fixture", "status": "active"},
        )
        self.assertIsNone(memory_hygiene._command_stale_proposal(record))

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

    def test_memory_restating_repo_docs_is_flagged_review_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            readme = Path(tmp) / "README.md"
            readme.write_text(
                "# Project\n\n"
                "RECALL stores decisions, constraints, debugging history, commands, requirements, "
                "risks, and custom categories in a project-local memory store so agents can recover "
                "useful context across sessions without hosted services.\n",
                encoding="utf-8",
            )
            duplicate = seed_raw(
                tmp,
                "architecture",
                "RECALL stores decisions constraints debugging history commands requirements risks "
                "and custom categories in a project-local memory store so agents recover useful "
                "context across sessions without hosted services.",
                {"source": "skill", "status": "active"},
            )
            original = seed_raw(
                tmp,
                "debug_history",
                "Windows sqlite temp cleanup fails unless the connection is closed explicitly before "
                "TemporaryDirectory teardown removes the folder.",
                {"source": "skill", "status": "active"},
            )
            plan = memory_hygiene.hygiene_plan(tmp)
            doc_proposals = {p["id"]: p for p in plan["proposals"] if p["proposed_action"] == "review_doc_duplicate"}
            self.assertIn(duplicate.id, doc_proposals)
            self.assertNotIn(original.id, doc_proposals)
            proposal = doc_proposals[duplicate.id]
            self.assertFalse(proposal["safe_to_apply"])
            self.assertEqual(proposal["details"]["doc_path"], "README.md")
            self.assertIn("README.md", proposal["reason"])

            # Review-only: safe apply must not archive the flagged memory.
            memory_hygiene.hygiene_apply(tmp, safe=True)
            self.assertEqual(storage.get_record(duplicate.id, tmp).metadata.get("status"), "active")

    def test_docs_corpus_covers_docs_directory_and_missing_docs_is_quiet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "docs"
            docs_dir.mkdir()
            (docs_dir / "release.md").write_text(
                "Release notes must stay in docs and list every packaging gate, smoke check, and "
                "quality suite result before any version tag is pushed to the marketplace.\n",
                encoding="utf-8",
            )
            duplicate = seed_raw(
                tmp,
                "requirements",
                "Release notes must stay in docs and list every packaging gate smoke check and "
                "quality suite result before any version tag is pushed to the marketplace.",
                {"source": "skill", "status": "active"},
            )
            plan = memory_hygiene.hygiene_plan(tmp)
            actions = {p["id"]: p["proposed_action"] for p in plan["proposals"]}
            self.assertEqual(actions.get(duplicate.id), "review_doc_duplicate")

        with tempfile.TemporaryDirectory() as tmp:
            lonely = seed_raw(
                tmp,
                "requirements",
                "Release notes must stay in docs and list every packaging gate smoke check and "
                "quality suite result before any version tag is pushed to the marketplace.",
                {"source": "skill", "status": "active"},
            )
            plan = memory_hygiene.hygiene_plan(tmp)
            self.assertFalse(
                [p for p in plan["proposals"] if p["id"] == lonely.id and p["proposed_action"] == "review_doc_duplicate"]
            )

    def test_snapshot_stale_days_is_configurable(self) -> None:
        import config as recall_config

        with tempfile.TemporaryDirectory() as tmp:
            snapshot = seed_raw(
                tmp,
                "project_state",
                "Release 1.2 is in progress on the main branch with all gates green.",
                {"source": "skill", "status": "active"},
                days_ago=10,
            )
            # 10 days old: fine under the 45-day default.
            plan = memory_hygiene.hygiene_plan(tmp)
            self.assertFalse([p for p in plan["proposals"] if p["id"] == snapshot.id and p["proposed_action"] == "stale"])

            cfg = recall_config.load_config(tmp)
            cfg["staleness"]["snapshot_stale_days"] = 5
            recall_config.save_config(cfg, tmp)
            plan = memory_hygiene.hygiene_plan(tmp)
            self.assertTrue([p for p in plan["proposals"] if p["id"] == snapshot.id and p["proposed_action"] == "stale"])

    def test_hygiene_scan_caps_listed_proposals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for index in range(25):
                seed_raw(
                    tmp,
                    "lessons_learned",
                    f"fixed the bug {index}",
                    {"source": "skill", "status": "active"},
                )
            scan = memory_hygiene.hygiene_scan(tmp)
            self.assertLessEqual(len(scan["proposals"]), memory_hygiene.SCAN_MAX_LISTED_PROPOSALS)
            self.assertGreater(scan["omitted_proposals"], 0)
            self.assertIn("hygiene-plan", scan["proposals_note"])
            # Counts and candidate ids stay complete despite the display cap.
            self.assertEqual(sum(scan["counts"].values()), len(scan["candidate_ids"]))
            self.assertGreaterEqual(len(scan["candidate_ids"]), 25)
            # The uncapped detail view still lists everything.
            plan = memory_hygiene.hygiene_plan(tmp)
            self.assertGreaterEqual(len(plan["proposals"]), 25)

    def test_explicit_declaration_preference_needs_no_decision_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            declared = seed_raw(
                tmp,
                "preferences",
                "User wants migration scripts reviewed as dry-run output before apply.",
                {
                    "source": "skill", "status": "active",
                    "preference_key": "migration.review_style",
                    "preference_evidence_type": "explicit_declaration",
                },
            )
            observed_without_decision = seed_raw(
                tmp,
                "preferences",
                "User seems to prefer squash merges based on recent activity.",
                {
                    "source": "skill", "status": "active",
                    "preference_key": "merge.style",
                    "preference_evidence_type": "accepted_edit",
                },
            )
            plan = memory_hygiene.hygiene_plan(tmp)
            flagged = {p["id"] for p in plan["proposals"] if p["proposed_action"] == "needs_confirmation"}
            self.assertNotIn(declared.id, flagged)
            self.assertIn(observed_without_decision.id, flagged)

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
