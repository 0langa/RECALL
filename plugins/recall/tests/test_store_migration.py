"""migrate-store: legacy .codex_memory -> .recall directory migration."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import config as recall_config  # noqa: E402
import memory_manager  # noqa: E402
from services import recovery_service  # noqa: E402


def run_skill(root: str, *args: str) -> dict:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "recall_skill.py"), "--root", root, *args],
        text=True,
        capture_output=True,
        check=True,
        cwd=ROOT,
    )
    return json.loads(completed.stdout)


def seed_legacy_store(tmp: str, cards: int = 3) -> list[int]:
    """Build a store that lands in .codex_memory by pre-creating the legacy dir."""
    legacy = Path(tmp) / ".codex_memory"
    legacy.mkdir()
    ids = []
    for index in range(cards):
        record = memory_manager.add_record(
            "decisions",
            f"Legacy decision number {index}: keep the storage layer boring.",
            memory_manager.build_card_metadata(summary=f"Legacy decision {index}.", source="skill", status="active"),
            tmp,
        )
        ids.append(record.id)
    assert (legacy / "memory.sqlite").exists(), "fixture must live in the legacy directory"
    return ids


class StoreMigrationTests(unittest.TestCase):
    def test_dry_run_plans_without_touching_anything(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            seed_legacy_store(tmp)
            report = recovery_service.migrate_legacy_store(tmp)
            self.assertEqual(report["result"], "planned")
            self.assertEqual(report["plan"]["sqlite_records"], 3)
            self.assertFalse((Path(tmp) / ".recall").exists())

    def test_apply_migrates_and_new_store_wins_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".git").mkdir()
            ids = seed_legacy_store(tmp)
            report = recovery_service.migrate_legacy_store(tmp, apply=True)
            self.assertEqual(report["result"], "migrated")
            self.assertEqual(report["records"], len(ids))

            # .recall now wins resolution; retrieval reads the migrated store.
            self.assertEqual(recall_config.memory_dir(tmp).name, ".recall")
            result = memory_manager.query("storage layer boring", categories=["decisions"], root=tmp, limit=5)
            self.assertGreaterEqual(len(result["results"]), 1)

            # Legacy directory untouched as frozen backup.
            self.assertTrue((Path(tmp) / ".codex_memory" / "memory.sqlite").exists())
            # Gitignore covers both directories.
            gitignore = (Path(tmp) / ".gitignore").read_text(encoding="utf-8")
            self.assertIn(".recall/", gitignore)

            # New writes land in .recall, not the legacy store.
            memory_manager.add_record(
                "decisions",
                "Post-migration decision: new writes land in the neutral store.",
                memory_manager.build_card_metadata(summary="Post-migration write.", source="skill", status="active"),
                tmp,
            )
            legacy_count = recovery_service._sqlite_record_count(Path(tmp) / ".codex_memory" / "memory.sqlite")
            neutral_count = recovery_service._sqlite_record_count(Path(tmp) / ".recall" / "memory.sqlite")
            self.assertEqual(legacy_count, len(ids))
            self.assertEqual(neutral_count, len(ids) + 1)

    def test_refuses_when_recall_dir_already_has_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            seed_legacy_store(tmp)
            recall_dir = Path(tmp) / ".recall"
            recall_dir.mkdir()
            (recall_dir / "memory_config.json").write_text("{}", encoding="utf-8")
            report = recovery_service.migrate_legacy_store(tmp, apply=True)
            self.assertEqual(report["result"], "refused")

    def test_nothing_to_migrate_without_legacy_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = recovery_service.migrate_legacy_store(tmp, apply=True)
            self.assertEqual(report["result"], "nothing_to_migrate")

    def test_adapter_command_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            seed_legacy_store(tmp)
            planned = run_skill(tmp, "migrate-store")
            self.assertEqual(planned["result"], "planned")
            applied = run_skill(tmp, "migrate-store", "--apply")
            self.assertEqual(applied["result"], "migrated")
            doctor = run_skill(tmp, "doctor")
            self.assertTrue(doctor["report"]["index_complete"])
            self.assertIn(".recall", doctor["report"]["storage_path"])


if __name__ == "__main__":
    unittest.main()
