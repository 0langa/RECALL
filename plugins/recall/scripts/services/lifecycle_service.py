"""Trust lifecycle and contradiction governance."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import memory_lifecycle
import storage


CURRENT_STATUSES = {"hypothesis", "active", "validated", "open"}


def _claim_slot(record: storage.MemoryRecord) -> tuple[str, str] | None:
    metadata = record.metadata or {}
    key = str(metadata.get("claim_key") or "").strip().casefold()
    value = str(metadata.get("claim_value") or "").strip().casefold()
    return (key, value) if key and value else None


def find_conflicts(root: str | Path | None = None) -> list[dict[str, Any]]:
    """Return unresolved explicit claim-slot conflicts."""

    groups: dict[tuple[str, str], list[storage.MemoryRecord]] = defaultdict(list)
    for record in storage.iter_records(root):
        status = str((record.metadata or {}).get("status", "active")).lower()
        slot = _claim_slot(record)
        if slot and status in CURRENT_STATUSES:
            groups[(record.category, slot[0])].append(record)

    clusters = []
    for (category, claim_key), records in sorted(groups.items()):
        values = {str((record.metadata or {}).get("claim_value", "")).casefold() for record in records}
        if len(values) < 2:
            continue
        clusters.append(
            {
                "category": category,
                "claim_key": claim_key,
                "record_ids": [record.id for record in records],
                "values": sorted(values),
                "validated_ids": [
                    record.id
                    for record in records
                    if str((record.metadata or {}).get("status", "")).lower() == "validated"
                ],
                "resolution": "review_required",
            }
        )
    return clusters


def promote(record_id: int, root: str | Path | None = None, note: str | None = None) -> storage.MemoryRecord:
    """Promote a claim to validated unless validated truth contradicts it."""

    record = memory_lifecycle.get_required(record_id, root)
    slot = _claim_slot(record)
    if slot:
        for other in storage.iter_records(root):
            if other.id == record.id or _claim_slot(other) is None:
                continue
            other_slot = _claim_slot(other)
            other_status = str((other.metadata or {}).get("status", "")).lower()
            if (
                other.category == record.category
                and other_slot[0] == slot[0]
                and other_slot[1] != slot[1]
                and other_status == "validated"
            ):
                raise ValueError(f"memory #{record.id} contradicts validated memory #{other.id}")
    metadata = dict(record.metadata or {})
    metadata["status"] = "validated"
    metadata["trust"] = max(0.85, float(metadata.get("trust", metadata.get("confidence", 0.5))))
    metadata["validated_at"] = memory_lifecycle.utc_now()
    if note:
        metadata["lifecycle_note"] = note
    return storage.update_record_metadata(record.id, metadata, root)


def deprecate(record_id: int, root: str | Path | None = None, note: str | None = None) -> storage.MemoryRecord:
    """Mark a memory deprecated while preserving history."""

    return memory_lifecycle.update_metadata(
        record_id,
        {"status": "deprecated", "deprecated_at": memory_lifecycle.utc_now(), "lifecycle_note": note},
        root,
    )


def resolve_conflict(
    winner_id: int,
    loser_ids: Iterable[int],
    root: str | Path | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Supersede losing claims and validate the selected winner."""

    losers = []
    for loser_id in loser_ids:
        result = memory_lifecycle.supersede(loser_id, winner_id, root, note)
        losers.append(result["old"])
    winner = promote(winner_id, root, note)
    return {"winner": winner, "losers": losers}
