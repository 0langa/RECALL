#!/usr/bin/env python3
"""Curated SessionStart context rendering for RECALL."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import config as recall_config
import memory_manager
import retrieval


CATEGORY_CAPS = {
    "requirements": 3,
    "constraints": 2,
    "risks": 2,
    "architecture": 2,
    "project_state": 2,
    "decisions": 2,
    "debug_history": 1,
    "commands": 1,
}
DEFAULT_CATEGORIES = list(CATEGORY_CAPS)
ACTIVE_STATUSES = ["validated", "active", "open"]
HISTORICAL_STATUSES = ["resolved", "stale", "superseded"]
GENERIC_SUMMARIES = {
    "session stop checkpoint.",
    "session compaction checkpoint.",
    "bash result captured.",
    "tool result captured.",
}


def record_text(record: dict[str, Any], max_chars: int = 220) -> str:
    raw_metadata = record.get("metadata")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    raw_summary = metadata.get("summary")
    summary = raw_summary if isinstance(raw_summary, str) else ""
    if summary.strip().lower() and summary.strip().lower() not in GENERIC_SUMMARIES:
        text = summary
    else:
        raw_details = metadata.get("details")
        details = raw_details if isinstance(raw_details, str) else ""
        text = details or record.get("content", "")
    text = " ".join(str(text).split())
    if len(text) > max_chars:
        return text[: max_chars - 14].rstrip() + " [truncated]"
    return text


def cap_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, int] = defaultdict(int)
    capped: list[dict[str, Any]] = []
    for record in records:
        category = str(record.get("category", ""))
        limit = CATEGORY_CAPS.get(category, 1)
        if seen[category] >= limit:
            continue
        seen[category] += 1
        capped.append(record)
    return capped


def render_grouped(records: list[dict[str, Any]], token_budget: int, historical: bool = False) -> str:
    if not records:
        return ""
    lines = ["Historical lower-confidence RECALL context:" if historical else "Curated RECALL project memory:"]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record.get("category", "uncategorized"))].append(record)
    for category in CATEGORY_CAPS:
        category_records = grouped.get(category, [])
        if not category_records:
            continue
        lines.append(f"{category}:")
        for record in category_records:
            lines.append(f"- #{record.get('id')} {record_text(record)}")
    output: list[str] = []
    used = 0
    for line in lines:
        line_tokens = max(1, len(line.split()))
        if output and used + line_tokens > token_budget:
            break
        output.append(line)
        used += line_tokens
    return "\n".join(output)


def written_this_session(record: dict[str, Any], session_id: str) -> bool:
    raw_metadata = record.get("metadata")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    return session_id in (
        str(metadata.get("session_id") or ""),
        str(metadata.get("source_session") or ""),
    )


INJECTION_MIN_OVERLAP = 0.1


def _card_gate_overlap(query: str, record: dict[str, Any]) -> float:
    """Per-card overlap between the prompt and the card's agent-facing text."""
    query_tokens = retrieval.gate_tokens(query)
    if not query_tokens:
        return 0.0
    raw_metadata = record.get("metadata")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    texts = [str(record.get("content") or "")]
    for key in ("summary", "details"):
        value = metadata.get(key)
        if isinstance(value, str):
            texts.append(value)
    card_tokens: set[str] = set()
    for text in texts:
        card_tokens.update(retrieval.gate_tokens(text))
    return len(query_tokens & card_tokens) / len(query_tokens)


def drop_weak_matches(records: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Injection noise floor: keep the strongest match unconditionally, drop
    tail cards with no meaningful prompt overlap.

    The relevance gate already decided injection happens (top-1 signal is
    strong); this trims the weakly-related filler that otherwise rides along
    on category caps — judged as noise and paid for in tokens.
    """
    if not records:
        return records
    scored = [(index, _card_gate_overlap(query, record)) for index, record in enumerate(records)]
    best_index = max(scored, key=lambda item: item[1])[0]
    kept = [
        record
        for (index, overlap), record in zip(scored, records, strict=True)
        if index == best_index or overlap >= INJECTION_MIN_OVERLAP
    ]
    return kept


def drop_session_records(records: list[dict[str, Any]], session_id: str | None) -> list[dict[str, Any]]:
    """Session-recency suppression for automatic injection.

    Cards written in the current session are already in the agent's
    conversation; re-injecting them is pure token waste. Explicit retrieval
    is not filtered — when the agent asks, it gets everything.
    """
    if not session_id:
        return records
    return [record for record in records if not written_this_session(record, session_id)]


def build_session_context(
    root: str | Path | None,
    query: str,
    limit: int,
    token_budget: int | None = None,
    exclude_categories: list[str] | None = None,
    exclude_session_id: str | None = None,
) -> str:
    cfg = recall_config.load_config(root)
    budget = min(int(token_budget or cfg.get("token_budget", 1200)), 900)
    active = memory_manager.query(
        query,
        categories=DEFAULT_CATEGORIES,
        exclude_categories=exclude_categories,
        limit=max(limit * 2, sum(CATEGORY_CAPS.values())),
        root=root,
        statuses=ACTIVE_STATUSES,
    )
    records = cap_records(
        drop_weak_matches(drop_session_records(active.get("results", []), exclude_session_id), query)
    )[:limit]
    if records:
        return render_grouped(records, budget)

    historical = memory_manager.query(
        query,
        categories=DEFAULT_CATEGORIES,
        exclude_categories=exclude_categories,
        limit=limit,
        root=root,
        statuses=HISTORICAL_STATUSES,
    )
    historical_records = cap_records(drop_session_records(historical.get("results", []), exclude_session_id))[:limit]
    return render_grouped(historical_records, budget, historical=True)
