#!/usr/bin/env python3
"""Detect explicit memory/category cues in user prompts."""

from __future__ import annotations

import argparse
import json
import re

import _recall_path  # noqa: F401
from hook_io import additional_context, read_hook_input, root_from_payload
import memory_manager


REMEMBER_RE = re.compile(r"(?is)\bremember(?: this| that)?:?\s*(?P<content>.+)")
CATEGORY_RE = re.compile(
    r"(?is)\bdefine category\s+(?P<name>[a-zA-Z0-9_-]+)(?:\s*:\s*(?P<description>.+))?"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    parser.add_argument("--category", default="preferences")
    args = parser.parse_args()
    payload, raw = read_hook_input()
    root = root_from_payload(payload, args.root)
    prompt = str(payload.get("prompt") or raw).strip()
    if not prompt:
        print(json.dumps({"continue": True}))
        return

    category_match = CATEGORY_RE.search(prompt)
    if category_match:
        details = memory_manager.define_category(
            category_match.group("name"),
            category_match.group("description"),
            1.0,
            root,
        )
        print(
            json.dumps(
                additional_context(
                    "UserPromptSubmit",
                    f"RECALL defined category `{category_match.group('name')}`: {details['description']}",
                )
            )
        )
        return

    remember_match = REMEMBER_RE.search(prompt)
    if remember_match:
        record = memory_manager.add_record(
            args.category,
            remember_match.group("content").strip(),
            {"source": "prompt_inspector"},
            root,
        )
        print(
            json.dumps(
                additional_context(
                    "UserPromptSubmit",
                    f"RECALL saved memory #{record.id} in `{record.category}`.",
                )
            )
        )
        return

    print(json.dumps({"continue": True}))


if __name__ == "__main__":
    main()
