#!/usr/bin/env python3
"""Memory hygiene helpers for automatic RECALL writes."""

from __future__ import annotations

import hashlib
import json
from typing import Any, NamedTuple

import config as recall_config
from embedder import tokenize
import storage


NEAR_DUPLICATE_THRESHOLD = 0.72


class RelatedRecord(NamedTuple):
    kind: str
    record: storage.MemoryRecord
    similarity: float


def normalized_metadata_value(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.lower().split())
    if isinstance(value, list):
        return sorted(str(item).lower().strip() for item in value if str(item).strip())
    return value


def content_fingerprint(category: str, content: str, metadata: dict[str, Any] | None = None) -> str:
    metadata = metadata or {}
    payload = {
        "category": recall_config.normalize_category(category),
        "content": " ".join(content.lower().split()),
        "source": normalized_metadata_value(metadata.get("source")),
        "tool_name": normalized_metadata_value(metadata.get("tool_name")),
        "command": normalized_metadata_value(metadata.get("command")),
        "status": normalized_metadata_value(metadata.get("status")),
        "tags": normalized_metadata_value(metadata.get("tags", [])),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def token_jaccard(left: str, right: str) -> float:
    left_tokens = set(tokenize(left))
    right_tokens = set(tokenize(right))
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def same_memory_family(record: storage.MemoryRecord, category: str, metadata: dict[str, Any]) -> bool:
    if record.category != recall_config.normalize_category(category):
        return False
    record_metadata = record.metadata or {}
    for key in ("source", "tool_name"):
        requested = str(metadata.get(key) or "").strip().lower()
        existing = str(record_metadata.get(key) or "").strip().lower()
        if requested or existing:
            return requested == existing
    return True


def find_related_record(
    category: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    root: str | None = None,
) -> RelatedRecord | None:
    metadata = metadata or {}
    fingerprint = content_fingerprint(category, content, metadata)
    best: RelatedRecord | None = None
    for record in storage.iter_records(root):
        if not same_memory_family(record, category, metadata):
            continue
        if (record.metadata or {}).get("recall_fingerprint") == fingerprint:
            return RelatedRecord("exact", record, 1.0)
        similarity = token_jaccard(content, record.content)
        if similarity >= NEAR_DUPLICATE_THRESHOLD and (best is None or similarity > best.similarity):
            best = RelatedRecord("near", record, similarity)
    return best
