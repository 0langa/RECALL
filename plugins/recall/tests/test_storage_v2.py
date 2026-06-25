from __future__ import annotations

import concurrent.futures
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import config as recall_config  # noqa: E402
import memory_manager  # noqa: E402
import storage  # noqa: E402


class StorageV2Tests(unittest.TestCase):
    def test_sqlite_uses_schema_v2_and_concurrency_pragmas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage.init_store(tmp)
            with closing(storage.connect_sqlite(tmp)) as connection:
                columns = {row[1] for row in connection.execute("PRAGMA table_info(memories)")}
                journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
                foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
                busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
            required = {
                "memory_type",
                "title",
                "status",
                "trust",
                "confidence",
                "importance",
                "source_kind",
                "source_path",
                "source_hash",
                "source_revision",
                "created_at",
                "updated_at",
                "confirmed_at",
                "accessed_at",
                "expires_at",
                "lineage",
            }
            self.assertTrue(required.issubset(columns))
            self.assertEqual(storage.schema_version(tmp), 2)
            self.assertEqual(str(journal_mode).lower(), "wal")
            self.assertEqual(foreign_keys, 1)
            self.assertGreaterEqual(busy_timeout, 1000)

    def test_v1_store_migrates_with_backup_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recall_config.ensure_config(tmp)
            path = storage.db_path(tmp)
            with closing(sqlite3.connect(path)) as connection:
                connection.execute(
                    """
                    CREATE TABLE memories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        category TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        content TEXT NOT NULL,
                        metadata TEXT NOT NULL DEFAULT '{}',
                        embedding TEXT NOT NULL DEFAULT '[]'
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO memories (category, timestamp, content, metadata, embedding) VALUES (?, ?, ?, ?, ?)",
                    ("architecture", "2026-01-01T00:00:00+00:00", "V1 survives.", "{}", "[]"),
                )
                connection.commit()

            storage.init_store(tmp)
            first_backups = list((recall_config.memory_dir(tmp) / "backups").glob("memory-v1-*.sqlite"))
            storage.init_store(tmp)
            second_backups = list((recall_config.memory_dir(tmp) / "backups").glob("memory-v1-*.sqlite"))

            self.assertEqual(len(first_backups), 1)
            self.assertEqual(first_backups, second_backups)
            self.assertEqual(storage.schema_version(tmp), 2)
            self.assertEqual(next(iter(storage.iter_records(tmp))).content, "V1 survives.")

    def test_normalized_columns_follow_card_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_manager.add_record(
                "requirements",
                "Source-linked requirement.",
                memory_manager.build_card_metadata(
                    summary="Source-linked requirement",
                    source="plugins/recall/README.md",
                    status="active",
                    importance=0.9,
                    confidence=0.8,
                    base={
                        "memory_type": "requirement",
                        "trust": 0.75,
                        "source_kind": "file",
                        "source_path": "plugins/recall/README.md",
                        "source_hash": "abc123",
                        "source_revision": "deadbeef",
                    },
                ),
                tmp,
            )
            with closing(sqlite3.connect(storage.db_path(tmp))) as connection:
                row = connection.execute(
                    "SELECT memory_type, title, status, trust, confidence, importance, source_kind, source_path, source_hash, source_revision FROM memories"
                ).fetchone()
            self.assertEqual(row, ("requirement", "Source-linked requirement", "active", 0.75, 0.8, 0.9, "file", "plugins/recall/README.md", "abc123", "deadbeef"))

    def test_concurrent_writers_do_not_lose_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage.init_store(tmp)

            def write(index: int) -> int:
                return memory_manager.add_record("tasks", f"Concurrent record {index}", root=tmp).id

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                ids = list(executor.map(write, range(40)))
            records = list(storage.iter_records(tmp))
            self.assertEqual(len(ids), len(set(ids)))
            self.assertEqual(len(records), 40)

    def test_doctor_reports_sqlite_migration_and_fts_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = memory_manager.doctor(tmp)
            self.assertEqual(report["schema_version"], 2)
            self.assertEqual(report["sqlite"]["journal_mode"], "wal")
            self.assertTrue(report["sqlite"]["foreign_keys"])
            self.assertGreaterEqual(report["sqlite"]["busy_timeout_ms"], 1000)
            self.assertIn("fts5_available", report["sqlite"])


if __name__ == "__main__":
    unittest.main()
