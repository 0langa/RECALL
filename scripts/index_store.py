#!/usr/bin/env python3
"""Portable vector index maintenance for RECALL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import config as recall_config
from embedder import DIMENSIONS
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
        "embedding_model": cfg.get("embedding_model", "local-hash-v1"),
        "dimensions": len(embedding) or DIMENSIONS,
        "embedding": embedding,
    }


def append_record(record: storage.MemoryRecord, root: str | Path | None = None) -> None:
    path = index_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(build_index_record(record, root), sort_keys=True) + "\n")


def load_index(root: str | Path | None = None) -> dict[int, dict[str, Any]]:
    path = index_path(root)
    if not path.exists():
        return {}
    loaded: dict[int, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            record_id = payload.get("id")
            embedding = payload.get("embedding")
            if not isinstance(record_id, int) or not isinstance(embedding, list):
                continue
            loaded[record_id] = payload
    return loaded


def rebuild(root: str | Path | None = None) -> dict[str, Any]:
    storage.init_store(root)
    records = list(storage.iter_records(root))
    path = index_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(build_index_record(record, root), sort_keys=True) + "\n")
    return {"index_path": str(path), "indexed_records": len(records)}


def diagnostics(root: str | Path | None = None) -> dict[str, Any]:
    records = list(storage.iter_records(root))
    index = load_index(root)
    record_ids = {record.id for record in records}
    index_ids = set(index)
    return {
        "index_path": str(index_path(root)),
        "records": len(records),
        "index_records": len(index),
        "missing_index_ids": sorted(record_ids - index_ids),
        "stale_index_ids": sorted(index_ids - record_ids),
        "index_complete": record_ids == index_ids,
    }


def ensure_complete(root: str | Path | None = None) -> dict[int, dict[str, Any]]:
    report = diagnostics(root)
    if not report["index_complete"]:
        rebuild(root)
    return load_index(root)
