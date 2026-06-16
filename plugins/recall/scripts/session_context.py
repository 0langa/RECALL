#!/usr/bin/env python3
"""Curated SessionStart context rendering for RECALL."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import config as recall_config
import memory_manager


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
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    summary = metadata.get("summary") if isinstance(metadata.get("summary"), str) else ""
    if summary.strip().lower() and summary.strip().lower() not in GENERIC_SUMMARIES:
        text = summary
    else:
        details = metadata.get("details") if isinstance(metadata.get("details"), str) else ""
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


def build_session_context(
    root: str | Path | None,
    query: str,
    limit: int,
    token_budget: int | None = None,
    exclude_categories: list[str] | None = None,
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
    records = cap_records(active.get("results", []))[:limit]
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
    historical_records = cap_records(historical.get("results", []))[:limit]
    return render_grouped(historical_records, budget, historical=True)
