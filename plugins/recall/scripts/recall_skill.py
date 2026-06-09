#!/usr/bin/env python3
"""Narrow adapter used by bundled RECALL skills.

This is the public skill execution surface for the stdlib V1 plugin. The
lower-level memory_manager module remains the internal backend used by hooks,
tests, and support diagnostics.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import config as recall_config
import memory_review
import memory_manager


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


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
