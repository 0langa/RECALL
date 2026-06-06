#!/usr/bin/env python3
"""Store a session summary before context compaction."""

from __future__ import annotations

import argparse
import json

import _recall_path  # noqa: F401
from hook_io import read_hook_input, root_from_payload
import memory_manager
from summarizer import summarize_texts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    parser.add_argument("--metadata", default="{}")
    args = parser.parse_args()
    payload, raw = read_hook_input()
    root = root_from_payload(payload, args.root)
    raw = raw.strip()
    if not raw:
        print(json.dumps({"continue": True}))
        return
    summary = summarize_texts([raw], token_budget=700)
    record = memory_manager.add_record(
        "session_summaries",
        summary,
        {"source": "pre_compact", "hook_event": payload.get("hook_event_name"), **json.loads(args.metadata)},
        root,
    )
    print(json.dumps({"continue": True, "systemMessage": f"RECALL saved compaction checkpoint #{record.id}."}))


if __name__ == "__main__":
    main()
