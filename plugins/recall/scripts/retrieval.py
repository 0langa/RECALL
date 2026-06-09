#!/usr/bin/env python3
"""Ranking and result shaping for RECALL retrieval."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import config as recall_config
from embedder import cosine, embed, tokenize
import index_store
import storage
from summarizer import summarize_records


STATUS_WEIGHTS = {
    "active": 1.0,
    "open": 0.95,
    "resolved": 0.65,
    "stale": 0.35,
    "superseded": 0.25,
    "archived": 0.15,
}
DEFAULT_STATUS_WEIGHT = 0.8


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def recency_timestamp(record: storage.MemoryRecord) -> datetime:
    metadata = record.metadata or {}
    for key in ("last_confirmed", "updated_at", "timestamp"):
        value = metadata.get(key) if key != "timestamp" else record.timestamp
        if isinstance(value, str) and value.strip():
            try:
                return parse_timestamp(value)
            except ValueError:
                continue
    return parse_timestamp(record.timestamp)


def passes_filters(
    record: storage.MemoryRecord,
    categories: set[str] | None,
    exclude_categories: set[str] | None,
    since: datetime | None,
    statuses: set[str] | None = None,
) -> bool:
    if categories is not None and record.category not in categories:
        return False
    if exclude_categories is not None and record.category in exclude_categories:
        return False
    if since is not None and parse_timestamp(record.timestamp) < since:
        return False
    if statuses is not None and str(record.metadata.get("status", "")).lower() not in statuses:
        return False
    return True


def searchable_text(record: storage.MemoryRecord) -> str:
    metadata = record.metadata or {}
    parts = [record.content]
    for key in ("summary", "details", "source", "status"):
        value = metadata.get(key)
        if isinstance(value, str):
            parts.append(value)
    tags = metadata.get("tags")
    if isinstance(tags, list):
        parts.extend(str(tag) for tag in tags)
    elif isinstance(tags, str):
        parts.append(tags)
    return "\n".join(part for part in parts if part)


def lexical_overlap_score(query_text: str, content: str) -> float:
    query_tokens = set(tokenize(query_text))
    if not query_tokens:
        return 0.0
    content_tokens = set(tokenize(content))
    return len(query_tokens & content_tokens) / len(query_tokens)


def weighted_lexical_score(query_text: str, record: storage.MemoryRecord) -> float:
    metadata = record.metadata or {}
    query_tokens = set(tokenize(query_text))
    if not query_tokens:
        return 0.0

    score = 0.0
    fields: list[tuple[float, str]] = [(0.35, record.content)]
    for weight, key in ((0.9, "summary"), (0.65, "details"), (0.25, "source"), (0.2, "status")):
        value = metadata.get(key)
        if isinstance(value, str):
            fields.append((weight, value))
    tags = metadata.get("tags")
    if isinstance(tags, list):
        fields.append((1.0, " ".join(str(tag) for tag in tags)))
    elif isinstance(tags, str):
        fields.append((1.0, tags))

    for weight, text in fields:
        content_tokens = set(tokenize(text))
        if content_tokens:
            score += weight * (len(query_tokens & content_tokens) / len(query_tokens))
    return score


def status_weight(record: storage.MemoryRecord) -> float:
    status = str((record.metadata or {}).get("status", "")).strip().lower()
    return STATUS_WEIGHTS.get(status, DEFAULT_STATUS_WEIGHT)


def score_record(
    record: storage.MemoryRecord,
    query_text: str,
    query_vector: list[float],
    index: dict[int, dict[str, Any]],
    cfg: dict[str, Any],
) -> float:
    indexed_embedding = index.get(record.id, {}).get("embedding")
    embedding = indexed_embedding if isinstance(indexed_embedding, list) else record.embedding or embed(record.content)
    score = cosine(query_vector, embedding)
    score += 0.45 * weighted_lexical_score(query_text, record)
    try:
        score += 0.15 * float(record.metadata.get("importance", 0.0))
    except (TypeError, ValueError):
        pass
    score *= recall_config.category_weight(cfg, record.category)
    score *= status_weight(record)
    age_days = max(0.0, (datetime.now(timezone.utc) - recency_timestamp(record)).total_seconds() / 86400)
    score += 0.03 / (1.0 + age_days)
    return score


def query(
    query_text: str,
    categories: list[str] | None = None,
    exclude_categories: list[str] | None = None,
    limit: int = 8,
    root: str | Path | None = None,
    summarize: bool = False,
    statuses: list[str] | None = None,
) -> dict[str, Any]:
    cfg = recall_config.load_config(root)
    include_set = {recall_config.normalize_category(value) for value in categories} if categories else None
    exclude_set = (
        {recall_config.normalize_category(value) for value in exclude_categories}
        if exclude_categories
        else None
    )
    status_set = {value.strip().lower() for value in statuses} if statuses else None
    since = None
    if cfg.get("recency_days") is not None:
        since = datetime.now(timezone.utc) - timedelta(days=int(cfg["recency_days"]))

    index = index_store.ensure_complete(root)
    query_vector = embed(query_text)
    ranked: list[storage.MemoryRecord] = []
    for record in storage.iter_records(root):
        if not passes_filters(record, include_set, exclude_set, since, status_set):
            continue
        record.score = score_record(record, query_text, query_vector, index, cfg)
        ranked.append(record)

    ranked.sort(key=lambda item: (item.score, parse_timestamp(item.timestamp), item.id), reverse=True)
    results = [
        {
            "id": record.id,
            "category": record.category,
            "timestamp": record.timestamp,
            "score": round(record.score, 4),
            "content": record.content,
            "metadata": record.metadata,
        }
        for record in ranked[:limit]
    ]
    response: dict[str, Any] = {"query": query_text, "results": results}
    if summarize:
        response["summary"] = summarize_records(results, cfg["token_budget"])
    return response
