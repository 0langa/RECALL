"""Portable export, import, backup, and restore workflows."""

from __future__ import annotations

import json
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config as recall_config
import index_store
import security
import storage


FORMAT = "recall.export.v1"


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
