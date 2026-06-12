"""Token-budgeted explainable context packet assembly."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

import memory_manager
from models import ContextPacketRequest, ContextPacketResponse


def estimate_tokens(text: str) -> int:
    """Conservatively estimate tokens without an external tokenizer."""

    return max(1, math.ceil((len(text) / 4) * 1.15))


def build_context_packet(request: ContextPacketRequest) -> ContextPacketResponse:
    """Return diverse current memories within the declared token budget."""

    result = memory_manager.query(
        request.query_text,
        categories=list(request.categories),
        limit=100,
        root=request.root,
    )
    cards: list[dict[str, Any]] = []
    used = 0
    category_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    for item in result["results"]:
        metadata = item.get("metadata", {})
        category = str(item["category"])
        source = str(metadata.get("source") or "unspecified")
        if category_counts[category] >= 3 or source_counts[source] >= 2:
            continue
        title = str(metadata.get("summary") or item["content"][:120]).strip()
        content = " ".join(str(item["content"]).split())
        content = content[:320]
        rendered = f"[{category}] {title}: {content}"
        cost = estimate_tokens(rendered)
        if used + cost > request.token_budget:
            title_rendered = f"[{category}] {title}"
            title_cost = estimate_tokens(title_rendered)
            if used + title_cost > request.token_budget:
                continue
            rendered = title_rendered
            cost = title_cost
        cards.append(
            {
                "id": item["id"],
                "category": category,
                "source": source,
                "text": rendered,
                "estimated_tokens": cost,
                "score_components": {
                    "combined_score": item["score"],
                    "status": metadata.get("status", "unspecified"),
                    "importance": metadata.get("importance"),
                    "trust": metadata.get("trust", metadata.get("confidence")),
                },
            }
        )
        used += cost
        category_counts[category] += 1
        source_counts[source] += 1
    return ContextPacketResponse(
        {
            "query": request.query_text,
            "token_budget": request.token_budget,
            "estimated_tokens": used,
            "cards": cards,
            "candidate_count": len(result["results"]),
            "omitted_count": len(result["results"]) - len(cards),
        }
    )
