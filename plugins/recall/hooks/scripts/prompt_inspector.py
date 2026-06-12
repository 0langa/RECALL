#!/usr/bin/env python3
"""Detect explicit memory/category cues in user prompts."""

from __future__ import annotations

import argparse
import json
import re

import _recall_path  # noqa: F401
import capture_policy
from hook_io import additional_context, read_hook_input, root_from_payload
import memory_manager
import config as recall_config
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
    explicit_recall = bool(RECALL_INVOKE_RE.search(prompt))
    recall_mode = str(recall_config.load_config_if_present(root).get("recall_mode", "manual"))
    if not explicit_recall and recall_mode == "manual":
        print(json.dumps({"continue": True}))
        return

    session_id = str(payload.get("session_id") or "")
    turn_id = str(payload.get("turn_id") or "")
    cue_text = RECALL_INVOKE_RE.sub("", prompt).strip() if explicit_recall else prompt

    category_match = CATEGORY_RE.search(cue_text) if explicit_recall else None
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
        if capture_policy.should_activate_turn(root, explicit_write=True):
            turn_buffer.mark_active(root, session_id, turn_id, prompt)
        return

    remember_match = REMEMBER_RE.search(cue_text) if explicit_recall else None
    if remember_match:
        remembered = remember_match.group("content").strip()
        record = memory_manager.add_record(
            args.category,
            remembered,
            memory_manager.build_card_metadata(
                summary=remembered[:220],
                source="prompt_inspector",
                status="active",
            ),
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
        if capture_policy.should_activate_turn(root, explicit_write=True):
            turn_buffer.mark_active(root, session_id, turn_id, prompt)
        return

    if capture_policy.should_activate_turn(root):
        turn_buffer.mark_active(root, session_id, turn_id, prompt)

    should_retrieve = explicit_recall or recall_mode == "always"
    if recall_mode == "relevant" and capture_policy.persistent_memory_exists(root):
        preview = memory_manager.query(cue_text or prompt, limit=1, root=root)
        should_retrieve = bool(preview["results"] and preview["results"][0]["score"] >= 0.15)

    if should_retrieve and capture_policy.persistent_memory_exists(root):
        context = session_context.build_session_context(root, cue_text or prompt, 8)
        if context:
            print(json.dumps(additional_context("UserPromptSubmit", context)))
            return

    print(json.dumps({"continue": True}))


if __name__ == "__main__":
    main()
