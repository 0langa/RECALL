#!/usr/bin/env python3
"""Flush final session notes into RECALL."""

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
    args = parser.parse_args()
    payload, raw = read_hook_input()
    root = root_from_payload(payload, args.root)
    notes = raw.strip()
    if not notes:
        print(json.dumps({"continue": True}))
        return
    record = memory_manager.add_record(
        "project_state",
        summarize_texts([notes], token_budget=500),
        {"source": "stop"},
        root,
    )
    print(json.dumps({"continue": True, "systemMessage": f"RECALL saved session checkpoint #{record.id}."}))


if __name__ == "__main__":
    main()
