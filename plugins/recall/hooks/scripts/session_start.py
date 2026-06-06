#!/usr/bin/env python3
"""Load high-signal project context at session start."""

from __future__ import annotations

import argparse
import json

import _recall_path  # noqa: F401
from hook_io import additional_context, read_hook_input, root_from_payload
import memory_manager


DEFAULT_CATEGORIES = ["project_state", "requirements", "risks", "constraints", "architecture"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    parser.add_argument("--query", default="current project state requirements risks constraints architecture")
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()
    payload, _ = read_hook_input()
    root = root_from_payload(payload, args.root)
    result = memory_manager.query(args.query, DEFAULT_CATEGORIES, limit=args.limit, root=root, summarize=True)
    summary = result.get("summary") or ""
    if not summary:
        print(json.dumps({"continue": True}))
        return
    print(json.dumps(additional_context("SessionStart", f"RECALL project memory:\n{summary}")))


if __name__ == "__main__":
    main()
