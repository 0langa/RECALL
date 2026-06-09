#!/usr/bin/env python3
"""CLI-first review summaries for RECALL project memory."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import config as recall_config
import storage


RELATION_KEYS = ("related_to", "supersedes", "superseded_by", "merged_from")
GENERIC_SUMMARIES = {
    "session stop checkpoint.",
    "session compaction checkpoint.",
    "bash result captured.",
    "tool result captured.",
}


def compact_text(record: storage.MemoryRecord, max_chars: int = 180) -> str:
    summary = record.metadata.get("summary") if isinstance(record.metadata, dict) else None
    if isinstance(summary, str) and summary.strip() and summary.strip().lower() not in GENERIC_SUMMARIES:
        text = summary
    else:
        details = record.metadata.get("details") if isinstance(record.metadata, dict) else None
        text = details if isinstance(details, str) and details.strip() else record.content
    text = " ".join(text.split())
    if len(text) > max_chars:
        return text[: max_chars - 14].rstrip() + " [truncated]"
    return text


def relation_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: metadata[key] for key in RELATION_KEYS if key in metadata}


def memory_card(record: storage.MemoryRecord) -> dict[str, Any]:
    metadata = record.metadata or {}
    return {
        "id": record.id,
        "category": record.category,
        "status": metadata.get("status", "unspecified"),
        "timestamp": record.timestamp,
        "summary": compact_text(record),
        "source": metadata.get("source"),
        "source_session": metadata.get("source_session") or metadata.get("turn_id"),
        "last_confirmed": metadata.get("last_confirmed"),
        "relationships": relation_metadata(metadata),
        "tags": metadata.get("tags", []),
    }


def review_memory(
    root: str | Path | None = None,
    *,
    statuses: list[str] | None = None,
    categories: list[str] | None = None,
    source: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    status_set = {status.strip().lower() for status in statuses or [] if status.strip()}
    category_set = {recall_config.normalize_category(category) for category in categories or [] if category.strip()}
    source_filter = source.strip().lower() if source else None
    records = list(storage.iter_records(root))
    filtered: list[storage.MemoryRecord] = []
    for record in records:
        metadata = record.metadata or {}
        status = str(metadata.get("status", "unspecified")).lower()
        record_source = str(metadata.get("source", "")).lower()
        if status_set and status not in status_set:
            continue
        if category_set and record.category not in category_set:
            continue
        if source_filter and record_source != source_filter:
            continue
        filtered.append(record)

    status_counts = Counter(str((record.metadata or {}).get("status", "unspecified")) for record in records)
    category_counts = Counter(record.category for record in records)
    filtered.sort(key=lambda record: (record.timestamp, record.id), reverse=True)
    return {
        "total": len(records),
        "shown": min(len(filtered), limit),
        "status_counts": dict(sorted(status_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "memories": [memory_card(record) for record in filtered[:limit]],
    }
