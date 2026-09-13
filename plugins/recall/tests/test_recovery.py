from __future__ import annotations

import json
from contextlib import closing
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import memory_manager  # noqa: E402
import storage  # noqa: E402
import config  # noqa: E402
from services import recovery_service  # noqa: E402


class RecoveryTests(unittest.TestCase):
    def test_index_fault_cannot_hide_committed_save(self) -> None:
        for backend in ("sqlite", "jsonl"):
            with tempfile.TemporaryDirectory() as tmp:
                cfg = config.load_config(tmp)
                cfg["backend"] = backend
                config.save_config(cfg, tmp)
                committed_ids = []

                def failed_append(record, root, observed=committed_ids):
                    observed.extend(item.id for item in storage.iter_records(root))
                    raise OSError("Injected index fault")

                with mock.patch.object(memory_manager.index_store, "append_record", side_effect=failed_append):
                    with self.assertLogs("memory_manager", level="WARNING"):
                        result = memory_manager.add_record_if_useful(
                            "architecture", "Canonical storage commits before its derived index.", root=tmp,
                        )
                self.assertEqual(result["action"], "saved")
                self.assertEqual(committed_ids, [result["record"].id])
                self.assertEqual(storage.get_record(result["record"].id, tmp), result["record"])
                self.assertEqual(memory_manager.rebuild_index(tmp)["indexed_records"], 1)
                self.assertTrue(memory_manager.doctor(tmp)["index_complete"])

    def test_sqlite_nested_write_rolls_back_and_never_updates_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage.init_store(tmp)
            with mock.patch.object(memory_manager.index_store, "append_record") as append:
                with self.assertRaisesRegex(RuntimeError, "Abort outer transaction"):
                    with storage.write_transaction(tmp):
                        saved = memory_manager.add_record("architecture", "Uncommitted draft", root=tmp)
                        self.assertEqual(storage.get_record(saved.id, tmp), saved)
                        with closing(storage.connect_sqlite(tmp)) as separate:
                            self.assertEqual(separate.execute("SELECT COUNT(*) FROM memories").fetchone()[0], 0)
                        raise RuntimeError("Abort outer transaction")
                append.assert_not_called()
            self.assertEqual(list(storage.iter_records(tmp)), [])

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
