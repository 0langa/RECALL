#!/usr/bin/env python3
"""CLI-first review and audit summaries for RECALL project memory."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
from typing import Any

import config as recall_config
import memory_noise
import retrieval
import security
from services import lifecycle_service
import storage


RELATION_KEYS = ("related_to", "supersedes", "superseded_by", "merged_from")
GENERIC_SUMMARIES = {
    "session stop checkpoint.",
    "session compaction checkpoint.",
    "bash result captured.",
    "tool result captured.",
    "apply_patch result captured.",
}
AUTO_SOURCES = {"post_tool_use", "pre_compact", "stop"}
MANUAL_SOURCES = {"skill", "user", "prompt_inspector"}
SYNTHESIZED_SOURCES = {"finalizer"}
COMMAND_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\bget-content\b"), "Get-Content"),
    (re.compile(r"(?i)\bget-childitem\b"), "Get-ChildItem"),
    (re.compile(r"(?i)\bselect-string\b"), "Select-String"),
    (re.compile(r"(?i)\bselect-object\b"), "Select-Object"),
    (re.compile(r"(?i)\bget-location\b"), "Get-Location"),
    (re.compile(r"(?i)\brg\b"), "rg"),
    (re.compile(r"(?i)\bgit\s+status\b"), "git status"),
    (re.compile(r"(?i)\bgit\s+log\b"), "git log"),
    (re.compile(r"(?i)\bgit\s+show\b"), "git show"),
    (re.compile(r"(?i)\bdir\b"), "dir"),
    (re.compile(r"(?i)\bls\b"), "ls"),
    (re.compile(r"(?i)\bpwd\b"), "pwd"),
    (re.compile(r"(?i)\bcat\b"), "cat"),
    (re.compile(r"(?i)\btype\b"), "type"),
    (re.compile(r"(?i)\breview-memory\b"), "review-memory"),
    (re.compile(r"(?i)\bretrieve-memory\b"), "retrieve-memory"),
    (re.compile(r"(?i)\barchive-noise\b"), "archive-noise"),
    (re.compile(r"(?i)\bpython\s+-m\s+unittest\b"), "python -m unittest"),
    (re.compile(r"(?i)\bbuild_plugin(?:\.ps1|\.sh)?\b"), "build_plugin"),
    (re.compile(r"(?i)\bsmoke_recall(?:\.py)?\b"), "smoke_recall"),
]
COMMAND_CAPTURE_RE = re.compile(r"(?is)\bcommand:\s*(.+?)(?:\s+result:|\s+exit_code:|$)")


def compact_text(record: storage.MemoryRecord, max_chars: int = 180) -> str:
    summary = record.metadata.get("summary") if isinstance(record.metadata, dict) else None
    if isinstance(summary, str) and summary.strip() and not is_generic_summary(summary):
        text = summary
    else:
        details = record.metadata.get("details") if isinstance(record.metadata, dict) else None
        text = details if isinstance(details, str) and details.strip() else record.content
    # Legacy/imported stores may hold raw secrets; never surface them in review output.
    text = " ".join(security.redact_text(text).split())
    if len(text) > max_chars:
        return text[: max_chars - 14].rstrip() + " [truncated]"
    return text


def relation_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: metadata[key] for key in RELATION_KEYS if key in metadata}


def is_generic_summary(value: str | None) -> bool:
    if not isinstance(value, str):
        return False
    cleaned = value.strip().lower()
    if not cleaned:
        return False
    return cleaned in GENERIC_SUMMARIES or bool(memory_noise.GENERIC_SUMMARY_RE.search(cleaned))


def command_text(record: storage.MemoryRecord) -> str:
    metadata = record.metadata or {}
    command = metadata.get("command")
    if isinstance(command, str) and command.strip():
        return command.strip()
    text = " ".join(
        str(value)
        for value in [
            record.content,
            metadata.get("summary", ""),
            metadata.get("details", ""),
        ]
        if isinstance(value, str) and value.strip()
    )
    match = COMMAND_CAPTURE_RE.search(text)
    return match.group(1).strip() if match else ""


def normalize_command_pattern(command: str) -> str | None:
    cleaned = " ".join(command.split())
    if not cleaned:
        return None
    for pattern, label in COMMAND_PATTERNS:
        if pattern.search(cleaned):
            return label
    parts = cleaned.split()
    return " ".join(parts[: min(3, len(parts))])


def source_value(record: storage.MemoryRecord) -> str:
    return str((record.metadata or {}).get("source", "unspecified") or "unspecified")


def source_kind(source: str) -> str:
    normalized = source.strip().lower()
    if normalized in AUTO_SOURCES:
        return "automatic"
    if normalized in MANUAL_SOURCES:
        return "manual"
    if normalized in SYNTHESIZED_SOURCES:
        return "synthesized"
    return "other"


def relationship_count(record: storage.MemoryRecord) -> int:
    metadata = record.metadata or {}
    return sum(1 for key in RELATION_KEYS if key in metadata)


def filtered_counts(records: list[storage.MemoryRecord], field: str) -> dict[str, int]:
    if field == "status":
        counter = Counter(str((record.metadata or {}).get("status", "unspecified")) for record in records)
    elif field == "category":
        counter = Counter(record.category for record in records)
    else:
        counter = Counter(source_value(record) for record in records)
    return dict(sorted(counter.items()))


def top_counter_items(counter: Counter[str], key_name: str, limit: int = 8) -> list[dict[str, Any]]:
    return [{key_name: name, "count": count} for name, count in counter.most_common(limit) if name]


def quality_metrics(records: list[storage.MemoryRecord]) -> dict[str, Any]:
    active = 0
    archived = 0
    generic_summary_count = 0
    generic_active_summary_count = 0
    relationship_records = 0
    confirmed_records = 0
    active_noise_candidates = 0
    source_counts: Counter[str] = Counter()
    source_kind_counts: Counter[str] = Counter()
    noisy_command_counts: Counter[str] = Counter()
    generic_summary_counts: Counter[str] = Counter()

    for record in records:
        metadata = record.metadata or {}
        status = str(metadata.get("status", "unspecified")).lower()
        source = source_value(record)
        source_counts[source] += 1
        source_kind_counts[source_kind(source)] += 1
        if status == "active":
            active += 1
        if status == "archived":
            archived += 1
        summary = metadata.get("summary")
        if isinstance(summary, str) and is_generic_summary(summary):
            generic_summary_count += 1
            generic_summary_counts[summary.strip()] += 1
            if status == "active":
                generic_active_summary_count += 1
        if relationship_count(record):
            relationship_records += 1
        if "last_confirmed" in metadata:
            confirmed_records += 1
        noise_reason = memory_noise.archive_reason(record)
        if noise_reason is not None:
            active_noise_candidates += 1
            pattern = normalize_command_pattern(command_text(record))
            if pattern is not None:
                noisy_command_counts[pattern] += 1

    signal_records = max(0, active - active_noise_candidates)
    signal_to_noise = round(signal_records / active, 4) if active else 1.0
    return {
        "signal_to_noise_estimate": signal_to_noise,
        "active_records": active,
        "archived_records": archived,
        "active_noise_candidates": active_noise_candidates,
        "generic_summary_count": generic_summary_count,
        "generic_active_summary_count": generic_active_summary_count,
        "relationship_record_count": relationship_records,
        "confirmed_record_count": confirmed_records,
        "source_counts": dict(sorted(source_counts.items())),
        "source_kind_counts": dict(sorted(source_kind_counts.items())),
        "top_generic_summaries": top_counter_items(generic_summary_counts, "summary"),
        "top_noisy_commands": top_counter_items(noisy_command_counts, "pattern"),
        "recommended_cleanup_command": "python ./scripts/recall_skill.py archive-noise",
    }


def memory_card(record: storage.MemoryRecord) -> dict[str, Any]:
    metadata = security.redact_value(record.metadata or {})
    noise_reason = memory_noise.archive_reason(record)
    flag, flag_reason = retrieval.health_flag(record)
    return {
        "id": record.id,
        "category": record.category,
        "status": metadata.get("status", "unspecified"),
        "timestamp": record.timestamp,
        "summary": compact_text(record),
        "source": metadata.get("source"),
        "source_kind": metadata.get("source_kind"),
        "source_path": metadata.get("source_path"),
        "source_hash": metadata.get("source_hash"),
        "source_revision": metadata.get("source_revision"),
        "source_checked_at": metadata.get("source_checked_at"),
        "source_history": metadata.get("source_history", []),
        "evidence": metadata.get("evidence", []),
        "verification_invalidated_at": metadata.get("verification_invalidated_at"),
        "flag": flag,
        "flags": [flag],
        "flag_reason": flag_reason,
        "truncated": "[truncated]" in compact_text(record),
        "invalidation_reason": metadata.get("invalidation_reason"),
        "replacement_source_path": metadata.get("replacement_source_path"),
        "source_session": metadata.get("source_session") or metadata.get("turn_id"),
        "last_confirmed": metadata.get("last_confirmed"),
        "relationships": relation_metadata(metadata),
        "tags": metadata.get("tags", []),
        "importance": metadata.get("importance"),
        "confidence": metadata.get("confidence"),
        "capture_reason": metadata.get("capture_reason"),
        "record_kind": metadata.get("record_kind"),
        "noise_candidate": noise_reason is not None,
        "noise_reason": noise_reason,
    }


def _trust_cards(records: list[storage.MemoryRecord]) -> list[dict[str, Any]]:
    cards = [dict(memory_card(record), metadata=record.metadata) for record in records]
    retrieval.mark_conflicts(cards)
    return [security.redact_value({key: value for key, value in item.items() if key != "metadata"}) for item in cards]


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
    decision = recall_config.root_decision(root)
    resolved_root = Path(decision["root"]) if decision["status"] == "resolved" else None
    has_store = resolved_root is not None and recall_config.persistent_memory_exists(resolved_root)
    records = list(storage.iter_records(resolved_root)) if has_store else []
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
    source_counts = Counter(source_value(record) for record in records)
    filtered.sort(key=lambda record: (record.timestamp, record.id), reverse=True)
    trust = _trust_cards(records)
    by_id = {item["id"]: item for item in trust}
    cards = []
    for record in filtered[:max(0, limit)]:
        item = by_id[record.id]
        cards.append({key: value for key, value in item.items() if key != "metadata"})
    empty_reason = None if cards else (
        f"{decision['status']}_root" if resolved_root is None else "no_store" if not has_store
        else "empty_store" if not records else "filters_excluded_all" if not filtered else "result_limit"
    )
    return {
        "total": len(records),
        "matched": len(filtered),
        "shown": len(cards),
        "omitted_count": len(filtered) - len(cards),
        "truncated": len(cards) < len(filtered) or any(item["truncated"] for item in cards),
        "health": dict(retrieval.selection_health(retrieval.health_summary(trust), cards), scope="entire_store"),
        "root_decision": decision,
        "empty_reason": empty_reason,
        "filters": {
            "statuses": sorted(status_set),
            "categories": sorted(category_set),
            "source": source_filter,
        },
        "status_counts": dict(sorted(status_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "source_counts": dict(sorted(source_counts.items())),
        "filtered_status_counts": filtered_counts(filtered, "status"),
        "filtered_category_counts": filtered_counts(filtered, "category"),
        "filtered_source_counts": filtered_counts(filtered, "source"),
        "quality": quality_metrics(records),
        "memories": security.redact_value(cards),
    }


def audit_memory(
    root: str | Path | None = None,
    *,
    statuses: list[str] | None = None,
    categories: list[str] | None = None,
    source: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    review = review_memory(
        root,
        statuses=statuses,
        categories=categories,
        source=source,
        limit=limit,
    )
    decision = review["root_decision"]
    resolved_root = Path(decision["root"]) if decision["status"] == "resolved" else None
    has_store = resolved_root is not None and recall_config.persistent_memory_exists(resolved_root)
    records = list(storage.iter_records(resolved_root)) if has_store else []
    status_set = {status.strip().lower() for status in statuses or [] if status.strip()}
    category_set = {recall_config.normalize_category(category) for category in categories or [] if category.strip()}
    source_filter = source.strip().lower() if source else None
    candidates: list[storage.MemoryRecord] = []
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
        if memory_noise.archive_reason(record) is not None:
            candidates.append(record)
    candidates.sort(key=lambda record: (record.timestamp, record.id), reverse=True)
    conflict_clusters = lifecycle_service.find_conflicts(resolved_root) if has_store else []
    trust_by_id = {card["id"]: card for card in _trust_cards(records)}
    noise_cards = [trust_by_id[record.id] for record in candidates[:max(0, limit)]]
    return {
        "total": review["total"],
        "matched": review["matched"],
        "shown": len(noise_cards),
        "root_decision": decision,
        "empty_reason": None if noise_cards else review["empty_reason"] or "no_noise_candidates",
        "omitted_count": max(0, len(candidates) - limit),
        "truncated": len(candidates) > limit or any(card["truncated"] for card in noise_cards),
        "health": dict(retrieval.selection_health(review["health"], noise_cards), scope="entire_store"),
        "filters": review["filters"],
        "status_counts": review["status_counts"],
        "category_counts": review["category_counts"],
        "source_counts": review["source_counts"],
        "quality": review["quality"],
        "noise_candidates": noise_cards,
        "conflict_clusters": conflict_clusters,
        "health_recommendations": [
            "Resolve ambiguous conflict clusters before promoting claims to validated truth."
        ] if conflict_clusters else [],
    }
