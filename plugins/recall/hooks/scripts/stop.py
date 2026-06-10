#!/usr/bin/env python3
"""Gate RECALL end-of-turn memory finalization."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

import _recall_path  # noqa: F401
from finalizer_prompt import build_finalizer_prompt
from hook_io import event_name, read_hook_input, root_from_payload, stop_text
import memory_manager
import turn_buffer


DURABLE_STOP_RE = re.compile(
    r"(?i)\b("
    r"completed|implemented|changed|fixed|verified|tested|built|released|"
    r"commit|branch|push|pull request|pr\b|tag|artifact|"
    r"requirement|decision|risk|blocker|next step|architecture|"
    r"memory|recall|hook|plugin"
    r")\b"
)


def plugin_root() -> Path:
    env_root = os.environ.get("PLUGIN_ROOT")
    if env_root:
        return Path(env_root).resolve()
    return Path(__file__).resolve().parents[2]


def output(payload: dict) -> None:
    print(json.dumps(payload))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    args = parser.parse_args()
    try:
        payload, raw = read_hook_input()
        root = root_from_payload(payload, args.root)
        session_id = str(payload.get("session_id") or "")
        turn_id = str(payload.get("turn_id") or "")
        if not turn_buffer.is_active(root, session_id, turn_id):
            output({"continue": True})
            return

        if payload.get("stop_hook_active") is True:
            turn_buffer.mark_finalized(root, session_id, turn_id)
            output({"continue": True})
            return

        notes = memory_manager.redact_secrets(stop_text(payload, raw))
        events = turn_buffer.load_events(root, session_id, turn_id)
        if notes and DURABLE_STOP_RE.search(notes):
            turn_buffer.append_event(
                root,
                session_id,
                turn_id,
                {
                    "event": "stop",
                    "source": "Stop",
                    "hook_event": event_name(payload, "Stop"),
                    "signal": "project_state",
                    "summary": notes.splitlines()[0][:220],
                    "details": notes,
                    "durable_candidate": True,
                    "importance_hint": 0.6,
                    "tags": ["stop", "project-state"],
                },
            )
            events = turn_buffer.load_events(root, session_id, turn_id)

        if not turn_buffer.is_dirty(events):
            output({"continue": True})
            return

        if turn_buffer.finalizer_status(root, session_id, turn_id) in {"requested", "finalized"}:
            output({"continue": True})
            return

        root_path = plugin_root()
        packet = turn_buffer.create_finalizer_request(
            root,
            session_id=session_id,
            turn_id=turn_id,
            cwd=str(payload.get("cwd") or root or ""),
            plugin_root=str(root_path),
            adapter=str(root_path / "scripts" / "recall_skill.py"),
            transcript_path=str(payload.get("transcript_path") or "") or None,
            last_assistant_message=notes,
            events=events,
        )
        packet_payload = json.loads(packet.read_text(encoding="utf-8"))
        output({"continue": True, "decision": "block", "reason": build_finalizer_prompt(str(packet), packet_payload)})
    except Exception as exc:  # Hooks must not break the user turn.
        output({"continue": True, "systemMessage": f"RECALL finalizer skipped: {type(exc).__name__}."})


if __name__ == "__main__":
    main()
