"""Token-budgeted explainable context packet assembly."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

import memory_manager
import retrieval
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
        truncated = len(content) > 320
        content = content[:320]
        flags = item.get("flags", [item.get("flag", "current")])
        label = f"[{category};{','.join(flags)}]"
        rendered = f"{label} {title}: {content}" + (" [truncated]" if truncated else "")
        cost = estimate_tokens(rendered)
        if used + cost > request.token_budget:
            title_rendered = f"{label} {title} [truncated]"
            title_cost = estimate_tokens(title_rendered)
            if used + title_cost > request.token_budget:
                continue
            rendered = title_rendered
            cost = title_cost
            truncated = True
        cards.append(
            {
                "id": item["id"],
                "category": category,
                "source": source,
                "text": rendered,
                "flag": item.get("flag", "current"),
                "flags": flags,
                "flag_reason": item.get("flag_reason"),
                "truncated": truncated,
                "provenance": {
                    key: metadata[key] for key in (
                        "source_path", "source_hash", "source_revision", "source_checked_at",
                        "invalidation_reason", "verification_invalidated_at",
                    ) if key in metadata
                },
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
            "candidate_count": result.get("candidate_count", len(result["results"])),
            "omitted_count": result.get("omitted_count", 0) + len(result["results"]) - len(cards),
            "filtered_count": result.get("filtered_count", 0),
            "truncated": bool(result.get("truncated") or len(cards) < len(result["results"]) or any(card["truncated"] for card in cards)),
            "health": retrieval.selection_health(result.get("health", {}), cards),
            "root_decision": result.get("root_decision"),
            "empty_reason": None if cards else result.get("empty_reason") or "token_budget",
        }
    )
