from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import config as recall_config  # noqa: E402
import index_store  # noqa: E402
import memory_manager  # noqa: E402
import memory_hygiene  # noqa: E402
import memory_review  # noqa: E402


class MemoryLifecycleTests(unittest.TestCase):
    def test_edit_redacts_legacy_confirmation_history(self) -> None:
        for backend in ("sqlite", "jsonl"):
            with self.subTest(backend=backend), tempfile.TemporaryDirectory() as tmp:
                cfg = recall_config.default_config()
                cfg["backend"] = backend
                recall_config.save_config(cfg, tmp)
                record = memory_manager.add_record("requirements", "Release notes live in docs/old.md.", root=tmp)
                # Simulate unredacted legacy evidence; the edit must still apply
                # the write boundary when moving it into historical metadata.
                secret = "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWX"
                memory_manager.update_record_metadata(record.id, {
                    "status": "validated", "confirmation_sessions": [secret], "confirmed_count": 1,
                }, tmp)
                edited = memory_manager.edit_record(record.id, tmp, content="Release notes live in docs/new.md.")
                self.assertNotIn(secret, str(edited.metadata))
                self.assertIn("verification_history", edited.metadata)

    def test_edit_record_clears_claim_for_content_change(self) -> None:
        for backend in ("sqlite", "jsonl"):
            with tempfile.TemporaryDirectory() as tmp:
                if backend == "jsonl":
                    recall_config.ensure_config(tmp)
                    cfg = recall_config.load_config(tmp)
                    cfg["backend"] = "jsonl"
                    recall_config.save_config(cfg, tmp)

                record = memory_manager.add_record(
                    "requirements",
                    "Release notes path is docs/old.md.",
                    metadata=memory_manager.build_card_metadata(
                        source="fixture",
                        status="active",
                        base={"claim_key": "release_notes.path", "claim_value": "docs/old.md"},
                    ),
                    root=tmp,
                )
                edited = memory_manager.edit_record(
                    record.id,
                    tmp,
                    content="Release notes path is docs/new.md.",
                    summary="Release notes moved to docs/new.md.",
                    status="validated",
                )
                index_store.rebuild(tmp)
                reopened = memory_manager.get_record(record.id, tmp)
                old_results = memory_manager.query(
                    "Release notes path is docs/old.md",
                    categories=["requirements"],
                    root=tmp,
                )["results"]
                new_results = memory_manager.query(
                    "Release notes path is docs/new.md",
                    categories=["requirements"],
                    root=tmp,
                )["results"]
                review = memory_review.review_memory(tmp, categories=["requirements"])
                report = memory_hygiene.reconcile_current_truth(tmp, claim_key="release_notes.path")

                self.assertEqual(edited.id, record.id)
                self.assertIsNotNone(reopened)
                assert reopened is not None
                self.assertEqual(reopened.content, "Release notes path is docs/new.md.")
                self.assertEqual(edited.metadata.get("status"), "active")
                self.assertNotIn("claim_key", edited.metadata)
                self.assertNotIn("claim_value", edited.metadata)
                self.assertTrue(all(item["content"] != "Release notes path is docs/old.md." for item in old_results))
                self.assertEqual(new_results[0]["id"], record.id)
                self.assertEqual(review["memories"][0]["summary"], "Release notes moved to docs/new.md.")
                self.assertEqual(report["proposals"], [])

    def test_edit_record_preserves_claim_on_tags_only_edit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = memory_manager.add_record(
                "requirements",
                "Release notes path is docs/new.md.",
                metadata=memory_manager.build_card_metadata(
                    source="fixture",
                    status="validated",
                    base={
                        "claim_key": "release_notes.path",
                        "claim_value": "docs/new.md",
                        "confirmed_count": 2,
                        "last_confirmed": "2026-09-10T12:00:00+00:00",
                    },
                ),
                root=tmp,
            )
            edited = memory_manager.edit_record(record.id, tmp, tags=["release-notes"])

            self.assertEqual(edited.id, record.id)
            self.assertEqual(edited.metadata.get("claim_key"), "release_notes.path")
            self.assertEqual(edited.metadata.get("claim_value"), "docs/new.md")
            self.assertEqual(edited.metadata.get("confirmed_count"), 2)
            self.assertEqual(edited.metadata.get("last_confirmed"), "2026-09-10T12:00:00+00:00")
            self.assertEqual(edited.metadata.get("tags"), ["release-notes"])

    def test_edit_record_invalidates_old_verification_for_semantic_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = memory_manager.add_record(
                "requirements",
                "Release notes path is docs/old.md.",
                metadata=memory_manager.build_card_metadata(
                    source="fixture",
                    status="validated",
                    base={
                        "claim_key": "release_notes.path",
                        "claim_value": "docs/old.md",
                        "confirmed_count": 3,
                        "last_confirmed": "2026-09-10T12:00:00+00:00",
                    },
                ),
                root=tmp,
            )

            edited = memory_manager.edit_record(
                record.id,
                tmp,
                summary="Release notes path needs independent re-verification.",
            )

            self.assertEqual(edited.metadata.get("status"), "active")
            self.assertNotIn("claim_key", edited.metadata)
            self.assertNotIn("claim_value", edited.metadata)
            self.assertNotIn("confirmed_count", edited.metadata)
            self.assertNotIn("last_confirmed", edited.metadata)
            self.assertIn("verification_invalidated_at", edited.metadata)

    def test_edit_record_replaces_claim_when_explicitly_supplied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = memory_manager.add_record(
                "requirements",
                "Release notes path is docs/old.md.",
                metadata=memory_manager.build_card_metadata(
                    source="fixture",
                    status="active",
                    base={"claim_key": "release_notes.path", "claim_value": "docs/old.md"},
                ),
                root=tmp,
            )
            edited = memory_manager.edit_record(
                record.id,
                tmp,
                content="Release notes path is docs/new.md.",
                summary="Release notes moved to docs/new.md.",
                claim_key="release_notes.path",
                claim_value="docs/new.md",
            )

            self.assertEqual(edited.metadata.get("claim_key"), "release_notes.path")
            self.assertEqual(edited.metadata.get("claim_value"), "docs/new.md")

    def test_edit_record_clears_claim_with_explicit_clear(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = memory_manager.add_record(
                "requirements",
                "Release notes path is docs/old.md.",
                metadata=memory_manager.build_card_metadata(
                    source="fixture",
                    status="active",
                    base={"claim_key": "release_notes.path", "claim_value": "docs/old.md"},
                ),
                root=tmp,
            )
            edited = memory_manager.edit_record(record.id, tmp, clear_claim=True)

            self.assertNotIn("claim_key", edited.metadata)
            self.assertNotIn("claim_value", edited.metadata)

    def test_edit_record_invalid_claim_inputs_do_not_modify_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = memory_manager.add_record(
                "requirements",
                "Release notes path is docs/old.md.",
                metadata=memory_manager.build_card_metadata(
                    source="fixture",
                    status="active",
                    base={"claim_key": "release_notes.path", "claim_value": "docs/old.md"},
                ),
                root=tmp,
            )

            with self.assertRaises(ValueError):
                memory_manager.edit_record(record.id, tmp, claim_key="release_notes.path")

            with self.assertRaises(ValueError):
                memory_manager.edit_record(record.id, tmp, clear_claim=True, claim_key="release_notes.path", claim_value="docs/new.md")

            with self.assertRaises(ValueError):
                memory_manager.edit_record(record.id, tmp, claim_key=" ", claim_value="docs/new.md")

            unchanged = memory_manager.get_record(record.id, tmp)
            self.assertEqual(unchanged.content, record.content)
            self.assertEqual(unchanged.metadata.get("claim_key"), "release_notes.path")
            self.assertEqual(unchanged.metadata.get("claim_value"), "docs/old.md")

    def test_update_metadata_works_for_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = memory_manager.add_record("requirements", "Keep storage local.", root=tmp)
            updated = memory_manager.update_record_metadata(record.id, {"status": "resolved"}, tmp)
            fetched = memory_manager.get_record(record.id, tmp)

            self.assertEqual(updated.id, record.id)
            self.assertEqual(fetched.metadata["status"], "resolved")
            self.assertEqual(fetched.content, "Keep storage local.")

    def test_update_metadata_works_for_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recall_config.ensure_config(tmp)
            cfg = recall_config.load_config(tmp)
            cfg["backend"] = "jsonl"
            recall_config.save_config(cfg, tmp)
            record = memory_manager.add_record("requirements", "Keep JSONL local.", root=tmp)
            updated = memory_manager.update_record_metadata(record.id, {"status": "resolved"}, tmp)
            fetched = memory_manager.get_record(record.id, tmp)

            self.assertEqual(updated.id, record.id)
            self.assertEqual(fetched.metadata["status"], "resolved")

    def test_edit_record_updates_content_category_and_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = memory_manager.add_record("requirements", "Use raw transcript logs.", root=tmp)
            edited = memory_manager.edit_record(
                record.id,
                tmp,
                category="decisions",
                content="Use structured memory cards.",
                summary="Structured cards are preferred.",
                tags=["memory-quality"],
                status="active",
            )
            old_query = memory_manager.query("raw transcript logs", categories=["requirements"], root=tmp)
            new_query = memory_manager.query("structured memory cards", categories=["decisions"], root=tmp)
            doctor = memory_manager.doctor(tmp)

            self.assertEqual(edited.id, record.id)
            self.assertEqual(edited.category, "decisions")
            self.assertIn("edited_at", edited.metadata)
            self.assertEqual(old_query["results"], [])
            self.assertEqual(new_query["results"][0]["id"], record.id)
            self.assertTrue(doctor["index_complete"])

    def test_edit_and_delete_record_work_for_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recall_config.ensure_config(tmp)
            cfg = recall_config.load_config(tmp)
            cfg["backend"] = "jsonl"
            recall_config.save_config(cfg, tmp)
            record = memory_manager.add_record("requirements", "Use raw transcript logs.", root=tmp)

            edited = memory_manager.edit_record(
                record.id,
                tmp,
                category="decisions",
                content="Use structured memory cards.",
                summary="Structured cards are preferred.",
            )
            deleted = memory_manager.delete_record(record.id, tmp)

            self.assertEqual(edited.category, "decisions")
            self.assertEqual(deleted.id, record.id)
            self.assertIsNone(memory_manager.get_record(record.id, tmp))
            self.assertTrue(memory_manager.doctor(tmp)["index_complete"])

    def test_confirm_resolve_stale_and_prune_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = memory_manager.add_record("decisions", "Use schema-first memory cards.", root=tmp)
            confirmed = memory_manager.confirm_record(record.id, tmp, source_session="session-1")
            resolved = memory_manager.resolve_record(record.id, tmp, "Implemented.")
            stale = memory_manager.mark_record_stale(record.id, tmp, "Needs review.")
            archived = memory_manager.prune_record(record.id, tmp, "No longer useful.")

            self.assertEqual(confirmed.metadata["confirmed_count"], 1)
            self.assertEqual(confirmed.metadata["source_session"], "session-1")
            self.assertEqual(resolved.metadata["status"], "resolved")
            self.assertEqual(stale.metadata["status"], "stale")
            self.assertEqual(archived.metadata["status"], "archived")
            self.assertIn("archived_at", archived.metadata)

    def test_supersede_links_old_and_new_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = memory_manager.add_record(
                "decisions",
                "Use raw transcripts for memory.",
                memory_manager.build_card_metadata(status="active", tags=["memory-policy"]),
                root=tmp,
            )
            new = memory_manager.add_record(
                "decisions",
                "Use structured memory cards instead of raw transcripts.",
                memory_manager.build_card_metadata(status="active", tags=["memory-policy"], importance=0.9),
                root=tmp,
            )

            reason = "Checked current project evidence: structured memory cards are required."
            result = memory_manager.supersede_record(old.id, new.id, tmp, reason)
            query = memory_manager.query("memory policy transcripts", categories=["decisions"], root=tmp)
            reopened_old = memory_manager.get_record(old.id, tmp)
            reopened_new = memory_manager.get_record(new.id, tmp)
            history = memory_manager.query(
                "memory policy transcripts",
                categories=["decisions"],
                statuses=["superseded"],
                root=tmp,
            )

            self.assertEqual(result["old"].metadata["status"], "superseded")
            self.assertEqual(result["old"].metadata["superseded_by"], new.id)
            self.assertIn(old.id, result["new"].metadata["supersedes"])
            self.assertEqual(query["results"][0]["id"], new.id)
            self.assertEqual(reopened_old.metadata["lifecycle_note"], reason)
            self.assertEqual(reopened_old.metadata["superseded_by"], new.id)
            self.assertIn(old.id, reopened_new.metadata["supersedes"])
            self.assertEqual(history["results"][0]["id"], old.id)
            self.assertEqual(history["results"][0]["metadata"]["lifecycle_note"], reason)

    def test_merge_marks_secondaries_superseded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            primary = memory_manager.add_record("requirements", "Primary memory remains.", root=tmp)
            secondary = memory_manager.add_record("requirements", "Secondary memory is folded in.", root=tmp)

            result = memory_manager.merge_records(primary.id, [secondary.id], tmp, "Combined duplicate memories.")
            fetched_secondary = memory_manager.get_record(secondary.id, tmp)

            self.assertIn(secondary.id, result["primary"].metadata["merged_from"])
            self.assertEqual(fetched_secondary.metadata["status"], "superseded")
            self.assertEqual(fetched_secondary.metadata["superseded_by"], primary.id)


if __name__ == "__main__":
    unittest.main()
