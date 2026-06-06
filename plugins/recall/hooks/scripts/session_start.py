#!/usr/bin/env python3
"""Load high-signal project context at session start."""

from __future__ import annotations

import argparse
import json

import _recall_path  # noqa: F401
from hook_io import additional_context, read_hook_input, root_from_payload
import session_context


DEFAULT_CATEGORIES = ["project_state", "requirements", "risks", "constraints", "architecture"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    parser.add_argument("--query", default="current project state requirements risks constraints architecture")
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()
    payload, _ = read_hook_input()
    root = root_from_payload(payload, args.root)
    context = session_context.build_session_context(root, args.query, args.limit)
    if not context:
        print(json.dumps({"continue": True}))
        return
    print(json.dumps(additional_context("SessionStart", context)))


if __name__ == "__main__":
    main()
