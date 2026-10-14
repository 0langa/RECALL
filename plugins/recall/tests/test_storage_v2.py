from __future__ import annotations

import concurrent.futures
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest import mock
from contextlib import closing
from functools import partial
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import config as recall_config  # noqa: E402
import index_store  # noqa: E402
import memory_hygiene  # noqa: E402
import memory_lifecycle  # noqa: E402
import memory_manager  # noqa: E402
import retrieval  # noqa: E402
import storage  # noqa: E402
from services import lifecycle_service, recovery_service  # noqa: E402


def _jsonl_project(project: Path) -> Path:
    cfg = recall_config.load_config(project)
    cfg["backend"] = "jsonl"
    recall_config.save_config(cfg, project)
    return project


def _plant(project: Path, file_name: str, **row: object) -> None:
    """Append a row the way a cloned repository's committed .recall/jsonl can carry it."""
    payload = {"timestamp": "2026-10-14T00:00:00+00:00", "content": "planted", "metadata": {},
               "embedding": [], **row}
    with (storage.jsonl_dir(project) / file_name).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def _link_directory(link: Path, target: Path) -> None:
    """Create a directory symlink, or a junction where Windows symlinks need privileges."""
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        if sys.platform != "win32":
            raise unittest.SkipTest("directory symlinks are unavailable") from exc
        import _winapi

        _winapi.CreateJunction(str(target), str(link))


class StorageV2Tests(unittest.TestCase):
    def test_legacy_config_upgrade_cannot_erase_an_acknowledged_category(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recall_config.root_config_path(tmp).write_text(json.dumps({"backend": "jsonl"}), encoding="utf-8")
            recall_config.ensure_config(tmp)
            waiting = threading.Event()
            release = threading.Event()
            errors = []
            original_load = json.load

            def held_legacy_read(handle, *args, **kwargs):
                loaded = original_load(handle, *args, **kwargs)
                if threading.current_thread().name == "legacy-reader" and not waiting.is_set():
                    # Pause after the snapshot is complete. An open Windows
                    # read handle would prevent any replacement at all.
                    handle.close()
                    waiting.set()
                    if not release.wait(5):
                        raise TimeoutError("Test did not release the legacy reader")
                return loaded

            def reader():
                try:
                    recall_config.load_config(tmp)
                except BaseException as exc:
                    errors.append(repr(exc))

            with mock.patch.object(recall_config.json, "load", side_effect=held_legacy_read):
                worker = threading.Thread(target=reader, name="legacy-reader")
                worker.start()
                try:
                    self.assertTrue(waiting.wait(5))
                    acknowledged = recall_config.add_category("review_custom", "Keep this category.", raw_root=tmp)
                    self.assertEqual(acknowledged["description"], "Keep this category.")
                    self.assertIn("review_custom", recall_config.load_config(tmp)["categories"])
                finally:
                    release.set()
                    worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])
            final = recall_config.load_config(tmp)
            self.assertIn("review_custom", final["categories"])
            self.assertTrue(final["activation"]["enabled"])

    def test_parallel_category_definitions_keep_all_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
                results = list(executor.map(
                    lambda number: recall_config.add_category(f"custom_{number}", raw_root=tmp), range(12),
                ))
            categories = recall_config.load_config(tmp)["categories"]
            self.assertEqual(len(results), 12)
            self.assertTrue({f"custom_{number}" for number in range(12)}.issubset(categories))

    def test_atomic_initial_config_keeps_legacy_activation_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recall_config.root_config_path(tmp).write_text(json.dumps({"backend": "jsonl"}), encoding="utf-8")
            cfg = recall_config.load_config(tmp)
            self.assertEqual(cfg["backend"], "jsonl")
            self.assertTrue(cfg["activation"]["enabled"])
            self.assertEqual(cfg["activation"]["activated_by"], "legacy_memory_store")

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

    def test_idempotency_index_applies_to_already_migrated_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage.init_store(tmp)
            with closing(storage.connect_sqlite(tmp)) as connection:
                names = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'index'"
                    ).fetchall()
                }
            self.assertIn("idx_memories_idempotency", names)

    def test_add_record_if_new_returns_existing_on_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first, inserted_first = storage.add_record_if_new(
                "tasks", "2026-01-01T00:00:00+00:00", "Replayed call.", {}, [], "key-1", tmp
            )
            second, inserted_second = storage.add_record_if_new(
                "tasks", "2026-01-01T00:00:00+00:00", "Replayed call.", {}, [], "key-1", tmp
            )
            self.assertTrue(inserted_first)
            self.assertFalse(inserted_second)
            self.assertEqual(first.id, second.id)
            self.assertEqual(len(list(storage.iter_records(tmp))), 1)

    def test_add_record_if_new_is_race_free_under_concurrency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage.init_store(tmp)

            def write(index: int) -> int:
                record, _ = storage.add_record_if_new(
                    "tasks",
                    "2026-01-01T00:00:00+00:00",
                    "Same idempotent write racing from many threads.",
                    {},
                    [],
                    "shared-key",
                    tmp,
                )
                return record.id

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                ids = list(executor.map(write, range(20)))
            self.assertEqual(len(set(ids)), 1, "concurrent replays of the same idempotency_key must resolve to one record")
            self.assertEqual(len(list(storage.iter_records(tmp))), 1)

    def test_integrity_check_detects_corrupted_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage.init_store(tmp)
            memory_manager.add_record("tasks", "Healthy record before corruption.", root=tmp)
            self.assertTrue(storage.integrity_check(tmp)["ok"])

            path = storage.db_path(tmp)
            data = bytearray(path.read_bytes())
            data[100:200] = b"\x00" * 100
            path.write_bytes(bytes(data))

            report = storage.integrity_check(tmp)
            self.assertFalse(report["ok"])
            self.assertTrue(report["errors"])

    def test_doctor_short_circuits_on_corrupted_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage.init_store(tmp)
            memory_manager.add_record("tasks", "Healthy record before corruption.", root=tmp)
            path = storage.db_path(tmp)
            path.write_bytes(b"not a sqlite file at all")

            report = memory_manager.doctor(tmp)
            self.assertTrue(report["storage_corrupted"])
            self.assertIn("repairs_available", report)

    def test_restore_from_backup_recovers_corrupted_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage.init_store(tmp)
            memory_manager.add_record("tasks", "Record present in the backup.", root=tmp)
            backup_dir = recall_config.memory_dir(tmp) / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / "memory-v2-20260101T000000Z.sqlite"
            with closing(storage.connect_sqlite(tmp)) as connection, closing(sqlite3.connect(backup_path)) as backup:
                connection.backup(backup)

            memory_manager.add_record("tasks", "Record added after the backup, lost on restore.", root=tmp)
            path = storage.db_path(tmp)
            path.write_bytes(b"not a sqlite file at all")

            restored_from = storage.restore_from_backup(tmp)
            self.assertEqual(restored_from, backup_path)
            self.assertTrue(storage.integrity_check(tmp)["ok"])
            records = [record.content for record in storage.iter_records(tmp)]
            self.assertIn("Record present in the backup.", records)
            self.assertNotIn("Record added after the backup, lost on restore.", records)
            self.assertTrue(path.with_suffix(".sqlite.corrupt").exists())

    def test_repair_restore_backup_flag_wires_through_memory_manager(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage.init_store(tmp)
            memory_manager.add_record("tasks", "Kept via restore.", root=tmp)
            backup_dir = recall_config.memory_dir(tmp) / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / "memory-v2-20260101T000000Z.sqlite"
            with closing(storage.connect_sqlite(tmp)) as connection, closing(sqlite3.connect(backup_path)) as backup:
                connection.backup(backup)
            storage.db_path(tmp).write_bytes(b"not a sqlite file at all")

            result = memory_manager.repair(tmp, restore_backup=True)
            self.assertEqual(result["restored_from"], str(backup_path))
            self.assertFalse(result["doctor"]["storage_corrupted"])


class JsonlStoreConfinementTests(unittest.TestCase):
    """Rows and files in .recall/jsonl are untrusted: a cloned repository can commit them."""

    def test_planted_row_stays_readable_but_cannot_name_a_file_outside_the_store(self) -> None:
        # Review reproduction: one lifecycle edit of a planted row created or
        # rewrote <category>.jsonl three levels above jsonl/. Reads keep the
        # row; every edit that would turn its category into a path fails closed.
        for label in ("posix_relative", "windows_relative", "absolute", "windows_drive", "no_letters"):
            with self.subTest(label), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp).resolve()
                project = _jsonl_project(base / "a" / "project")
                legit = memory_manager.add_record("decisions", "Legit decision survives.", root=project)
                victim = base / "a" / "outside.jsonl"
                victim.write_text("precious line\n", encoding="utf-8")
                target = victim.with_suffix("")
                category = {
                    "posix_relative": "../../../outside",
                    "windows_relative": "..\\..\\..\\outside",
                    # Rooted without a drive, so Windows keeps the store's drive.
                    "absolute": "/" + target.relative_to(target.anchor).as_posix(),
                    # Only Windows reads this as a path; elsewhere it is an odd file name.
                    "windows_drive": "\\".join([target.drive or "C:", *target.parts[1:]]),
                    # normalize_category() itself raises for a name without a letter or digit.
                    "no_letters": "..",
                }[label]
                # The planted vector is stale, so an index rebuild wants to rewrite the row.
                _plant(project, "decisions.jsonl", id=99, category=category)
                store = {path.name: path.read_bytes() for path in storage.jsonl_dir(project).iterdir()}

                planted = storage.get_record(99, project)
                self.assertIsNotNone(planted)
                self.assertEqual(planted.category, category)
                self.assertEqual(sorted(record.id for record in storage.iter_records(project)), [legit.id, 99])
                for sink, attempt in (
                    ("update_record_metadata", partial(storage.update_record_metadata, 99, {"status": "stale"}, project)),
                    ("delete_record", partial(storage.delete_record, 99, project)),
                    ("add_record", partial(storage.add_record, category, legit.timestamp, "planted", {}, [], project)),
                    ("update_record", partial(storage.update_record, legit.id, category=category, content=legit.content,
                                              metadata=legit.metadata, embedding=[], root=project)),
                ):
                    with self.subTest(label, sink=sink), self.assertRaisesRegex(ValueError, "invalid category"):
                        attempt()

                # Retrieval rebuilds the index and scores every row; hygiene
                # fingerprints every row. Neither fails on the planted row.
                hits = retrieval.query("Legit decision survives", root=project)["results"]
                self.assertIn(legit.id, [hit["id"] for hit in hits])
                self.assertEqual(sorted(index_store.load_index(project)), [legit.id, 99])
                memory_hygiene.hygiene_scan(project)
                self.assertEqual({path.name: path.read_bytes() for path in storage.jsonl_dir(project).iterdir()}, store)
                report = memory_manager.doctor(project)
                self.assertEqual(report["invalid_jsonl_rows"], 1)
                self.assertIn("Invalid JSONL row count: 1.", report["warnings"])

                # The canonical row in the same file still edits and deletes; the planted row rides along.
                storage.update_record_metadata(legit.id, {"status": "stale"}, project)
                self.assertEqual(storage.get_record(legit.id, project).metadata, {"status": "stale"})
                storage.delete_record(legit.id, project)
                self.assertEqual([(record.id, record.category) for record in storage.iter_records(project)],
                                 [(99, category)])

                self.assertEqual(victim.read_text(encoding="utf-8"), "precious line\n")
                self.assertEqual([path for path in base.rglob("*") if path.is_file() and project not in path.parents],
                                 [victim])

    def test_edits_naming_a_planted_row_write_nothing_until_it_gets_a_store_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = _jsonl_project(Path(tmp) / "project")
            legit = memory_manager.add_record("decisions", "Legit decision survives.", root=project)
            _plant(project, "decisions.jsonl", id=99, category="../../../outside")
            config_file = recall_config.config_path(project)
            before = {path: path.read_bytes() for path in (config_file, *storage.jsonl_dir(project).iterdir())}

            # Supersede and conflict resolution look up both records before they
            # write either, so the legit record is never left superseded alone.
            for label, attempt in (
                ("supersede legit with planted", partial(memory_lifecycle.supersede, legit.id, 99, project)),
                ("supersede planted with legit", partial(memory_lifecycle.supersede, 99, legit.id, project)),
                ("planted wins conflict", partial(lifecycle_service.resolve_conflict, 99, [legit.id], project)),
                ("legit wins conflict", partial(lifecycle_service.resolve_conflict, legit.id, [99], project)),
                ("edit keeps the category", partial(memory_manager.edit_record, 99, project, content="Edited.")),
            ):
                with self.subTest(label), self.assertRaisesRegex(ValueError, "invalid category"):
                    attempt()
            self.assertEqual({path: path.read_bytes() for path in before}, before)
            self.assertEqual(sorted(storage.jsonl_dir(project).iterdir()), sorted(set(before) - {config_file}))

            # A store name is the way out: then the row edits like any other.
            memory_manager.edit_record(99, project, category="requirements")
            self.assertEqual(storage.get_record(99, project).category, "requirements")
            storage.delete_record(99, project)
            self.assertEqual([record.id for record in storage.iter_records(project)], [legit.id])

    def test_only_store_names_become_jsonl_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = _jsonl_project(Path(tmp) / "project")
            for category in ("..", "../x", "x/../decisions", "/etc/passwd", "C:\\x", "C:x", "c:decisions",
                             "\\\\server\\share\\x", "//server/share/x", "Decisions", "", None, 7):
                with self.subTest(category=category):
                    self.assertFalse(recall_config.is_canonical_category(category))
                    with self.assertRaisesRegex(ValueError, "category"):
                        storage.jsonl_path(category, project)
            self.assertEqual(storage.jsonl_path("api_contracts", project),
                             storage.jsonl_dir(project) / "api_contracts.jsonl")

    def test_linked_jsonl_directory_cannot_redirect_reads_writes_or_deletes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            project = _jsonl_project(base / "project")
            elsewhere = base / "elsewhere"
            elsewhere.mkdir()
            foreign = json.dumps({"id": 1, "category": "decisions", "timestamp": "2026-10-14T00:00:00+00:00",
                                  "content": "Another directory's data.", "metadata": {}, "embedding": []}) + "\n"
            victim = elsewhere / "decisions.jsonl"
            victim.write_text(foreign, encoding="utf-8")
            _link_directory(storage.jsonl_dir(project), elsewhere)

            self.assertEqual(list(storage.iter_records(project)), [])
            with self.assertRaisesRegex(ValueError, "outside the memory store"):
                memory_manager.add_record("decisions", "Must not land elsewhere.", root=project)
            archive = base / "export.json"
            archive.write_text(json.dumps({
                "format": recovery_service.FORMAT, "config": recall_config.load_config(project),
                "records": [{"id": 1, "category": "decisions", "timestamp": "2026-10-14T00:00:00+00:00",
                             "content": "Restored.", "metadata": {}, "embedding": []}],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "outside the memory store"):
                recovery_service.restore_memory(archive, project)

            self.assertEqual(victim.read_text(encoding="utf-8"), foreign)
            self.assertEqual([path.name for path in elsewhere.iterdir()], ["decisions.jsonl"])
            report = memory_manager.doctor(project)
            self.assertEqual(report["unsafe_jsonl_files"], 1)
            self.assertTrue(any("outside the memory store" in warning for warning in report["warnings"]))

    def test_normal_jsonl_store_still_loads_and_edits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = _jsonl_project(Path(tmp) / "project")
            first = memory_manager.add_record("decisions", "Keep JSONL as a supported backend.", root=project)
            second = memory_manager.add_record("API Contracts", "Do not break the v1 payload shape.", root=project)
            _plant(project, "debug_history.jsonl", id=7, category="debug_history", content="An older row.")

            self.assertEqual(sorted((record.id, record.category) for record in storage.iter_records(project)),
                             sorted([(first.id, "decisions"), (second.id, "api_contracts"), (7, "debug_history")]))
            storage.update_record_metadata(first.id, {"status": "stale"}, project)
            storage.update_record(second.id, category="requirements", content=second.content,
                                  metadata=second.metadata, embedding=second.embedding or [], root=project)
            storage.delete_record(7, project)

            records = {record.id: record for record in storage.iter_records(project)}
            self.assertEqual(sorted(records), sorted([first.id, second.id]))
            self.assertEqual(records[first.id].metadata["status"], "stale")
            self.assertEqual(records[second.id].category, "requirements")
            self.assertEqual(sorted(path.name for path in storage.jsonl_dir(project).glob("*.jsonl")),
                             ["api_contracts.jsonl", "debug_history.jsonl", "decisions.jsonl", "requirements.jsonl"])
            report = memory_manager.doctor(project)
            self.assertEqual((report["invalid_jsonl_rows"], report["unsafe_jsonl_files"]), (0, 0))

            # The same store opened through a linked project path resolves to the same files.
            link = Path(tmp) / "linked-project"
            _link_directory(link, project)
            self.assertEqual(sorted(record.id for record in storage.iter_records(link)), sorted(records))


if __name__ == "__main__":
    unittest.main()
