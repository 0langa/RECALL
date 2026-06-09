#!/usr/bin/env python3
"""Durable RECALL memory storage backends."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import config as recall_config


SCHEMA_VERSION = 1


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
    with closing(sqlite3.connect(path)) as connection:
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
        connection.execute("CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_memories_timestamp ON memories(timestamp)")
        connection.execute(
            "INSERT OR REPLACE INTO recall_meta (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
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
    init_store(root)
    cfg = recall_config.load_config(root)
    if cfg["backend"] == "sqlite":
        with closing(sqlite3.connect(db_path(root))) as connection:
            cursor = connection.execute(
                """
                INSERT INTO memories (category, timestamp, content, metadata, embedding)
                VALUES (?, ?, ?, ?, ?)
                """,
                (category, timestamp, content, json.dumps(metadata, sort_keys=True), json.dumps(embedding)),
            )
            record_id = int(cursor.lastrowid)
            connection.commit()
    else:
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


def iter_records(root: str | Path | None = None) -> Iterable[MemoryRecord]:
    init_store(root)
    cfg = recall_config.load_config(root)
    if cfg["backend"] == "sqlite":
        with closing(sqlite3.connect(db_path(root))) as connection:
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
        with closing(sqlite3.connect(db_path(root))) as connection:
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
    init_store(root)
    cfg = recall_config.load_config(root)
    if cfg["backend"] == "sqlite":
        with closing(sqlite3.connect(db_path(root))) as connection:
            row = connection.execute(
                "SELECT id, category, timestamp, content, embedding FROM memories WHERE id = ?",
                (record_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"RECALL memory #{record_id} was not found.")
            connection.execute(
                "UPDATE memories SET metadata = ? WHERE id = ?",
                (json.dumps(metadata, sort_keys=True), record_id),
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
    return MemoryRecord(record.id, record.category, record.timestamp, record.content, metadata, embedding=record.embedding)


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
    with closing(sqlite3.connect(db_path(root))) as connection:
        row = connection.execute(
            "SELECT value FROM recall_meta WHERE key = 'schema_version'"
        ).fetchone()
    return int(row[0]) if row else 0


def backend(root: str | Path | None = None) -> str:
    return str(recall_config.load_config(root)["backend"])
