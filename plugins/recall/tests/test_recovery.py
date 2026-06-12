from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import memory_manager  # noqa: E402
import storage  # noqa: E402
from services import recovery_service  # noqa: E402


class RecoveryTests(unittest.TestCase):
    def test_export_restore_preserves_identity_and_relationships(self) -> None:
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as restored:
            record = memory_manager.add_record(
                "architecture",
                "Use a local SQLite authority.",
                memory_manager.build_card_metadata(
                    summary="Local authority",
                    status="validated",
                    base={
                        "trust": 0.95,
                        "source_kind": "file",
                        "source_path": "docs/design.md",
                        "source_hash": "abc123",
                        "supersedes": [41],
                        "lineage": {"parent_ids": [41]},
                    },
                ),
                source,
            )
            archive = Path(source) / "export.json"
            recovery_service.export_memory(archive, source)
            report = recovery_service.restore_memory(archive, restored)
            recovered = storage.get_record(record.id, restored)

            self.assertEqual(report["records"], 1)
            self.assertIsNotNone(recovered)
            assert recovered is not None
            self.assertEqual(recovered.id, record.id)
            self.assertEqual(recovered.metadata["status"], "validated")
            self.assertEqual(recovered.metadata["source_path"], "docs/design.md")
            self.assertEqual(recovered.metadata["supersedes"], [41])
            self.assertEqual(recovered.metadata["lineage"], {"parent_ids": [41]})

    def test_export_redacts_secret_like_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_manager.add_record("risks", "token=unsafe-value", {"nested": "password=unsafe"}, tmp)
            archive = Path(tmp) / "export.json"
            recovery_service.export_memory(archive, tmp)
            text = archive.read_text(encoding="utf-8")

            self.assertNotIn("unsafe-value", text)
            self.assertNotIn("password=unsafe", text)
            self.assertIn("[REDACTED]", text)

    def test_import_requires_replace_for_nonempty_store(self) -> None:
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as target:
            memory_manager.add_record("requirements", "Source record", root=source)
            archive = Path(source) / "export.json"
            recovery_service.export_memory(archive, source)
            memory_manager.add_record("requirements", "Existing target", root=target)

            with self.assertRaisesRegex(ValueError, "not empty"):
                recovery_service.import_memory(archive, target)
            recovery_service.import_memory(archive, target, replace=True)
            self.assertEqual([record.content for record in storage.iter_records(target)], ["Source record"])

    def test_malformed_export_is_rejected_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            existing = memory_manager.add_record("requirements", "Keep me", root=tmp)
            archive = Path(tmp) / "bad.json"
            archive.write_text(json.dumps({"format": "wrong", "records": []}), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unsupported"):
                recovery_service.restore_memory(archive, tmp)
            self.assertEqual(storage.get_record(existing.id, tmp).content, "Keep me")
