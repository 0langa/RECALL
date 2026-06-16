#!/usr/bin/env python3
"""Durable RECALL memory storage backends."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import config as recall_config
import security


SCHEMA_VERSION = 2
SQLITE_BUSY_TIMEOUT_MS = 5000

V2_COLUMNS: dict[str, str] = {
    "memory_type": "TEXT NOT NULL DEFAULT 'fact'",
    "title": "TEXT",
    "status": "TEXT NOT NULL DEFAULT 'active'",
    "trust": "REAL NOT NULL DEFAULT 0.5",
    "confidence": "REAL NOT NULL DEFAULT 0.5",
    "importance": "REAL NOT NULL DEFAULT 0.5",
    "source_kind": "TEXT",
    "source_path": "TEXT",
    "source_hash": "TEXT",
    "source_revision": "TEXT",
    "created_at": "TEXT",
    "updated_at": "TEXT",
    "confirmed_at": "TEXT",
    "accessed_at": "TEXT",
    "expires_at": "TEXT",
    "lineage": "TEXT NOT NULL DEFAULT '{}'",
}

LINEAGE_KEYS = ("supersedes", "superseded_by", "merged_from", "merged_into", "related_to")


@dataclass
class MemoryRecord:
    id: int
    category: str
    timestamp: str
    content: str
    metadata: dict[str, Any]
    score: float = 0.0
    embedding: list[float] | None = None


def db_path(root: str | Path | None = None) -> Path:
    return recall_config.memory_dir(root) / "memory.sqlite"


def jsonl_dir(root: str | Path | None = None) -> Path:
    return recall_config.memory_dir(root) / "jsonl"


def vector_index_path(root: str | Path | None = None) -> Path:
    return recall_config.memory_dir(root) / "vector_index.bin"


def connect_sqlite(root: str | Path | None = None) -> sqlite3.Connection:
    """Open a configured SQLite connection for concurrent RECALL access."""

    connection = sqlite3.connect(db_path(root), timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
    connection.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _stored_schema_version(connection: sqlite3.Connection) -> int:
    if not _table_exists(connection, "recall_meta"):
        return 1 if _table_exists(connection, "memories") else 0
    row = connection.execute(
        "SELECT value FROM recall_meta WHERE key = 'schema_version'"
    ).fetchone()
    return int(row[0]) if row else (1 if _table_exists(connection, "memories") else 0)


def _backup_before_migration(connection: sqlite3.Connection, root: str | Path | None, version: int) -> Path:
    backup_dir = recall_config.memory_dir(root) / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(backup_dir.glob(f"memory-v{version}-*.sqlite"))
    if existing:
        return existing[-1]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = backup_dir / f"memory-v{version}-{stamp}.sqlite"
    with closing(sqlite3.connect(target)) as backup:
        connection.backup(backup)
    return target


def _normalized_fields(metadata: dict[str, Any], timestamp: str) -> dict[str, Any]:
    lineage = {key: metadata[key] for key in LINEAGE_KEYS if key in metadata}
    return {
        "memory_type": str(metadata.get("memory_type") or metadata.get("record_kind") or "fact"),
        "title": metadata.get("title") or metadata.get("summary"),
        "status": str(metadata.get("status") or "active"),
        "trust": float(metadata.get("trust", metadata.get("confidence", 0.5))),
        "confidence": float(metadata.get("confidence", 0.5)),
        "importance": float(metadata.get("importance", 0.5)),
        "source_kind": metadata.get("source_kind"),
        "source_path": metadata.get("source_path"),
        "source_hash": metadata.get("source_hash"),
        "source_revision": metadata.get("source_revision"),
        "created_at": metadata.get("created_at") or timestamp,
        "updated_at": metadata.get("updated_at") or metadata.get("edited_at") or timestamp,
        "confirmed_at": metadata.get("confirmed_at") or metadata.get("last_confirmed"),
        "accessed_at": metadata.get("accessed_at"),
        "expires_at": metadata.get("expires_at"),
        "lineage": json.dumps(lineage, sort_keys=True),
    }


def _migrate_to_v2(connection: sqlite3.Connection) -> None:
    columns = {row[1] for row in connection.execute("PRAGMA table_info(memories)").fetchall()}
    for name, declaration in V2_COLUMNS.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE memories ADD COLUMN {name} {declaration}")
    for record_id, timestamp, raw_metadata in connection.execute(
        "SELECT id, timestamp, metadata FROM memories"
    ).fetchall():
        fields = _normalized_fields(json.loads(raw_metadata or "{}"), timestamp)
        assignments = ", ".join(f"{name} = ?" for name in fields)
        connection.execute(
            f"UPDATE memories SET {assignments} WHERE id = ?",
            (*fields.values(), record_id),
        )


def _init_fts(connection: sqlite3.Connection) -> bool:
    try:
        existed = _table_exists(connection, "memories_fts")
        connection.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(category, title, content, content='memories', content_rowid='id')"
        )
        connection.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
              INSERT INTO memories_fts(rowid, category, title, content)
              VALUES (new.id, new.category, new.title, new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
              INSERT INTO memories_fts(memories_fts, rowid, category, title, content)
              VALUES ('delete', old.id, old.category, old.title, old.content);
            END;
            CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
              INSERT INTO memories_fts(memories_fts, rowid, category, title, content)
              VALUES ('delete', old.id, old.category, old.title, old.content);
              INSERT INTO memories_fts(rowid, category, title, content)
              VALUES (new.id, new.category, new.title, new.content);
            END;
            """
        )
        if not existed:
            connection.execute("INSERT INTO memories_fts(memories_fts) VALUES ('rebuild')")
        return True
    except sqlite3.OperationalError:
        return False


def init_store(root: str | Path | None = None) -> None:
    recall_config.ensure_config(root)
    cfg = recall_config.load_config(root)
    if cfg["backend"] == "sqlite":
        init_sqlite(root)
    else:
        jsonl_dir(root).mkdir(parents=True, exist_ok=True)


def init_sqlite(root: str | Path | None = None) -> None:
    path = db_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect_sqlite(root)) as connection:
        previous_version = _stored_schema_version(connection)
        if previous_version == SCHEMA_VERSION:
            return
        if 0 < previous_version < SCHEMA_VERSION:
            _backup_before_migration(connection, root, previous_version)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}',
                embedding TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS recall_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        columns = {row[1] for row in connection.execute("PRAGMA table_info(memories)").fetchall()}
        if "embedding" not in columns:
            connection.execute("ALTER TABLE memories ADD COLUMN embedding TEXT NOT NULL DEFAULT '[]'")
        if previous_version < 2:
            _migrate_to_v2(connection)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_memories_timestamp ON memories(timestamp)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(status)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_memories_source_path ON memories(source_path)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_memories_updated_at ON memories(updated_at)")
        fts5_available = _init_fts(connection)
        connection.execute(
            "INSERT OR REPLACE INTO recall_meta (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        connection.execute(
            "INSERT OR REPLACE INTO recall_meta (key, value) VALUES ('fts5_available', ?)",
            ("1" if fts5_available else "0",),
        )
        connection.commit()


def add_record(
    category: str,
    timestamp: str,
    content: str,
    metadata: dict[str, Any],
    embedding: list[float],
    root: str | Path | None = None,
) -> MemoryRecord:
    content = security.redact_text(content)
    metadata = security.redact_value(metadata)
    cfg = recall_config.load_config(root)
    if cfg["backend"] == "sqlite":
        init_sqlite(root)
        normalized = _normalized_fields(metadata, timestamp)
        with closing(connect_sqlite(root)) as connection:
            cursor = connection.execute(
                """
                INSERT INTO memories (
                    category, timestamp, content, metadata, embedding,
                    memory_type, title, status, trust, confidence, importance,
                    source_kind, source_path, source_hash, source_revision,
                    created_at, updated_at, confirmed_at, accessed_at, expires_at, lineage
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    category,
                    timestamp,
                    content,
                    json.dumps(metadata, sort_keys=True),
                    json.dumps(embedding),
                    *normalized.values(),
                ),
            )
            record_id = int(cursor.lastrowid)
            connection.commit()
    else:
        jsonl_dir(root).mkdir(parents=True, exist_ok=True)
        record_id = next_jsonl_id(root)
        path = jsonl_dir(root) / f"{category}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "id": record_id,
                        "category": category,
                        "timestamp": timestamp,
                        "content": content,
                        "metadata": metadata,
                        "embedding": embedding,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    return MemoryRecord(record_id, category, timestamp, content, metadata, embedding=embedding)


def add_records_batch(
    records: list[tuple[str, str, str, dict[str, Any], list[float]]],
    root: str | Path | None = None,
) -> list[MemoryRecord]:
    """Insert records in one SQLite transaction."""

    if not records:
        return []
    cfg = recall_config.load_config(root)
    if cfg["backend"] != "sqlite":
        return [add_record(category, timestamp, content, metadata, embedding, root) for category, timestamp, content, metadata, embedding in records]
    init_sqlite(root)
    inserted: list[MemoryRecord] = []
    with closing(connect_sqlite(root)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for category, timestamp, content, metadata, embedding in records:
                safe_content = security.redact_text(content)
                safe_metadata = security.redact_value(metadata)
                normalized = _normalized_fields(safe_metadata, timestamp)
                cursor = connection.execute(
                    """INSERT INTO memories (
                        category, timestamp, content, metadata, embedding,
                        memory_type, title, status, trust, confidence, importance,
                        source_kind, source_path, source_hash, source_revision,
                        created_at, updated_at, confirmed_at, accessed_at, expires_at, lineage
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (category, timestamp, safe_content, json.dumps(safe_metadata, sort_keys=True), json.dumps(embedding), *normalized.values()),
                )
                inserted.append(MemoryRecord(int(cursor.lastrowid), category, timestamp, safe_content, safe_metadata, embedding=embedding))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return inserted


def iter_records(root: str | Path | None = None) -> Iterable[MemoryRecord]:
    init_store(root)
    cfg = recall_config.load_config(root)
    if cfg["backend"] == "sqlite":
        with closing(connect_sqlite(root)) as connection:
            rows = connection.execute(
                "SELECT id, category, timestamp, content, metadata, embedding FROM memories ORDER BY timestamp DESC"
            ).fetchall()
        for row in rows:
            yield MemoryRecord(
                int(row[0]),
                row[1],
                row[2],
                row[3],
                json.loads(row[4] or "{}"),
                embedding=json.loads(row[5] or "[]"),
            )
        return
    yield from iter_jsonl_records(root)


def get_record(record_id: int, root: str | Path | None = None) -> MemoryRecord | None:
    init_store(root)
    cfg = recall_config.load_config(root)
    if cfg["backend"] == "sqlite":
        with closing(connect_sqlite(root)) as connection:
            row = connection.execute(
                "SELECT id, category, timestamp, content, metadata, embedding FROM memories WHERE id = ?",
                (record_id,),
            ).fetchone()
        if row is None:
            return None
        return MemoryRecord(
            int(row[0]),
            row[1],
            row[2],
            row[3],
            json.loads(row[4] or "{}"),
            embedding=json.loads(row[5] or "[]"),
        )
    for record in iter_jsonl_records(root):
        if record.id == record_id:
            return record
    return None


def update_record_metadata(record_id: int, metadata: dict[str, Any], root: str | Path | None = None) -> MemoryRecord:
    metadata = security.redact_value(metadata)
    init_store(root)
    cfg = recall_config.load_config(root)
    if cfg["backend"] == "sqlite":
        with closing(connect_sqlite(root)) as connection:
            row = connection.execute(
                "SELECT id, category, timestamp, content, embedding FROM memories WHERE id = ?",
                (record_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"RECALL memory #{record_id} was not found.")
            normalized = _normalized_fields(metadata, row[2])
            assignments = ", ".join(f"{name} = ?" for name in normalized)
            connection.execute(
                f"UPDATE memories SET metadata = ?, {assignments} WHERE id = ?",
                (json.dumps(metadata, sort_keys=True), *normalized.values(), record_id),
            )
            connection.commit()
        return MemoryRecord(
            int(row[0]),
            row[1],
            row[2],
            row[3],
            metadata,
            embedding=json.loads(row[4] or "[]"),
        )

    record = get_record(record_id, root)
    if record is None:
        raise KeyError(f"RECALL memory #{record_id} was not found.")
    path = jsonl_dir(root) / f"{record.category}.jsonl"
    rewritten: list[dict[str, Any]] = []
    if path.exists():
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if int(payload.get("id", -1)) == record_id:
                    payload["metadata"] = metadata
                rewritten.append(payload)
    with path.open("w", encoding="utf-8") as handle:
        for payload in rewritten:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return MemoryRecord(
        record.id,
        record.category,
        record.timestamp,
        record.content,
        metadata,
        embedding=record.embedding,
    )


def update_record(
    record_id: int,
    *,
    category: str,
    content: str,
    metadata: dict[str, Any],
    embedding: list[float],
    root: str | Path | None = None,
) -> MemoryRecord:
    content = security.redact_text(content)
    metadata = security.redact_value(metadata)
    init_store(root)
    existing = get_record(record_id, root)
    if existing is None:
        raise KeyError(f"RECALL memory #{record_id} was not found.")
    cfg = recall_config.load_config(root)
    if cfg["backend"] == "sqlite":
        with closing(connect_sqlite(root)) as connection:
            normalized = _normalized_fields(metadata, existing.timestamp)
            assignments = ", ".join(f"{name} = ?" for name in normalized)
            connection.execute(
                f"""
                UPDATE memories
                SET category = ?, content = ?, metadata = ?, embedding = ?, {assignments}
                WHERE id = ?
                """,
                (
                    category,
                    content,
                    json.dumps(metadata, sort_keys=True),
                    json.dumps(embedding),
                    *normalized.values(),
                    record_id,
                ),
            )
            connection.commit()
        return MemoryRecord(
            existing.id,
            category,
            existing.timestamp,
            content,
            metadata,
            embedding=embedding,
        )

    payloads_by_path: dict[Path, list[dict[str, Any]]] = {}
    found = False
    for path in sorted(jsonl_dir(root).glob("*.jsonl")):
        payloads: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if int(payload.get("id", -1)) == record_id:
                    found = True
                    if path.stem == category:
                        payload.update(
                            {
                                "category": category,
                                "content": content,
                                "metadata": metadata,
                                "embedding": embedding,
                            }
                        )
                        payloads.append(payload)
                    continue
                payloads.append(payload)
        payloads_by_path[path] = payloads
    if not found:
        raise KeyError(f"RECALL memory #{record_id} was not found.")
    target_path = jsonl_dir(root) / f"{category}.jsonl"
    if existing.category != category:
        payloads_by_path.setdefault(target_path, []).append(
            {
                "id": existing.id,
                "category": category,
                "timestamp": existing.timestamp,
                "content": content,
                "metadata": metadata,
                "embedding": embedding,
            }
        )
    for path, payloads in payloads_by_path.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for payload in payloads:
                handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return MemoryRecord(existing.id, category, existing.timestamp, content, metadata, embedding=embedding)


def delete_record(record_id: int, root: str | Path | None = None) -> MemoryRecord:
    init_store(root)
    existing = get_record(record_id, root)
    if existing is None:
        raise KeyError(f"RECALL memory #{record_id} was not found.")
    cfg = recall_config.load_config(root)
    if cfg["backend"] == "sqlite":
        with closing(connect_sqlite(root)) as connection:
            connection.execute("DELETE FROM memories WHERE id = ?", (record_id,))
            connection.commit()
        return existing

    path = jsonl_dir(root) / f"{existing.category}.jsonl"
    payloads: list[dict[str, Any]] = []
    if path.exists():
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if int(payload.get("id", -1)) != record_id:
                    payloads.append(payload)
        with path.open("w", encoding="utf-8") as handle:
            for payload in payloads:
                handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return existing


def iter_jsonl_records(root: str | Path | None = None) -> Iterable[MemoryRecord]:
    base = jsonl_dir(root)
    if not base.exists():
        return
    for path in sorted(base.glob("*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                    yield MemoryRecord(
                        int(payload["id"]),
                        payload["category"],
                        payload["timestamp"],
                        payload["content"],
                        payload.get("metadata", {}),
                        embedding=payload.get("embedding"),
                    )
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    continue


def jsonl_diagnostics(root: str | Path | None = None) -> dict[str, Any]:
    base = jsonl_dir(root)
    malformed_rows = 0
    invalid_rows = 0
    if not base.exists():
        return {"malformed_jsonl_rows": 0, "invalid_jsonl_rows": 0}
    for path in sorted(base.glob("*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    malformed_rows += 1
                    continue
                required = ("id", "category", "timestamp", "content")
                if not isinstance(payload, dict) or any(key not in payload for key in required):
                    invalid_rows += 1
    return {"malformed_jsonl_rows": malformed_rows, "invalid_jsonl_rows": invalid_rows}


def next_jsonl_id(root: str | Path | None = None) -> int:
    return max((record.id for record in iter_jsonl_records(root)), default=0) + 1


def schema_version(root: str | Path | None = None) -> int:
    cfg = recall_config.load_config(root)
    if cfg["backend"] != "sqlite":
        return SCHEMA_VERSION
    init_sqlite(root)
    with closing(connect_sqlite(root)) as connection:
        row = connection.execute(
            "SELECT value FROM recall_meta WHERE key = 'schema_version'"
        ).fetchone()
    return int(row[0]) if row else 0


def sqlite_diagnostics(root: str | Path | None = None) -> dict[str, Any]:
    """Return SQLite migration, concurrency, and FTS state."""

    init_sqlite(root)
    with closing(connect_sqlite(root)) as connection:
        journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        foreign_keys = bool(connection.execute("PRAGMA foreign_keys").fetchone()[0])
        busy_timeout_ms = int(connection.execute("PRAGMA busy_timeout").fetchone()[0])
        row = connection.execute(
            "SELECT value FROM recall_meta WHERE key = 'fts5_available'"
        ).fetchone()
    backups = sorted((recall_config.memory_dir(root) / "backups").glob("memory-v*.sqlite"))
    return {
        "journal_mode": journal_mode,
        "foreign_keys": foreign_keys,
        "busy_timeout_ms": busy_timeout_ms,
        "fts5_available": bool(row and row[0] == "1"),
        "migration_backups": [path.name for path in backups],
    }


def backend(root: str | Path | None = None) -> str:
    return str(recall_config.load_config(root)["backend"])
