from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import config as recall_config  # noqa: E402
import memory_manager  # noqa: E402


class MemoryLifecycleTests(unittest.TestCase):
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

            result = memory_manager.supersede_record(old.id, new.id, tmp, "Correction from latest design.")
            query = memory_manager.query("memory policy transcripts", categories=["decisions"], root=tmp)

            self.assertEqual(result["old"].metadata["status"], "superseded")
            self.assertEqual(result["old"].metadata["superseded_by"], new.id)
            self.assertIn(old.id, result["new"].metadata["supersedes"])
            self.assertEqual(query["results"][0]["id"], new.id)

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
