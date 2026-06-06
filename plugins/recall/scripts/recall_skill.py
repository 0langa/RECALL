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


if __name__ == "__main__":
    main()
