from __future__ import annotations

import sys
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import memory_manager  # noqa: E402
from services import provenance_service  # noqa: E402


class ProvenanceTests(unittest.TestCase):
    def test_save_insight_cli_captures_file_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "docs" / "decision.md"
            source.parent.mkdir()
            source.write_text("Use WAL mode.", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "recall_skill.py"),
                    "--root",
                    tmp,
                    "save-insight",
                    "decisions",
                    "Use WAL mode.",
                    "--summary",
                    "Use WAL mode",
                    "--source-path",
                    "docs/decision.md",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )
            record_id = json.loads(completed.stdout)["id"]
            record = memory_manager.get_record(record_id, tmp)
            self.assertEqual(record.metadata["source_kind"], "file")
            self.assertEqual(record.metadata["source_path"], "docs/decision.md")
            self.assertEqual(len(record.metadata["source_hash"]), 64)

    def test_file_descriptor_is_relative_hashed_and_project_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "docs" / "truth.md"
            source.parent.mkdir()
            source.write_text("current truth", encoding="utf-8")
            descriptor = provenance_service.describe_file(tmp, source)
            self.assertEqual(descriptor["source_kind"], "file")
            self.assertEqual(descriptor["source_path"], "docs/truth.md")
            self.assertEqual(len(descriptor["source_hash"]), 64)
            with self.assertRaisesRegex(ValueError, "outside project root"):
                provenance_service.describe_file(tmp, Path(tmp).parent / "outside.md")

    def test_reconcile_marks_modified_and_deleted_sources_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            modified = Path(tmp) / "src" / "modified.txt"
            deleted = Path(tmp) / "src" / "deleted.txt"
            modified.parent.mkdir()
            modified.write_text("before", encoding="utf-8")
            deleted.write_text("exists", encoding="utf-8")
            first = provenance_service.describe_file(tmp, modified)
            second = provenance_service.describe_file(tmp, deleted)
            modified_record = memory_manager.add_record("architecture", "Modified source claim", first, tmp)
            deleted_record = memory_manager.add_record("requirements", "Deleted source claim", second, tmp)

            modified.write_text("after", encoding="utf-8")
            deleted.unlink()
            report = provenance_service.reconcile_sources(tmp)

            self.assertEqual(report["modified"], 1)
            self.assertEqual(report["deleted"], 1)
            self.assertEqual(memory_manager.get_record(modified_record.id, tmp).metadata["status"], "stale")
            self.assertEqual(
                memory_manager.get_record(modified_record.id, tmp).metadata["invalidation_reason"],
                "source_modified",
            )
            self.assertEqual(memory_manager.get_record(deleted_record.id, tmp).metadata["status"], "stale")

    def test_reconcile_detects_moved_source_by_content_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = Path(tmp) / "old" / "design.md"
            new = Path(tmp) / "new" / "design.md"
            old.parent.mkdir()
            old.write_text("stable design", encoding="utf-8")
            record = memory_manager.add_record(
                "architecture",
                "Design source moved.",
                provenance_service.describe_file(tmp, old),
                tmp,
            )
            new.parent.mkdir()
            old.replace(new)

            report = provenance_service.reconcile_sources(tmp)
            refreshed = memory_manager.get_record(record.id, tmp)
            self.assertEqual(report["moved"], 1)
            self.assertEqual(refreshed.metadata["invalidation_reason"], "source_moved")
            self.assertEqual(refreshed.metadata["replacement_source_path"], "new/design.md")

    def test_refresh_source_restores_current_hash_and_active_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "truth.md"
            source.write_text("v1", encoding="utf-8")
            record = memory_manager.add_record(
                "decisions",
                "Tracked decision.",
                provenance_service.describe_file(tmp, source),
                tmp,
            )
            source.write_text("v2", encoding="utf-8")
            provenance_service.reconcile_sources(tmp)
            refreshed = provenance_service.refresh_source(record.id, tmp)
            self.assertEqual(refreshed.metadata["status"], "active")
            self.assertNotIn("invalidation_reason", refreshed.metadata)
            self.assertEqual(refreshed.metadata["source_hash"], provenance_service.hash_file(source))


if __name__ == "__main__":
    unittest.main()
