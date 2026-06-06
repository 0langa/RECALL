#!/usr/bin/env python3
"""Capture useful command and debugging memories after tool use."""

from __future__ import annotations

import argparse
import json
import re

import _recall_path  # noqa: F401
from hook_io import additional_context, event_name, patch_targets, read_hook_input, root_from_payload, tool_command, tool_response_text
import memory_manager


ERROR_RE = re.compile(r"(?i)\b(error|exception|traceback|failed|failure)\b")
SUCCESS_RE = re.compile(r"(?i)\b(passed|success|succeeded|done|0 failures|exit[_ ]code: 0)\b")
MAX_CAPTURE_CHARS = 700


def compact_tool_response(tool_name: str, command: str | None, output: str) -> str:
    if tool_name == "apply_patch":
        targets = patch_targets(command or "")
        target_text = ", ".join(targets[:8]) if targets else "unknown files"
        status = "success" if SUCCESS_RE.search(output) else "completed"
        return f"Tool: apply_patch\nFiles: {target_text}\nResult: {status}"

    lines = [line.rstrip() for line in output.splitlines() if line.strip()]
    selected: list[str] = []
    for line in lines:
        if ERROR_RE.search(line) or SUCCESS_RE.search(line) or "exit_code" in line or "stderr" in line:
            selected.append(line)
    if not selected:
        selected = lines[-8:]
    body = "\n".join(selected)
    if len(body) > MAX_CAPTURE_CHARS:
        body = body[:MAX_CAPTURE_CHARS].rstrip() + "\n[truncated]"
    return "\n".join(part for part in [f"Tool: {tool_name}" if tool_name else "", f"Command: {command}" if command else "", body] if part)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    parser.add_argument("--command")
    args = parser.parse_args()
    payload, raw = read_hook_input()
    root = root_from_payload(payload, args.root)
    tool_name = str(payload.get("tool_name") or "").strip()
    command = args.command or tool_command(payload)
    output = tool_response_text(payload, raw)
    if not output and not args.command:
        print(json.dumps({"continue": True}))
        return

    content = compact_tool_response(tool_name, command, output)
    category = "debug_history" if ERROR_RE.search(content) else "commands"
    if category == "commands" and tool_name != "apply_patch" and not SUCCESS_RE.search(content) and not command:
        print(json.dumps({"continue": True}))
        return

    record = memory_manager.add_record(
        category,
        content,
        memory_manager.build_card_metadata(
            summary=f"{tool_name or 'Tool'} result captured.",
            details=content,
            tags=["tool-use", tool_name.lower() if tool_name else "tool"],
            source="post_tool_use",
            status="active",
            importance=0.5 if category == "commands" else 0.7,
            confidence=0.8,
            base={
                "hook_event": event_name(payload, "PostToolUse"),
                "tool_name": tool_name,
                "tool_use_id": payload.get("tool_use_id"),
                "turn_id": payload.get("turn_id"),
            },
        ),
        root,
    )
    print(
        json.dumps(
            additional_context(
                "PostToolUse",
                f"RECALL saved {record.category} memory #{record.id} from the last tool result.",
            )
        )
    )


if __name__ == "__main__":
    main()
