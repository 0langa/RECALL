#!/usr/bin/env python3
"""Store a session summary before context compaction."""

from __future__ import annotations

import argparse
import json

import _recall_path  # noqa: F401
import capture_policy
from hook_io import normalize_hook_event, read_hook_input
import memory_manager
from summarizer import summarize_texts
import turn_buffer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    parser.add_argument("--metadata", default="{}")
    parser.add_argument("--provider", default="codex")
    args = parser.parse_args()
    payload, raw = read_hook_input()
    event = normalize_hook_event(
        payload,
        raw,
        fallback_event="PreCompact",
        provider=args.provider,
        fallback_root=args.root,
    )
    root = event.root
    if not turn_buffer.is_active(root, event.session_id, event.turn_id):
        print(json.dumps({"continue": True}))
        return
    if not capture_policy.should_store_precompact(root):
        print(json.dumps({"continue": True}))
        return

    text = event.compaction_text()
    if not text:
        print(json.dumps({"continue": True}))
        return
    summary = summarize_texts([text], token_budget=700)
    metadata = json.loads(args.metadata)
    session_id = event.session_id or "session"
    card_metadata = memory_manager.build_card_metadata(
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
                "hook_event": event.event_name,
                "trigger": event.trigger,
                "session_id": session_id,
                "turn_id": event.turn_id,
                "idempotency_key": event.idempotency_key("PreCompact"),
                "claim_key": f"session_summary:{session_id}",
                "claim_value": summary[:220],
                **event.provider_metadata(capture_channel="hook"),
                **metadata,
            },
    )
    existing = next(
        (
            record
            for record in memory_manager.iter_records(root)
            if record.category == "session_summaries"
            and str((record.metadata or {}).get("session_id") or "") == session_id
            and str((record.metadata or {}).get("status") or "active") not in {"archived", "superseded"}
        ),
        None,
    )
    if existing is None:
        memory_manager.add_record_if_useful("session_summaries", summary, card_metadata, root)
    else:
        memory_manager.edit_record(
            existing.id,
            root,
            content=summary,
            summary="Session compaction checkpoint.",
            details=summary,
            source="pre_compact",
            status="active",
            importance=0.7,
            confidence=0.8,
        )
    print(json.dumps({"continue": True}))


if __name__ == "__main__":
    main()
