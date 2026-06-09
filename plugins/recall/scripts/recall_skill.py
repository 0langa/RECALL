#!/usr/bin/env python3
"""Narrow adapter used by bundled RECALL skills.

This is the public skill execution surface for the stdlib V1 plugin. The
lower-level memory_manager module remains the internal backend used by hooks,
tests, and support diagnostics.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import config as recall_config
import memory_review
import memory_manager


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def load_json_card(*, file_path: str | None, use_stdin: bool) -> dict[str, Any]:
    if bool(file_path) == use_stdin:
        raise ValueError("save-turn-card requires exactly one of --file or --stdin.")
    raw = sys.stdin.read() if use_stdin else Path(str(file_path)).read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"turn card JSON is invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("turn card JSON must be an object.")
    return payload


def string_value(
    payload: dict[str, Any],
    name: str,
    *,
    required: bool = False,
    default: str | None = None,
) -> str | None:
    value = payload.get(name, default)
    if value is None:
        if required:
            raise ValueError(f"turn card is missing required field: {name}")
        return None
    if not isinstance(value, str):
        raise ValueError(f"turn card field {name} must be a string.")
    cleaned = value.strip()
    if required and not cleaned:
        raise ValueError(f"turn card field {name} must not be empty.")
    return cleaned or None


def float_value(payload: dict[str, Any], name: str) -> float | None:
    value = payload.get(name)
    if value is None:
        return None
    if not isinstance(value, (int, float)):
        raise ValueError(f"turn card field {name} must be a number.")
    return float(value)


def list_value(payload: dict[str, Any], name: str) -> list[str]:
    value = payload.get(name, [])
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"turn card field {name} must be a list of strings.")
    return [item for item in value if item.strip()]


def reject_secret_like_text(*values: str | None) -> None:
    for value in values:
        if value and memory_manager.redact_secrets(value) != value:
            raise ValueError("turn card contains secret-like text and was not stored.")


def save_turn_card(card: dict[str, Any], root: Path | None) -> dict[str, Any]:
    category = string_value(card, "category", required=True)
    content = string_value(card, "content", required=True)
    summary = string_value(card, "summary", required=True)
    details = string_value(card, "details")
    status = string_value(card, "status", default="active")
    source = string_value(card, "source", default="finalizer")
    tags = list_value(card, "tags")
    importance = float_value(card, "importance")
    confidence = float_value(card, "confidence")
    reject_secret_like_text(content, summary, details)

    metadata_base: dict[str, Any] = {
        "schema": "recall.turn_card.v1",
        "capture_reason": string_value(card, "capture_reason"),
        "session_id": string_value(card, "session_id"),
        "turn_id": string_value(card, "turn_id"),
        "evidence_ids": list_value(card, "evidence_ids"),
    }
    metadata = memory_manager.build_card_metadata(
        summary=summary,
        details=details,
        tags=tags,
        source=source,
        status=status,
        importance=importance,
        confidence=confidence,
        base={key: value for key, value in metadata_base.items() if value not in (None, [], "")},
    )
    result = memory_manager.add_record_if_useful(str(category), str(content), metadata, root)
    record = result.get("record")
    payload: dict[str, Any] = {
        "action": "save-turn-card",
        "result": result.get("action"),
        "reason": result.get("reason"),
    }
    if record is not None:
        payload["id"] = record.id
        payload["category"] = record.category
        payload["metadata"] = record.metadata
    if result.get("duplicate_id") is not None:
        payload["duplicate_id"] = result["duplicate_id"]
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RECALL skill actions against project-local memory.")
    parser.add_argument("--root", help="Project root. Defaults to the current working directory.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    save = subparsers.add_parser("save-insight")
    save.add_argument("category")
    save.add_argument("content")
    save.add_argument("--summary")
    save.add_argument("--details")
    save.add_argument("--tag", action="append", default=[])
    save.add_argument("--source", default="skill")
    save.add_argument("--status", default="active")
    save.add_argument("--importance", type=float)
    save.add_argument("--confidence", type=float)

    turn_card = subparsers.add_parser("save-turn-card")
    source = turn_card.add_mutually_exclusive_group(required=True)
    source.add_argument("--file")
    source.add_argument("--stdin", action="store_true")

    retrieve = subparsers.add_parser("retrieve-memory")
    retrieve.add_argument("query_text")
    retrieve.add_argument("--category", action="append", default=[])
    retrieve.add_argument("--exclude-category", action="append", default=[])
    retrieve.add_argument("--status", action="append", default=[])
    retrieve.add_argument("--limit", type=int, default=8)
    retrieve.add_argument("--summary", action="store_true")

    define = subparsers.add_parser("define-category")
    define.add_argument("category")
    define.add_argument("--description", required=True)
    define.add_argument("--weight", type=float, default=1.0)

    subparsers.add_parser("doctor")
    subparsers.add_parser("repair")
    subparsers.add_parser("list-categories")

    review = subparsers.add_parser("review-memory")
    review.add_argument("--status", action="append", default=[])
    review.add_argument("--category", action="append", default=[])
    review.add_argument("--source")
    review.add_argument("--limit", type=int, default=20)

    confirm = subparsers.add_parser("confirm-memory")
    confirm.add_argument("id", type=int)
    confirm.add_argument("--source-session")

    resolve = subparsers.add_parser("resolve-memory")
    resolve.add_argument("id", type=int)
    resolve.add_argument("--note")

    stale = subparsers.add_parser("stale-memory")
    stale.add_argument("id", type=int)
    stale.add_argument("--note")

    supersede = subparsers.add_parser("supersede-memory")
    supersede.add_argument("old_id", type=int)
    supersede.add_argument("new_id", type=int)
    supersede.add_argument("--note")

    merge = subparsers.add_parser("merge-memories")
    merge.add_argument("primary_id", type=int)
    merge.add_argument("secondary_id", nargs="+")
    merge.add_argument("--note")

    prune = subparsers.add_parser("prune-memory")
    prune.add_argument("id", type=int)
    prune.add_argument("--note")

    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else None

    if args.command == "save-insight":
        record = memory_manager.add_record(
            args.category,
            args.content,
            memory_manager.build_card_metadata(
                summary=args.summary,
                details=args.details,
                tags=args.tag,
                source=args.source,
                status=args.status,
                importance=args.importance,
                confidence=args.confidence,
            ),
            root,
        )
        print_json({"action": "save-insight", "id": record.id, "category": record.category})
    elif args.command == "save-turn-card":
        print_json(save_turn_card(load_json_card(file_path=args.file, use_stdin=args.stdin), root))
    elif args.command == "retrieve-memory":
        print_json(
            memory_manager.query(
                args.query_text,
                categories=args.category,
                exclude_categories=args.exclude_category,
                statuses=args.status,
                limit=args.limit,
                root=root,
                summarize=args.summary,
            )
        )
    elif args.command == "define-category":
        details = memory_manager.define_category(args.category, args.description, args.weight, root)
        print_json({"action": "define-category", "category": args.category, "details": details})
    elif args.command == "doctor":
        print_json({"action": "doctor", "report": memory_manager.doctor(root)})
    elif args.command == "repair":
        print_json({"action": "repair", "report": memory_manager.repair(root)})
    elif args.command == "list-categories":
        cfg = recall_config.load_config(root)
        categories = [
            {
                "name": name,
                "description": details["description"],
                "weight": details["weight"],
            }
            for name, details in sorted(cfg["categories"].items())
        ]
        print_json({"action": "list-categories", "categories": categories})
    elif args.command == "review-memory":
        print_json(
            {
                "action": "review-memory",
                "review": memory_review.review_memory(
                    root,
                    statuses=args.status,
                    categories=args.category,
                    source=args.source,
                    limit=args.limit,
                ),
            }
        )
    elif args.command == "confirm-memory":
        record = memory_manager.confirm_record(args.id, root, args.source_session)
        print_json({"action": "confirm-memory", "id": record.id, "metadata": record.metadata})
    elif args.command == "resolve-memory":
        record = memory_manager.resolve_record(args.id, root, args.note)
        print_json({"action": "resolve-memory", "id": record.id, "metadata": record.metadata})
    elif args.command == "stale-memory":
        record = memory_manager.mark_record_stale(args.id, root, args.note)
        print_json({"action": "stale-memory", "id": record.id, "metadata": record.metadata})
    elif args.command == "supersede-memory":
        result = memory_manager.supersede_record(args.old_id, args.new_id, root, args.note)
        print_json(
            {
                "action": "supersede-memory",
                "old": {"id": result["old"].id, "metadata": result["old"].metadata},
                "new": {"id": result["new"].id, "metadata": result["new"].metadata},
            }
        )
    elif args.command == "merge-memories":
        result = memory_manager.merge_records(args.primary_id, args.secondary_id, root, args.note)
        print_json(
            {
                "action": "merge-memories",
                "primary": {"id": result["primary"].id, "metadata": result["primary"].metadata},
                "merged": [{"id": record.id, "metadata": record.metadata} for record in result["merged"]],
            }
        )
    elif args.command == "prune-memory":
        record = memory_manager.prune_record(args.id, root, args.note)
        print_json({"action": "prune-memory", "id": record.id, "metadata": record.metadata})


if __name__ == "__main__":
    main()
