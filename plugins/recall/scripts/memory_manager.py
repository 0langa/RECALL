#!/usr/bin/env python3
"""Public API and CLI for RECALL project memory."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config as recall_config
from embedder import embed
import index_store
import memory_hygiene
import memory_lifecycle
import retrieval
import security
import storage
import write_policy
from services import preference_service


MemoryRecord = storage.MemoryRecord

CARD_STATUSES = {
    "hypothesis",
    "active",
    "validated",
    "open",
    "resolved",
    "stale",
    "superseded",
    "deprecated",
    "archived",
}
AUTO_WRITE_SOURCES = {"post_tool_use", "pre_compact", "stop"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def redact_secrets(text: str) -> str:
    return security.redact_text(text)


def redact_metadata(value: Any) -> Any:
    """Recursively redact secret-like strings before persistence."""

    return security.redact_value(value)


def db_path(root: str | Path | None = None) -> Path:
    return storage.db_path(root)


def jsonl_dir(root: str | Path | None = None) -> Path:
    return storage.jsonl_dir(root)


def vector_index_path(root: str | Path | None = None) -> Path:
    return storage.vector_index_path(root)


def init_store(root: str | Path | None = None) -> None:
    storage.init_store(root)


def clamp_unit_interval(value: float, field_name: str) -> float:
    if value < 0 or value > 1:
        raise ValueError(f"{field_name} must be between 0.0 and 1.0.")
    return value


def normalize_tags(tags: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for tag in tags or []:
        cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", tag.strip().lower()).strip("-")
        if cleaned and cleaned not in normalized:
            normalized.append(cleaned)
    return normalized


def build_card_metadata(
    *,
    summary: str | None = None,
    details: str | None = None,
    tags: list[str] | None = None,
    source: str | None = None,
    status: str | None = None,
    importance: float | None = None,
    confidence: float | None = None,
    base: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = dict(base or {})
    if summary is not None:
        metadata["summary"] = summary.strip()
    if details is not None:
        metadata["details"] = details.strip()
    normalized_tags = normalize_tags(tags)
    if normalized_tags:
        existing = metadata.get("tags", [])
        if not isinstance(existing, list):
            existing = [str(existing)]
        metadata["tags"] = normalize_tags([*existing, *normalized_tags])
    if source is not None:
        metadata["source"] = source.strip()
    if status is not None:
        normalized_status = status.strip().lower()
        if normalized_status not in CARD_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(CARD_STATUSES))}.")
        metadata["status"] = normalized_status
    if importance is not None:
        metadata["importance"] = clamp_unit_interval(float(importance), "importance")
    if confidence is not None:
        metadata["confidence"] = clamp_unit_interval(float(confidence), "confidence")
    return {key: value for key, value in metadata.items() if value not in ("", [], None)}


def get_record(record_id: int, root: str | Path | None = None) -> MemoryRecord | None:
    return storage.get_record(record_id, root)


def update_record_metadata(
    record_id: int,
    metadata: dict[str, Any],
    root: str | Path | None = None,
) -> MemoryRecord:
    return storage.update_record_metadata(record_id, metadata, root)


def edit_record(
    record_id: int,
    root: str | Path | None = None,
    *,
    category: str | None = None,
    content: str | None = None,
    summary: str | None = None,
    details: str | None = None,
    tags: list[str] | None = None,
    source: str | None = None,
    status: str | None = None,
    importance: float | None = None,
    confidence: float | None = None,
) -> MemoryRecord:
    record = storage.get_record(record_id, root)
    if record is None:
        raise KeyError(f"RECALL memory #{record_id} was not found.")
    normalized_category = (
        recall_config.normalize_category(category)
        if category is not None
        else record.category
    )
    if normalized_category not in recall_config.load_config(root)["categories"]:
        recall_config.add_category(
            normalized_category,
            f"Auto-created custom category `{normalized_category}`.",
            1.0,
            root,
        )
    safe_content = redact_secrets((content if content is not None else record.content).strip())
    if not safe_content:
        raise ValueError("Cannot store an empty RECALL memory.")
    metadata = redact_metadata(build_card_metadata(
        summary=summary,
        details=details,
        tags=tags,
        source=source,
        status=status,
        importance=importance,
        confidence=confidence,
        base=dict(record.metadata or {}),
    ))
    metadata["edited_at"] = utc_now()
    edited = storage.update_record(
        record.id,
        category=normalized_category,
        content=safe_content,
        metadata=metadata,
        embedding=embed(safe_content),
        root=root,
    )
    index_store.rebuild(root)
    return edited


def delete_record(record_id: int, root: str | Path | None = None) -> MemoryRecord:
    deleted = storage.delete_record(record_id, root)
    index_store.rebuild(root)
    return deleted


def add_record(
    category: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    root: str | Path | None = None,
) -> MemoryRecord:
    cfg = recall_config.load_config(root)
    normalized_category = recall_config.normalize_category(category)
    metadata = redact_metadata(dict(metadata or {}))
    if normalized_category not in cfg["categories"]:
        recall_config.add_category(
            normalized_category,
            f"Auto-created custom category `{normalized_category}`.",
            1.0,
            root,
        )
        metadata["recall_warning"] = "Category was auto-created. Refine its description and weight when useful."

    safe_content = redact_secrets(content.strip())
    if not safe_content:
        raise ValueError("Cannot store an empty RECALL memory.")
    record = storage.add_record(
        normalized_category,
        utc_now(),
        safe_content,
        metadata,
        embed(safe_content),
        root,
    )
    index_store.append_record(record, root)
    return record


def add_record_if_useful(
    category: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    root: str | Path | None = None,
) -> dict[str, Any]:
    metadata = dict(metadata or {})
    safe_content = redact_secrets(content.strip())
    if not safe_content:
        raise ValueError("Cannot store an empty RECALL memory.")
    source = str(metadata.get("source", "")).strip().lower()
    if source in AUTO_WRITE_SOURCES and not metadata.get("auto_capture_policy"):
        return {
            "action": "ignored",
            "record": None,
            "duplicate_id": None,
            "reason": "auto_capture_policy_required",
        }
    idempotency_key = str(metadata.get("idempotency_key") or "").strip()
    if idempotency_key:
        for existing in storage.iter_records(root):
            if str((existing.metadata or {}).get("idempotency_key") or "") == idempotency_key:
                return {"action": "ignored", "record": existing, "duplicate_id": existing.id, "reason": "idempotent_replay"}
    preference = preference_service.evaluate(recall_config.normalize_category(category), metadata, root)
    if preference.action == "ignore":
        return {"action": "ignored", "record": None, "duplicate_id": None, "reason": preference.reason}
    if preference.action == "update":
        return {"action": "updated_existing", "record": preference.record, "duplicate_id": preference.record.id, "reason": preference.reason}
    metadata = preference.metadata
    decision = write_policy.classify_write(category, safe_content, metadata, str(root) if root is not None else None)
    if decision.action == "ignore":
        return {
            "action": "ignored",
            "record": None,
            "duplicate_id": None,
            "reason": decision.reason,
        }
    if decision.action == "update_existing" and decision.related_id is not None:
        confirmed = confirm_record(
            decision.related_id,
            root,
            source_session=str(metadata.get("turn_id") or metadata.get("source_session") or "") or None,
        )
        return {
            "action": "updated_existing",
            "record": confirmed,
            "duplicate_id": decision.related_id,
            "reason": decision.reason,
        }
    fingerprint = memory_hygiene.content_fingerprint(category, safe_content, metadata)
    metadata["recall_fingerprint"] = fingerprint
    if decision.supersedes_id is not None:
        metadata["supersedes"] = memory_lifecycle.add_ids(metadata.get("supersedes"), decision.supersedes_id)
    action = "saved"
    if decision.related_id is not None and decision.similarity is not None:
        metadata["related_memory_id"] = decision.related_id
        metadata["related_to"] = memory_lifecycle.add_ids(metadata.get("related_to"), decision.related_id)
        metadata["related_similarity"] = round(decision.similarity, 4)
        action = "saved_related"
    record = add_record(category, safe_content, metadata, root)
    if decision.supersedes_id is not None:
        memory_lifecycle.supersede(decision.supersedes_id, record.id, root, "Automatic write policy supersession cue.")
    return {"action": action, "record": record, "duplicate_id": None}


def append_vector_index(
    record_id: int,
    category: str,
    timestamp: str,
    vector: list[float],
    root: str | Path | None = None,
) -> None:
    record = MemoryRecord(record_id, category, timestamp, "", {}, embedding=vector)
    index_store.append_record(record, root)


def next_jsonl_id(root: str | Path | None = None) -> int:
    return storage.next_jsonl_id(root)


def iter_records(root: str | Path | None = None):
    yield from storage.iter_records(root)


def iter_jsonl_records(root: str | Path | None = None):
    yield from storage.iter_jsonl_records(root)


def query(
    query_text: str,
    categories: list[str] | None = None,
    exclude_categories: list[str] | None = None,
    limit: int = 8,
    root: str | Path | None = None,
    summarize: bool = False,
    statuses: list[str] | None = None,
) -> dict[str, Any]:
    return retrieval.query(query_text, categories, exclude_categories, limit, root, summarize, statuses)


def rebuild_index(root: str | Path | None = None) -> dict[str, Any]:
    return index_store.rebuild(root)


def doctor(root: str | Path | None = None) -> dict[str, Any]:
    storage.init_store(root)
    index_report = index_store.diagnostics(root)
    backend = storage.backend(root)
    jsonl_report = storage.jsonl_diagnostics(root) if backend == "jsonl" else {
        "malformed_jsonl_rows": 0,
        "invalid_jsonl_rows": 0,
    }
    sqlite_report = storage.sqlite_diagnostics(root) if backend == "sqlite" else {}
    warnings: list[str] = []
    repairs_available: list[str] = []
    if index_report["missing_index_ids"]:
        warnings.append(f"Index is missing {len(index_report['missing_index_ids'])} storage record(s).")
    if index_report["stale_index_ids"]:
        warnings.append(f"Index contains {len(index_report['stale_index_ids'])} stale record id(s).")
    if index_report["invalid_index_rows"]:
        warnings.append(f"Invalid index row count: {index_report['invalid_index_rows']}.")
    if not index_report["index_complete"]:
        repairs_available.extend(["rebuild-index", "repair"])
    if jsonl_report["malformed_jsonl_rows"]:
        warnings.append(f"Malformed JSONL row count: {jsonl_report['malformed_jsonl_rows']}.")
    if jsonl_report["invalid_jsonl_rows"]:
        warnings.append(f"Invalid JSONL row count: {jsonl_report['invalid_jsonl_rows']}.")
    return {
        "backend": backend,
        "schema_version": storage.schema_version(root),
        "records": index_report["records"],
        "index_records": index_report["index_records"],
        "index_complete": index_report["index_complete"],
        "missing_index_ids": index_report["missing_index_ids"],
        "stale_index_ids": index_report["stale_index_ids"],
        "invalid_index_rows": index_report["invalid_index_rows"],
        "malformed_jsonl_rows": jsonl_report["malformed_jsonl_rows"],
        "invalid_jsonl_rows": jsonl_report["invalid_jsonl_rows"],
        "sqlite": sqlite_report,
        "warnings": warnings,
        "repairs_available": repairs_available,
        "storage_path": str(db_path(root) if backend == "sqlite" else jsonl_dir(root)),
        "index_path": index_report["index_path"],
    }


def repair(root: str | Path | None = None) -> dict[str, Any]:
    storage.init_store(root)
    rebuild_report = rebuild_index(root)
    return {"repair": rebuild_report, "doctor": doctor(root)}


def confirm_record(record_id: int, root: str | Path | None = None, source_session: str | None = None) -> MemoryRecord:
    return memory_lifecycle.confirm(record_id, root, source_session)


def resolve_record(record_id: int, root: str | Path | None = None, note: str | None = None) -> MemoryRecord:
    return memory_lifecycle.resolve(record_id, root, note)


def mark_record_stale(record_id: int, root: str | Path | None = None, note: str | None = None) -> MemoryRecord:
    return memory_lifecycle.mark_stale(record_id, root, note)


def prune_record(record_id: int, root: str | Path | None = None, note: str | None = None) -> MemoryRecord:
    return memory_lifecycle.prune(record_id, root, note)


def supersede_record(
    old_record_id: int,
    new_record_id: int,
    root: str | Path | None = None,
    note: str | None = None,
) -> dict[str, MemoryRecord]:
    return memory_lifecycle.supersede(old_record_id, new_record_id, root, note)


def merge_records(
    primary_id: int,
    secondary_ids: list[int | str],
    root: str | Path | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    return memory_lifecycle.merge(primary_id, secondary_ids, root, note)


def define_category(
    name: str,
    description: str | None = None,
    weight: float = 1.0,
    root: str | Path | None = None,
) -> dict[str, Any]:
    return recall_config.add_category(name, description, weight, root)


def parse_metadata(raw_metadata: str | None) -> dict[str, Any]:
    if not raw_metadata:
        return {}
    return json.loads(raw_metadata)


def main() -> None:
    parser = argparse.ArgumentParser(description="Store and retrieve RECALL project memory.")
    parser.add_argument("--root", help="Project root. Defaults to current directory or RECALL_PROJECT_ROOT.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init")

    add = subparsers.add_parser("add")
    add.add_argument("category")
    add.add_argument("content", nargs="?")
    add.add_argument("--metadata", help="JSON metadata object.")
    add.add_argument("--summary", dest="card_summary", help="Concise memory-card summary.")
    add.add_argument("--details", help="Additional memory-card details.")
    add.add_argument("--tag", action="append", dest="tags", help="Memory-card tag. May be repeated.")
    add.add_argument("--source", help="Memory source, such as user, pre_compact, post_tool_use, or manual.")
    add.add_argument("--status", choices=sorted(CARD_STATUSES), help="Memory-card lifecycle status.")
    add.add_argument("--importance", type=float, help="Memory importance from 0.0 to 1.0.")
    add.add_argument("--confidence", type=float, help="Memory confidence from 0.0 to 1.0.")

    search = subparsers.add_parser("query")
    search.add_argument("query_text")
    search.add_argument("--category", action="append", dest="categories")
    search.add_argument("--exclude-category", action="append", dest="exclude_categories")
    search.add_argument("--limit", type=int, default=8)
    search.add_argument("--summary", action="store_true")
    search.add_argument("--status", action="append", dest="statuses")

    define = subparsers.add_parser("define-category")
    define.add_argument("name")
    define.add_argument("--description")
    define.add_argument("--weight", type=float, default=1.0)

    subparsers.add_parser("rebuild-index")
    subparsers.add_parser("doctor")
    subparsers.add_parser("repair")

    args = parser.parse_args()
    if args.command == "init":
        init_store(args.root)
        print(recall_config.config_path(args.root))
    elif args.command == "add":
        metadata = build_card_metadata(
            summary=args.card_summary,
            details=args.details,
            tags=args.tags,
            source=args.source,
            status=args.status,
            importance=args.importance,
            confidence=args.confidence,
            base=parse_metadata(args.metadata),
        )
        content = args.content or args.card_summary or args.details
        if content is None:
            raise SystemExit("add requires content or --summary/--details.")
        record = add_record(args.category, content, metadata, args.root)
        print(json.dumps(record.__dict__, indent=2, sort_keys=True))
    elif args.command == "query":
        print(
            json.dumps(
                query(
                    args.query_text,
                    args.categories,
                    args.exclude_categories,
                    args.limit,
                    args.root,
                    args.summary,
                    args.statuses,
                ),
                indent=2,
                sort_keys=True,
            )
        )
    elif args.command == "define-category":
        print(json.dumps(define_category(args.name, args.description, args.weight, args.root), indent=2))
    elif args.command == "rebuild-index":
        print(json.dumps(rebuild_index(args.root), indent=2, sort_keys=True))
    elif args.command == "doctor":
        print(json.dumps(doctor(args.root), indent=2, sort_keys=True))
    elif args.command == "repair":
        print(json.dumps(repair(args.root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
