#!/usr/bin/env python3
"""Lifecycle operations for RECALL memory records."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import storage


RELATION_FIELDS = {"related_to", "supersedes", "superseded_by", "merged_from"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_ids(values: int | str | Iterable[int | str] | None) -> list[int]:
    if values is None:
        return []
    if isinstance(values, (int, str)):
        values = [values]
    normalized: list[int] = []
    for value in values:
        record_id = int(value)
        if record_id not in normalized:
            normalized.append(record_id)
    return normalized


def add_ids(existing: Any, values: int | str | Iterable[int | str] | None) -> list[int]:
    combined = normalize_ids(existing if isinstance(existing, list) else ([] if existing in (None, "") else existing))
    for record_id in normalize_ids(values):
        if record_id not in combined:
            combined.append(record_id)
    return combined


def get_required(record_id: int, root: str | Path | None = None) -> storage.MemoryRecord:
    record = storage.get_record(int(record_id), root)
    if record is None:
        raise KeyError(f"RECALL memory #{record_id} was not found.")
    return record


def update_metadata(record_id: int, updates: dict[str, Any], root: str | Path | None = None) -> storage.MemoryRecord:
    record = get_required(record_id, root)
    metadata = dict(record.metadata or {})
    metadata.update({key: value for key, value in updates.items() if value not in (None, "", [])})
    metadata["updated_at"] = utc_now()
    return storage.update_record_metadata(record.id, metadata, root)


def confirm(record_id: int, root: str | Path | None = None, source_session: str | None = None) -> storage.MemoryRecord:
    record = get_required(record_id, root)
    metadata = dict(record.metadata or {})
    metadata["last_confirmed"] = utc_now()
    metadata["confirmed_count"] = int(metadata.get("confirmed_count", 0) or 0) + 1
    if source_session:
        metadata["source_session"] = source_session
    if metadata.get("status") in (None, "", "stale", "hypothesis"):
        metadata["status"] = "active"
    if metadata["confirmed_count"] >= 2 and metadata.get("status") == "active":
        metadata["status"] = "validated"
        metadata["validated_at"] = utc_now()
        metadata["trust"] = max(0.85, float(metadata.get("trust", metadata.get("confidence", 0.5))))
    metadata["updated_at"] = utc_now()
    return storage.update_record_metadata(record.id, metadata, root)


def resolve(record_id: int, root: str | Path | None = None, note: str | None = None) -> storage.MemoryRecord:
    return update_metadata(
        record_id,
        {
            "status": "resolved",
            "resolved_at": utc_now(),
            "lifecycle_note": note,
        },
        root,
    )


def mark_stale(record_id: int, root: str | Path | None = None, note: str | None = None) -> storage.MemoryRecord:
    return update_metadata(
        record_id,
        {
            "status": "stale",
            "stale_at": utc_now(),
            "lifecycle_note": note,
        },
        root,
    )


def prune(record_id: int, root: str | Path | None = None, note: str | None = None) -> storage.MemoryRecord:
    return update_metadata(
        record_id,
        {
            "status": "archived",
            "archived_at": utc_now(),
            "lifecycle_note": note,
        },
        root,
    )


def supersede(
    old_record_id: int,
    new_record_id: int,
    root: str | Path | None = None,
    note: str | None = None,
) -> dict[str, storage.MemoryRecord]:
    old_record = get_required(old_record_id, root)
    new_record = get_required(new_record_id, root)
    old_metadata = dict(old_record.metadata or {})
    old_metadata.update(
        {
            "status": "superseded",
            "superseded_by": new_record.id,
            "superseded_at": utc_now(),
            "lifecycle_note": note,
            "updated_at": utc_now(),
        }
    )
    new_metadata = dict(new_record.metadata or {})
    new_metadata["supersedes"] = add_ids(new_metadata.get("supersedes"), old_record.id)
    new_metadata["last_confirmed"] = utc_now()
    new_metadata["updated_at"] = utc_now()
    return {
        "old": storage.update_record_metadata(old_record.id, old_metadata, root),
        "new": storage.update_record_metadata(new_record.id, new_metadata, root),
    }


def merge(
    primary_id: int,
    secondary_ids: Iterable[int | str],
    root: str | Path | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    primary = get_required(primary_id, root)
    secondary_ints = [record_id for record_id in normalize_ids(list(secondary_ids)) if record_id != primary.id]
    primary_metadata = dict(primary.metadata or {})
    primary_metadata["merged_from"] = add_ids(primary_metadata.get("merged_from"), secondary_ints)
    primary_metadata["related_to"] = add_ids(primary_metadata.get("related_to"), secondary_ints)
    primary_metadata["last_confirmed"] = utc_now()
    primary_metadata["updated_at"] = utc_now()
    updated_primary = storage.update_record_metadata(primary.id, primary_metadata, root)
    updated_secondaries = []
    for secondary_id in secondary_ints:
        secondary = get_required(secondary_id, root)
        metadata = dict(secondary.metadata or {})
        metadata.update(
            {
                "status": "superseded",
                "superseded_by": primary.id,
                "superseded_at": utc_now(),
                "lifecycle_note": note or f"Merged into memory #{primary.id}.",
                "updated_at": utc_now(),
            }
        )
        updated_secondaries.append(storage.update_record_metadata(secondary.id, metadata, root))
    return {"primary": updated_primary, "merged": updated_secondaries}
