"""Portable export, import, backup, restore, and store-migration workflows."""

from __future__ import annotations

import json
import shutil
import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config as recall_config
import index_store
import storage
import security


FORMAT = "recall.export.v1"


def _sqlite_record_count(db_path: Path) -> int:
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute("SELECT COUNT(*) FROM memories").fetchone()
        return int(row[0]) if row else 0
    finally:
        connection.close()


def migrate_legacy_store(root: str | Path | None = None, *, apply: bool = False) -> dict[str, Any]:
    """Migrate a legacy `.codex_memory/` store into provider-neutral `.recall/`.

    Copies (never moves) the SQLite store via the sqlite backup API, plus the
    config and any JSONL files, rebuilds the vector index against the new
    directory, and verifies record counts match. The legacy directory is left
    untouched as a frozen backup; once `.recall/` exists it wins resolution
    and `.codex_memory/` becomes read-only history by precedence.
    """

    project = recall_config.project_root(root)
    legacy = recall_config.legacy_memory_dir(project)
    neutral = recall_config.neutral_memory_dir(project)
    report: dict[str, Any] = {
        "action": "migrate-store",
        "mode": "apply" if apply else "dry-run",
        "legacy": str(legacy),
        "target": str(neutral),
    }
    if not legacy.exists():
        return {**report, "result": "nothing_to_migrate", "reason": "no legacy .codex_memory directory"}
    if neutral.exists() and any(neutral.iterdir()):
        return {
            **report,
            "result": "refused",
            "reason": ".recall already exists and is not empty; resolve manually to avoid overwriting memory",
        }

    legacy_db = legacy / "memory.sqlite"
    legacy_jsonl = legacy / "jsonl"
    plan = {
        "sqlite": legacy_db.exists(),
        "sqlite_records": _sqlite_record_count(legacy_db) if legacy_db.exists() else 0,
        "config": (legacy / "memory_config.json").exists(),
        "jsonl_files": len(list(legacy_jsonl.glob("*.jsonl"))) if legacy_jsonl.exists() else 0,
    }
    report["plan"] = plan
    if not apply:
        return {**report, "result": "planned", "next": "re-run with --apply to migrate"}

    neutral.mkdir(parents=True, exist_ok=True)
    if plan["config"]:
        shutil.copyfile(legacy / "memory_config.json", neutral / "memory_config.json")
    if plan["sqlite"]:
        # sqlite backup API is safe against a WAL store and checkpoints it.
        source = sqlite3.connect(legacy_db)
        target = sqlite3.connect(neutral / "memory.sqlite")
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
    if plan["jsonl_files"]:
        (neutral / "jsonl").mkdir(exist_ok=True)
        for path in legacy_jsonl.glob("*.jsonl"):
            shutil.copyfile(path, neutral / "jsonl" / path.name)

    migrated_count = _sqlite_record_count(neutral / "memory.sqlite") if plan["sqlite"] else 0
    if plan["sqlite"] and migrated_count != plan["sqlite_records"]:
        return {
            **report,
            "result": "failed",
            "reason": f"record count mismatch after copy: legacy {plan['sqlite_records']} vs migrated {migrated_count}",
        }
    # Root now resolves to .recall (it exists), so rebuild targets the new store.
    index_report = index_store.rebuild(project)
    gitignore = recall_config.ensure_gitignore_entries(project)
    return {
        **report,
        "result": "migrated",
        "records": migrated_count,
        "index": index_report,
        "gitignore": gitignore,
        "legacy_directory": "left in place as frozen backup; .recall now wins resolution. Delete .codex_memory manually once satisfied.",
    }


def _payload(root: str | Path | None) -> dict[str, Any]:
    records = [
        {
            "id": record.id,
            "category": record.category,
            "timestamp": record.timestamp,
            "content": security.redact_text(record.content),
            "metadata": security.redact_value(record.metadata),
            "embedding": record.embedding or [],
        }
        for record in storage.iter_records(root)
    ]
    return {"format": FORMAT, "config": recall_config.load_config(root), "records": records}


def export_memory(path: str | Path, root: str | Path | None = None) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _payload(root)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"path": str(target), "records": len(payload["records"]), "format": FORMAT}


def backup_memory(root: str | Path | None = None) -> dict[str, Any]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = recall_config.memory_dir(root) / "backups" / f"recall-{stamp}.json"
    return export_memory(target, root)


def _validated(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("format") != FORMAT:
        raise ValueError(f"unsupported RECALL export format; expected {FORMAT}")
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("RECALL export records must be a list")
    required = {"id", "category", "timestamp", "content", "metadata", "embedding"}
    for record in records:
        if not isinstance(record, dict) or not required.issubset(record):
            raise ValueError("RECALL export contains an invalid record")
    return security.redact_value(payload)


def import_memory(path: str | Path, root: str | Path | None = None, *, replace: bool = False) -> dict[str, Any]:
    payload = _validated(path)
    existing = list(storage.iter_records(root))
    if existing and not replace:
        raise ValueError("memory store is not empty; pass --replace to restore this export")
    recall_config.save_config(payload["config"], root)
    cfg = recall_config.load_config(root)
    records = payload["records"]
    if cfg["backend"] == "sqlite":
        storage.init_sqlite(root)
        with closing(storage.connect_sqlite(root)) as connection:
            connection.execute("DELETE FROM memories")
            for record in records:
                normalized = storage._normalized_fields(record["metadata"], record["timestamp"])
                connection.execute(
                    """
                    INSERT INTO memories (
                        id, category, timestamp, content, metadata, embedding,
                        memory_type, title, status, trust, confidence, importance,
                        source_kind, source_path, source_hash, source_revision,
                        created_at, updated_at, confirmed_at, accessed_at, expires_at, lineage
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(record["id"]), record["category"], record["timestamp"], record["content"],
                        json.dumps(record["metadata"], sort_keys=True), json.dumps(record["embedding"]),
                        *normalized.values(),
                    ),
                )
            connection.commit()
    else:
        base = storage.jsonl_dir(root)
        base.mkdir(parents=True, exist_ok=True)
        for old in base.glob("*.jsonl"):
            old.unlink()
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            grouped[str(record["category"])].append(record)
        for category, category_records in grouped.items():
            target = base / f"{category}.jsonl"
            target.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in category_records), encoding="utf-8")
    index_store.rebuild(root)
    return {"path": str(Path(path).expanduser().resolve()), "records": len(records), "format": FORMAT}


def restore_memory(path: str | Path, root: str | Path | None = None) -> dict[str, Any]:
    return import_memory(path, root, replace=True)
