#!/usr/bin/env python3
"""Establish the RECALL contract at session start for activated projects.

For projects without an activated RECALL store this stays quiet, preserving
the opt-in behavior. For activated projects it injects the compact lifecycle
contract so every provider (Codex, Claude Code, Kimi Code) starts from the
same memory behavior without the user re-explaining it.
"""

from __future__ import annotations

import argparse
import json

import _recall_path  # noqa: F401
import config as recall_config
import contract as recall_contract
from hook_io import additional_context, normalize_hook_event, read_hook_input
import storage


def store_overview(root: str) -> str:
    counts: dict[str, int] = {}
    total = 0
    try:
        for record in storage.iter_records(root):
            total += 1
            counts[record.category] = counts.get(record.category, 0) + 1
    except Exception:  # noqa: BLE001 - a broken store must not break session start.
        return ""
    if not total:
        return "The store is empty; save durable insights as this project produces them."
    top = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:5]
    summary = ", ".join(f"{name} ({count})" for name, count in top)
    return f"The store holds {total} memories; largest categories: {summary}."


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    parser.add_argument("--provider", default="codex")
    args = parser.parse_args()
    payload, raw = read_hook_input()
    event = normalize_hook_event(
        payload,
        raw,
        fallback_event="SessionStart",
        provider=args.provider,
        fallback_root=args.root,
    )
    root = event.root or event.cwd
    if not root or not recall_config.project_is_active(root):
        print(json.dumps({"continue": True}))
        return
    parts = [recall_contract.compact_contract_text()]
    overview = store_overview(root)
    if overview:
        parts.append(overview)
    print(json.dumps(additional_context("SessionStart", "\n".join(parts))))


if __name__ == "__main__":
    main()
