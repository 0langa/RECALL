#!/usr/bin/env python3
"""Flush final session notes into RECALL."""

from __future__ import annotations

import argparse
import json

import _recall_path  # noqa: F401
from hook_io import event_name, read_hook_input, root_from_payload, stop_text
import memory_manager
from summarizer import summarize_texts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    args = parser.parse_args()
    payload, raw = read_hook_input()
    root = root_from_payload(payload, args.root)
    notes = stop_text(payload, raw)
    if not notes:
        print(json.dumps({"continue": True}))
        return
    summary = summarize_texts([notes], token_budget=500)
    record = memory_manager.add_record(
        "project_state",
        summary,
        memory_manager.build_card_metadata(
            summary="Session stop checkpoint.",
            details=summary,
            tags=["session-stop", "project-state"],
            source="stop",
            status="active",
            importance=0.6,
            confidence=0.8,
            base={
                "hook_event": event_name(payload, "Stop"),
                "turn_id": payload.get("turn_id"),
            },
        ),
        root,
    )
    print(json.dumps({"continue": True, "systemMessage": f"RECALL saved session checkpoint #{record.id}."}))


if __name__ == "__main__":
    main()
