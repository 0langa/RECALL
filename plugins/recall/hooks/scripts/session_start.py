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
import turn_policy


MAX_INJECTED_CHARS = 2000


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
        return "The store is empty. This is valid; RECALL does not require a save."
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
    root = event.root
    # SessionStart has no task-owned turn identity. Generated fallback ids must
    # not look like a late delivery from an unknown turn.
    policy = turn_policy.policy_status(root, provider=event.provider)
    if policy["disabled"]:
        print(json.dumps(turn_policy.disabled_result(hook=True)))
        return
    if not root or not recall_config.project_is_active(root):
        print(json.dumps({"continue": True}))
        return
    parts = [recall_contract.compact_contract_text()]
    # SessionStart precedes the task prompt. Policy/config contain no memory
    # cards, but even inventory reads must wait until task scope is known.
    overview = store_overview(root) if policy["scope_known"] and not policy.get("closed") else ""
    if overview:
        parts.append(overview)
    if recall_config.memory_dir(root).name == recall_config.LEGACY_MEMORY_DIR_NAME:
        parts.append(
            "This project still uses the legacy .codex_memory store. Migrate it to the "
            "provider-neutral .recall directory with `recall_skill.py migrate-store --apply` "
            "(safe copy; counts verified; the legacy directory is kept as a frozen backup)."
        )
    text = "\n".join(parts)
    # Hard cap the injected context so RECALL never dominates per-session
    # token cost (~2000 chars ≈ 500 tokens).
    if len(text) > MAX_INJECTED_CHARS:
        text = text[: MAX_INJECTED_CHARS - 1].rstrip() + "…"
    print(json.dumps(additional_context("SessionStart", text)))


if __name__ == "__main__":
    main()
