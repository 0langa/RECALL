#!/usr/bin/env python3
"""Portable vector index maintenance for RECALL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import config as recall_config
from embedder import DIMENSIONS, EMBEDDING_MODEL, embed
import storage


def index_path(root: str | Path | None = None) -> Path:
    return storage.vector_index_path(root)


def build_index_record(record: storage.MemoryRecord, root: str | Path | None = None) -> dict[str, Any]:
    cfg = recall_config.load_config(root)
    embedding = record.embedding or []
    return {
        "id": record.id,
        "category": record.category,
        "timestamp": record.timestamp,
        "embedding_model": cfg.get("embedding_model", EMBEDDING_MODEL),
        "dimensions": len(embedding) or DIMENSIONS,
        "embedding": embedding,
    }


def _migrate_stale_embeddings(records: list[storage.MemoryRecord], root: str | Path | None = None) -> int:
    """Re-embed records still carrying a previous embedder version's vector.

    This pure-hash embedder ties its output shape 1:1 to `DIMENSIONS`, so a
    length mismatch is the version signal: any stored embedding not shaped
    for the current embedder was computed by an older one and is stale.
    Recomputes from `record.content` (unaffected by the embedder change) and
    persists the fix to the memories table itself, not just the index
    mirror, so scoring never mixes vector generations mid-store.
    """
    migrated = 0
    for record in records:
        if len(record.embedding or []) == DIMENSIONS:
            continue
        record.embedding = embed(record.content)
        storage.update_record(
            record.id,
            category=record.category,
            content=record.content,
            metadata=record.metadata,
            embedding=record.embedding,
            root=root,
        )
        migrated += 1
    return migrated


def append_record(record: storage.MemoryRecord, root: str | Path | None = None) -> None:
    path = index_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(build_index_record(record, root), sort_keys=True) + "\n")


def load_index(root: str | Path | None = None) -> dict[int, dict[str, Any]]:
    return inspect_index(root)["index"]


def validate_index_payload(payload: Any) -> tuple[int | None, bool]:
    if not isinstance(payload, dict):
        return None, False
    record_id = payload.get("id")
    embedding = payload.get("embedding")
    dimensions = payload.get("dimensions")
    embedding_model = payload.get("embedding_model")
    if not isinstance(record_id, int):
        return None, False
    if not isinstance(embedding, list) or not all(isinstance(value, (int, float)) for value in embedding):
        return record_id, False
    if not isinstance(dimensions, int) or dimensions != len(embedding) or dimensions != DIMENSIONS:
        return record_id, False
    if not isinstance(embedding_model, str) or not embedding_model.strip():
        return record_id, False
    return record_id, True


def inspect_index(root: str | Path | None = None) -> dict[str, Any]:
    path = index_path(root)
    if not path.exists():
        return {"index": {}, "invalid_index_rows": 0}
    loaded: dict[int, dict[str, Any]] = {}
    invalid_rows = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                invalid_rows += 1
                continue
            record_id, valid = validate_index_payload(payload)
            if not valid or record_id is None:
                invalid_rows += 1
                continue
            loaded[record_id] = payload
    return {"index": loaded, "invalid_index_rows": invalid_rows}


def rebuild(root: str | Path | None = None) -> dict[str, Any]:
    storage.init_store(root)
    records = list(storage.iter_records(root))
    migrated_embeddings = _migrate_stale_embeddings(records, root)
    path = index_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(build_index_record(record, root), sort_keys=True) + "\n")
    return {"index_path": str(path), "indexed_records": len(records), "migrated_embeddings": migrated_embeddings}


def diagnostics(root: str | Path | None = None) -> dict[str, Any]:
    records = list(storage.iter_records(root))
    return diagnostics_for_records(records, root)


def diagnostics_for_records(records: list[storage.MemoryRecord], root: str | Path | None = None) -> dict[str, Any]:
    inspected = inspect_index(root)
    index = inspected["index"]
    record_ids = {record.id for record in records}
    index_ids = set(index)
    return {
        "index_path": str(index_path(root)),
        "records": len(records),
        "index_records": len(index),
        "missing_index_ids": sorted(record_ids - index_ids),
        "stale_index_ids": sorted(index_ids - record_ids),
        "invalid_index_rows": inspected["invalid_index_rows"],
        "index_complete": record_ids == index_ids and inspected["invalid_index_rows"] == 0,
    }


def ensure_complete(root: str | Path | None = None) -> dict[int, dict[str, Any]]:
    report = diagnostics(root)
    if not report["index_complete"]:
        rebuild(root)
    return load_index(root)


def ensure_complete_for_records(
    records: list[storage.MemoryRecord],
    root: str | Path | None = None,
) -> dict[int, dict[str, Any]]:
    report = diagnostics_for_records(records, root)
    if not report["index_complete"]:
        rebuild(root)
    return load_index(root)
