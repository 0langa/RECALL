#!/usr/bin/env python3
"""Detect explicit memory/category cues in user prompts."""

from __future__ import annotations

import argparse
import json
import re

import _recall_path  # noqa: F401
from hook_io import additional_context, read_hook_input, root_from_payload
import memory_manager
import session_context
import turn_buffer


RECALL_INVOKE_RE = re.compile(r"(?i)(@recall\b|plugin://recall\b|\$recall:)")
REMEMBER_RE = re.compile(
    r"(?is)(?:^|\n)\s*(?:please\s+)?remember(?:\s+(?:this|that|the following))?\s*[:\-]\s*(?P<content>.+)"
)
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
    if not RECALL_INVOKE_RE.search(prompt):
        print(json.dumps({"continue": True}))
        return

    turn_buffer.mark_active(
        root,
        str(payload.get("session_id") or ""),
        str(payload.get("turn_id") or ""),
        prompt,
    )
    cue_text = RECALL_INVOKE_RE.sub("", prompt).strip()

    category_match = CATEGORY_RE.search(cue_text)
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

    remember_match = REMEMBER_RE.search(cue_text)
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

    context = session_context.build_session_context(root, cue_text or prompt, 8)
    if context:
        print(json.dumps(additional_context("UserPromptSubmit", context)))
        return

    print(json.dumps({"continue": True}))


if __name__ == "__main__":
    main()
