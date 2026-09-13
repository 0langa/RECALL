#!/usr/bin/env python3
"""Durable RECALL memory storage backends."""

from __future__ import annotations

import json
import inspect
import os
import tempfile
import shutil
import sqlite3
from contextlib import closing, contextmanager
from contextvars import ContextVar
from functools import wraps
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, ParamSpec, TypeVar

import config as recall_config
import security
from store_lock import exclusive_lock


SCHEMA_VERSION = 2
SQLITE_BUSY_TIMEOUT_MS = 15000

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


@dataclass
class _WriteState:
    path: Path
    connection: sqlite3.Connection | None
    callbacks: list[Callable[[], None]] = field(default_factory=list)


_writes: ContextVar[tuple[_WriteState, ...]] = ContextVar("recall_writes", default=())
_P = ParamSpec("_P")
_T = TypeVar("_T")


def _active_write(root: str | Path | None) -> _WriteState | None:
    path = recall_config.memory_dir(root).resolve()
    return next((state for state in reversed(_writes.get()) if state.path == path), None)


@contextmanager
def _connection(root: str | Path | None) -> Iterator[sqlite3.Connection]:
    state = _active_write(root)
    if state is not None and state.connection is not None:
        yield state.connection
    else:
        with closing(connect_sqlite(root)) as connection:
            yield connection


@contextmanager
def write_transaction(root: str | Path | None = None) -> Iterator[None]:
    """Serialize the whole read/choice/write, including nested store operations.

    SQLite readers and writers share this BEGIN IMMEDIATE connection. JSONL
    uses an OS lock and atomic file replacement, without multi-file rollback.
    Nested scopes join the outer transaction; only its owner commits.
    """
    if _active_write(root) is not None:
        yield
        return
    init_store(root)
    path = recall_config.memory_dir(root).resolve()
    callbacks: list[Callable[[], None]] = []
    if backend(root) == "sqlite":
        with closing(connect_sqlite(root)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            token = _writes.set((*_writes.get(), _WriteState(path, connection, callbacks)))
            try:
                yield
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            finally:
                _writes.reset(token)
    else:
        with exclusive_lock(path / ".write.lock"):
            token = _writes.set((*_writes.get(), _WriteState(path, None, callbacks)))
            try:
                yield
            finally:
                _writes.reset(token)
    # Canonical storage has committed and its exclusion has been released.
    for callback in callbacks:
        callback()


def after_commit(callback: Callable[[], None], root: str | Path | None = None) -> None:
    state = _active_write(root)
    if state is None:
        callback()
    else:
        state.callbacks.append(callback)


def atomic_write(function: Callable[_P, _T]) -> Callable[_P, _T]:
    """Join the store transaction before any read used to choose a write."""
    signature = inspect.signature(function)

    @wraps(function)
    def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        root = signature.bind(*args, **kwargs).arguments.get("root")
        with write_transaction(root):
            return function(*args, **kwargs)

    return wrapped


@contextmanager
def _jsonl_replacement(path: Path) -> Iterator[Any]:
    """Keep the old file intact until the complete replacement is flushed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=".rewrite-", suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
        try:
            yield handle
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            handle.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


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


def _ensure_runtime_indexes(connection: sqlite3.Connection) -> None:
    """Additive, idempotent indexes safe to (re)create on every init.

    Kept outside the schema_version-gated migration block below so already
    -installed stores pick up new indexes on next open, not only on a
    version bump (no data migration involved, purely a perf/lookup aid).
    """

    if not _table_exists(connection, "memories"):
        return
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_memories_idempotency "
        "ON memories(json_extract(metadata, '$.idempotency_key'))"
    )


def init_sqlite(root: str | Path | None = None) -> None:
    if _active_write(root) is not None:
        return
    with exclusive_lock(recall_config.memory_dir(root) / ".init.lock"):
        _init_sqlite_unlocked(root)


def _init_sqlite_unlocked(root: str | Path | None = None) -> None:
    path = db_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connection(root) as connection:
        previous_version = _stored_schema_version(connection)
        if previous_version < SCHEMA_VERSION:
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
        _ensure_runtime_indexes(connection)
        connection.commit()


@atomic_write
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
        with _connection(root) as connection:
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
            record_id = int(cursor.lastrowid or 0)
    else:
        jsonl_dir(root).mkdir(parents=True, exist_ok=True)
        record_id = next_jsonl_id(root)
        path = jsonl_dir(root) / f"{category}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with _jsonl_replacement(path) as handle:
            if path.exists():
                with path.open(encoding="utf-8") as previous:
                    shutil.copyfileobj(previous, handle)
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


def find_by_idempotency_key(idempotency_key: str, root: str | Path | None = None) -> MemoryRecord | None:
    init_store(root)
    cfg = recall_config.load_config(root)
    if cfg["backend"] == "sqlite":
        init_sqlite(root)
        with _connection(root) as connection:
            row = connection.execute(
                "SELECT id, category, timestamp, content, metadata, embedding FROM memories "
                "WHERE json_extract(metadata, '$.idempotency_key') = ? ORDER BY id DESC LIMIT 1",
                (idempotency_key,),
            ).fetchone()
            if row is None:
                row = connection.execute(
                    "SELECT id, category, timestamp, content, metadata, embedding FROM memories "
                    "WHERE json_type(metadata, '$.idempotency_keys') = 'array' AND EXISTS ("
                    "SELECT 1 FROM json_each(memories.metadata, '$.idempotency_keys') "
                    "WHERE type = 'text' AND value = ?) ORDER BY id DESC LIMIT 1",
                    (idempotency_key,),
                ).fetchone()
        if row is None:
            return None
        return MemoryRecord(
            int(row[0]), row[1], row[2], row[3],
            json.loads(row[4] or "{}"), embedding=json.loads(row[5] or "[]"),
        )
    for record in iter_jsonl_records(root):
        if idempotency_key in _record_idempotency_keys(record.metadata):
            return record
    return None


def _record_idempotency_keys(metadata: dict[str, Any]) -> list[str]:
    primary = str(metadata.get("idempotency_key") or "")
    aliases = metadata.get("idempotency_keys", [])
    if not isinstance(aliases, list):
        aliases = []
    return list(dict.fromkeys([key for key in [primary, *aliases] if isinstance(key, str) and key]))


def metadata_with_idempotency_key(metadata: dict[str, Any], idempotency_key: str | None) -> dict[str, Any]:
    """Keep every successful save key in the same write as its record effect."""
    metadata = dict(metadata)
    if not idempotency_key:
        return metadata
    keys = _record_idempotency_keys(metadata)
    if idempotency_key not in keys:
        keys.append(idempotency_key)
    metadata["idempotency_key"] = keys[0]
    if len(keys) > 1:
        metadata["idempotency_keys"] = keys
    return metadata


@atomic_write
def add_record_if_new(
    category: str,
    timestamp: str,
    content: str,
    metadata: dict[str, Any],
    embedding: list[float],
    idempotency_key: str,
    root: str | Path | None = None,
) -> tuple[MemoryRecord, bool]:
    """Check and insert the idempotency key under the same store exclusion."""
    existing = find_by_idempotency_key(idempotency_key, root)
    if existing is not None:
        return existing, False
    metadata = dict(metadata)
    metadata["idempotency_key"] = idempotency_key
    return add_record(category, timestamp, content, metadata, embedding, root), True


@atomic_write
def add_records_batch(
    records: list[tuple[str, str, str, dict[str, Any], list[float]]],
    root: str | Path | None = None,
) -> list[MemoryRecord]:
    """Insert records in one SQLite transaction (JSONL has per-file commits)."""
    return [add_record(category, timestamp, content, metadata, embedding, root)
            for category, timestamp, content, metadata, embedding in records]


def iter_records(root: str | Path | None = None) -> Iterable[MemoryRecord]:
    init_store(root)
    cfg = recall_config.load_config(root)
    if cfg["backend"] == "sqlite":
        with _connection(root) as connection:
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
        with _connection(root) as connection:
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


@atomic_write
def update_record_metadata(record_id: int, metadata: dict[str, Any], root: str | Path | None = None) -> MemoryRecord:
    metadata = security.redact_value(metadata)
    init_store(root)
    cfg = recall_config.load_config(root)
    if cfg["backend"] == "sqlite":
        with _connection(root) as connection:
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
    with _jsonl_replacement(path) as handle:
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


@atomic_write
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
        with _connection(root) as connection:
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
        with _jsonl_replacement(path) as handle:
            for payload in payloads:
                handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return MemoryRecord(existing.id, category, existing.timestamp, content, metadata, embedding=embedding)


@atomic_write
def delete_record(record_id: int, root: str | Path | None = None) -> MemoryRecord:
    init_store(root)
    existing = get_record(record_id, root)
    if existing is None:
        raise KeyError(f"RECALL memory #{record_id} was not found.")
    cfg = recall_config.load_config(root)
    if cfg["backend"] == "sqlite":
        with _connection(root) as connection:
            connection.execute("DELETE FROM memories WHERE id = ?", (record_id,))
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
        with _jsonl_replacement(path) as handle:
            for payload in payloads:
                handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return existing


def iter_jsonl_records(root: str | Path | None = None) -> Iterable[MemoryRecord]:
    with write_transaction(root):
        records = list(_iter_jsonl_records_unlocked(root))
    yield from records


def _iter_jsonl_records_unlocked(root: str | Path | None = None) -> Iterable[MemoryRecord]:
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
    with _connection(root) as connection:
        row = connection.execute(
            "SELECT value FROM recall_meta WHERE key = 'schema_version'"
        ).fetchone()
    return int(row[0]) if row else 0


def sqlite_diagnostics(root: str | Path | None = None) -> dict[str, Any]:
    """Return SQLite migration, concurrency, and FTS state."""

    init_sqlite(root)
    with _connection(root) as connection:
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


def integrity_check(root: str | Path | None = None) -> dict[str, Any]:
    """Run PRAGMA integrity_check; also catches file-level corruption that
    would otherwise raise unhandled from the first connect (truncated by
    disk-full, killed mid-write) so `doctor()` can report it instead of
    crashing the caller."""

    if backend(root) != "sqlite":
        return {"ok": True, "errors": []}
    path = db_path(root)
    if not path.exists():
        return {"ok": True, "errors": []}
    try:
        with closing(sqlite3.connect(path, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)) as connection:
            rows = connection.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.DatabaseError as exc:
        return {"ok": False, "errors": [str(exc)]}
    errors = [str(row[0]) for row in rows if str(row[0]).lower() != "ok"]
    return {"ok": not errors, "errors": errors}


def latest_backup(root: str | Path | None = None) -> Path | None:
    backups = sorted((recall_config.memory_dir(root) / "backups").glob("memory-v*.sqlite"))
    return backups[-1] if backups else None


def restore_from_backup(root: str | Path | None = None) -> Path:
    """Restore memory.sqlite from the newest migration backup.

    Only ever called from an explicit `repair --restore-backup` step, never
    automatically — it overwrites the live (corrupted) database file. The
    corrupt file is preserved alongside it as `memory.sqlite.corrupt` first.
    """

    backup = latest_backup(root)
    if backup is None:
        raise RuntimeError("No backup available to restore from.")
    target = db_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.copy2(target, target.with_suffix(".sqlite.corrupt"))
    shutil.copy2(backup, target)
    return backup


def fts5_rerank_scores(record_texts: dict[int, str], tokens: set[str]) -> dict[int, float]:
    """Raw bm25() score per record id matched by any token (lower = better).

    Built as an ephemeral in-memory FTS5 table over exactly the caller's
    `record_texts` (typically `retrieval.searchable_text` per candidate),
    not the persisted `memories_fts` mirror — that table only indexes
    content+title, which rewards raw keyword-stuffed content over the same
    terms spread across summary/details/tags. Rebuilding fresh per query
    keeps this signal aligned with the same full field text the lexical
    scorer already weighs, at the cost of doing the work every call; caller
    supplies pre-filtered candidates to keep this cheap for large stores.
    Empty dict when there are no tokens, no candidates, or FTS5 support is
    missing from this SQLite build — callers must treat that as "no
    additional signal to blend in", never as "zero relevant records".
    """
    if not tokens or not record_texts:
        return {}
    connection = sqlite3.connect(":memory:")
    try:
        try:
            connection.execute("CREATE VIRTUAL TABLE docs USING fts5(text)")
        except sqlite3.OperationalError:
            return {}
        record_ids = list(record_texts.keys())
        connection.executemany(
            "INSERT INTO docs(rowid, text) VALUES (?, ?)",
            [(position, record_texts[record_id]) for position, record_id in enumerate(record_ids, start=1)],
        )
        match_query = " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens)
        try:
            rows = connection.execute(
                "SELECT rowid, bm25(docs) FROM docs WHERE docs MATCH ?", (match_query,)
            ).fetchall()
        except sqlite3.OperationalError:
            return {}
    finally:
        connection.close()
    return {record_ids[int(rowid) - 1]: float(score) for rowid, score in rows}
