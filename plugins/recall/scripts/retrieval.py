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


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


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
    score += 0.45 * lexical_overlap_score(query_text, searchable_text(record))
    try:
        score += 0.15 * float(record.metadata.get("importance", 0.0))
    except (TypeError, ValueError):
        pass
    score *= recall_config.category_weight(cfg, record.category)
    age_days = max(0.0, (datetime.now(timezone.utc) - parse_timestamp(record.timestamp)).total_seconds() / 86400)
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
    exclude_set = {recall_config.normalize_category(value) for value in exclude_categories} if exclude_categories else None
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

    ranked.sort(key=lambda item: item.score, reverse=True)
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
