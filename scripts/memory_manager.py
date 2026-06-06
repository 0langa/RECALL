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
import retrieval
import storage


MemoryRecord = storage.MemoryRecord

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*['\"]?[^'\"\s]+"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def redact_secrets(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def db_path(root: str | Path | None = None) -> Path:
    return storage.db_path(root)


def jsonl_dir(root: str | Path | None = None) -> Path:
    return storage.jsonl_dir(root)


def vector_index_path(root: str | Path | None = None) -> Path:
    return storage.vector_index_path(root)


def init_store(root: str | Path | None = None) -> None:
    storage.init_store(root)


def add_record(
    category: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    root: str | Path | None = None,
) -> MemoryRecord:
    storage.init_store(root)
    cfg = recall_config.load_config(root)
    normalized_category = recall_config.normalize_category(category)
    metadata = dict(metadata or {})
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
) -> dict[str, Any]:
    return retrieval.query(query_text, categories, exclude_categories, limit, root, summarize)


def rebuild_index(root: str | Path | None = None) -> dict[str, Any]:
    return index_store.rebuild(root)


def doctor(root: str | Path | None = None) -> dict[str, Any]:
    storage.init_store(root)
    index_report = index_store.diagnostics(root)
    backend = storage.backend(root)
    return {
        "backend": backend,
        "schema_version": storage.schema_version(root),
        "records": index_report["records"],
        "index_records": index_report["index_records"],
        "index_complete": index_report["index_complete"],
        "missing_index_ids": index_report["missing_index_ids"],
        "stale_index_ids": index_report["stale_index_ids"],
        "storage_path": str(db_path(root) if backend == "sqlite" else jsonl_dir(root)),
        "index_path": index_report["index_path"],
    }


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
    add.add_argument("content")
    add.add_argument("--metadata", help="JSON metadata object.")

    search = subparsers.add_parser("query")
    search.add_argument("query_text")
    search.add_argument("--category", action="append", dest="categories")
    search.add_argument("--exclude-category", action="append", dest="exclude_categories")
    search.add_argument("--limit", type=int, default=8)
    search.add_argument("--summary", action="store_true")

    define = subparsers.add_parser("define-category")
    define.add_argument("name")
    define.add_argument("--description")
    define.add_argument("--weight", type=float, default=1.0)

    subparsers.add_parser("rebuild-index")
    subparsers.add_parser("doctor")

    args = parser.parse_args()
    if args.command == "init":
        init_store(args.root)
        print(recall_config.config_path(args.root))
    elif args.command == "add":
        record = add_record(args.category, args.content, parse_metadata(args.metadata), args.root)
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


if __name__ == "__main__":
    main()
