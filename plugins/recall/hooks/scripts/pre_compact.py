#!/usr/bin/env python3
"""Store a session summary before context compaction."""

from __future__ import annotations

import argparse
import json

import _recall_path  # noqa: F401
import capture_policy
from hook_io import event_name, pre_compact_text, read_hook_input, root_from_payload
import memory_manager
from summarizer import summarize_texts
import turn_buffer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    parser.add_argument("--metadata", default="{}")
    args = parser.parse_args()
    payload, raw = read_hook_input()
    root = root_from_payload(payload, args.root)
    if not turn_buffer.is_active(root, str(payload.get("session_id") or ""), str(payload.get("turn_id") or "")):
        print(json.dumps({"continue": True}))
        return
    if not capture_policy.should_store_precompact(root):
        print(json.dumps({"continue": True}))
        return

    text = pre_compact_text(payload, raw)
    if not text:
        print(json.dumps({"continue": True}))
        return
    summary = summarize_texts([text], token_budget=700)
    metadata = json.loads(args.metadata)
    save_result = memory_manager.add_record_if_useful(
        "session_summaries",
        summary,
        memory_manager.build_card_metadata(
            summary="Session compaction checkpoint.",
            details=summary,
            tags=["session-summary", "compaction"],
            source="pre_compact",
            status="active",
            importance=0.7,
            confidence=0.8,
            base={
                "auto_capture_policy": "session_summary",
                "record_kind": "session_summary",
                "hook_event": event_name(payload, "PreCompact"),
                "trigger": payload.get("trigger"),
                "session_id": payload.get("session_id"),
                "turn_id": payload.get("turn_id"),
                **metadata,
            },
        ),
        root,
    )
    print(json.dumps({"continue": True}))


if __name__ == "__main__":
    main()
