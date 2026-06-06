#!/usr/bin/env python3
"""Capture useful command and debugging memories after tool use."""

from __future__ import annotations

import argparse
import json
import re

import _recall_path  # noqa: F401
from hook_io import additional_context, read_hook_input, root_from_payload
import memory_manager


ERROR_RE = re.compile(r"(?i)\b(error|exception|traceback|failed|failure)\b")
SUCCESS_RE = re.compile(r"(?i)\b(passed|success|succeeded|0 failures|exit code: 0)\b")
MAX_CAPTURE_CHARS = 700


def compact_tool_response(command: str | None, output: str) -> str:
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
    return "\n".join(part for part in [f"Command: {command}" if command else "", body] if part)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    parser.add_argument("--command")
    args = parser.parse_args()
    payload, raw = read_hook_input()
    root = root_from_payload(payload, args.root)
    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    tool_response = payload.get("tool_response")
    command = args.command or tool_input.get("command")
    output = json.dumps(tool_response, sort_keys=True) if tool_response is not None else raw.strip()
    if not output and not args.command:
        print(json.dumps({"continue": True}))
        return

    content = compact_tool_response(command, output)
    category = "debug_history" if ERROR_RE.search(content) else "commands"
    if category == "commands" and not SUCCESS_RE.search(content) and not command:
        print(json.dumps({"continue": True}))
        return

    record = memory_manager.add_record(category, content, {"source": "post_tool_use"}, root)
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
