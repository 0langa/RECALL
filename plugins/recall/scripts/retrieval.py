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
    "validated": 1.1,
    "active": 1.0,
    "hypothesis": 0.72,
    "open": 0.95,
    "resolved": 0.65,
    "stale": 0.35,
    "superseded": 0.25,
    "deprecated": 0.2,
    "archived": 0.15,
}
DEFAULT_STATUS_WEIGHT = 0.8
DEFAULT_QUERY_STATUSES = {"validated", "active", "open", "resolved", "unspecified"}
SOURCE_WEIGHTS = {
    "skill": 1.05,
    "user": 1.05,
    "prompt_inspector": 1.0,
    "finalizer": 1.0,
    "smoke_recall": 1.0,
    "stop": 0.92,
    "pre_compact": 0.82,
    "post_tool_use": 0.68,
}
DEFAULT_SOURCE_WEIGHT = 0.9
CURRENT_DURABLE_CATEGORIES = {"requirements", "constraints", "decisions", "architecture", "risks", "tasks", "project_state"}
CURRENT_STATUSES = {"validated", "active", "open"}
SOURCE_BLIND_MEMORY_RE = {"recall memory", "project memory", "automatically provided", "without running commands", "without reading source"}
CATEGORY_TERMS = {
    "requirements": {"requirement", "requirements", "accepted requirements"},
    "constraints": {"constraint", "constraints"},
    "risks": {"risk", "risks", "blocker", "blockers"},
    "architecture": {"architecture", "design"},
    "decisions": {"decision", "decisions", "accepted"},
    "tasks": {"next engineer", "next work", "next steps", "todo", "tasks"},
    "project_state": {"current state", "status", "project state"},
}


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


def record_status(record: storage.MemoryRecord) -> str:
    status = str((record.metadata or {}).get("status", "")).strip().lower()
    return status or "unspecified"


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
    if statuses is not None and record_status(record) not in statuses:
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


def normalized_lexical_overlap(query_text: str, record: storage.MemoryRecord) -> float:
    """Return a stable 0..1 overlap used by automatic-injection gating."""

    return min(1.0, weighted_lexical_score(query_text, record))


def source_blind_memory_request(query_text: str) -> bool:
    lowered = query_text.casefold()
    return any(marker in lowered for marker in SOURCE_BLIND_MEMORY_RE)


def requested_categories(query_text: str) -> set[str]:
    lowered = query_text.casefold()
    requested: set[str] = set()
    for category, terms in CATEGORY_TERMS.items():
        if any(term in lowered for term in terms):
            requested.add(category)
    return requested


def status_weight(record: storage.MemoryRecord) -> float:
    return STATUS_WEIGHTS.get(record_status(record), DEFAULT_STATUS_WEIGHT)


def source_weight(record: storage.MemoryRecord) -> float:
    source = str((record.metadata or {}).get("source", "")).strip().lower()
    return SOURCE_WEIGHTS.get(source, DEFAULT_SOURCE_WEIGHT)


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
    score *= source_weight(record)
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
    status_set = {value.strip().lower() for value in statuses} if statuses else set(DEFAULT_QUERY_STATUSES)
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


def assess_relevance(
    query_text: str,
    *,
    root: str | Path | None,
    categories: list[str] | None = None,
    exclude_categories: list[str] | None = None,
    statuses: list[str] | None = None,
) -> dict[str, Any]:
    response = query(
        query_text,
        categories=categories,
        exclude_categories=exclude_categories,
        limit=3,
        root=root,
        statuses=statuses,
    )
    results = response.get("results", [])
    top = results[0] if results else None
    lexical = 0.0
    if top is not None:
        record = storage.get_record(int(top["id"]), root)
        if record is not None:
            lexical = normalized_lexical_overlap(query_text, record)
    cfg = recall_config.load_config_if_present(root)
    thresholds = cfg.get("relevance", {})
    minimum_score = float(thresholds.get("minimum_score", 0.75))
    minimum_lexical = float(thresholds.get("minimum_lexical_overlap", 0.15))
    raw_score = float(top.get("score", 0.0)) if top else 0.0
    relevance_score = max(raw_score, lexical + 0.25) if top else 0.0
    category_match = False
    if top is not None and top.get("category") in CURRENT_DURABLE_CATEGORIES:
        status = str(((top.get("metadata") or {}).get("status") or "")).strip().lower()
        requested = requested_categories(query_text)
        category_match = source_blind_memory_request(query_text) and top.get("category") in requested and status in CURRENT_STATUSES
        if category_match:
            relevance_score = max(relevance_score, 0.8)
        if status in CURRENT_STATUSES and lexical >= minimum_lexical:
            relevance_score = max(relevance_score, lexical + 0.45)
    relevant = bool(top and relevance_score >= minimum_score and (lexical >= minimum_lexical or category_match))
    return {
        "relevant": relevant,
        "sufficient": relevant and len(results) > 0,
        "top_score": round(relevance_score, 4),
        "raw_rank_score": round(raw_score, 4),
        "lexical_overlap": round(lexical, 4),
        "category_match": category_match,
        "result_ids": [int(item["id"]) for item in results],
        "thresholds": {"minimum_score": minimum_score, "minimum_lexical_overlap": minimum_lexical},
    }
