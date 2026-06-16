#!/usr/bin/env python3
"""Capture useful command and debugging memories after tool use."""

from __future__ import annotations

import argparse
import json
import re

import _recall_path  # noqa: F401
import capture_policy
import config as recall_config
from hook_io import (
    idempotency_key,
    patch_targets,
    read_hook_input,
    root_from_payload,
    tool_command,
    tool_response_text,
)
import security
import turn_buffer


ERROR_RE = re.compile(r"(?i)\b(error|exception|traceback|failed|failure)\b")
SUCCESS_RE = re.compile(r"(?i)\b(passed|success|succeeded|done|0 failures|exit[_ ]code: 0)\b")
TEST_RESULT_LINE_RE = re.compile(r"(?i)\b(Ran\s+\d+\s+tests?|\d+\s+passed|0 failures)\b")
MAX_CAPTURE_CHARS = 700
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
def clean_output_line(line: str) -> str:
    return ANSI_RE.sub("", line).strip()


def exit_code_from_output(output: str) -> int | None:
    match = re.search(r"(?i)\bexit[_ ]code:\s*(-?\d+)\b", output)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def compact_tool_response(tool_name: str, command: str | None, output: str) -> str:
    if tool_name == "apply_patch":
        targets = patch_targets(command or "")
        target_text = ", ".join(targets[:8]) if targets else "unknown files"
        status = "success" if SUCCESS_RE.search(output) else "completed"
        return f"Tool: apply_patch\nFiles: {target_text}\nResult: {status}"

    lines = [clean_output_line(line) for line in output.splitlines() if clean_output_line(line)]
    selected: list[str] = []
    for line in lines:
        if ERROR_RE.search(line) or SUCCESS_RE.search(line) or TEST_RESULT_LINE_RE.search(line):
            selected.append(line)
    exit_code = exit_code_from_output(output)
    if exit_code is not None:
        selected.append(f"exit_code: {exit_code}")
    if not selected and command:
        selected = ["Result: completed"]
    body = "\n".join(selected)
    if len(body) > MAX_CAPTURE_CHARS:
        body = body[:MAX_CAPTURE_CHARS].rstrip() + "\n[truncated]"
    parts = [f"Tool: {tool_name}" if tool_name else "", f"Command: {command}" if command else "", body]
    return "\n".join(part for part in parts if part)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    parser.add_argument("--command")
    args = parser.parse_args()
    payload, raw = read_hook_input()
    root = root_from_payload(payload, args.root)
    session_id = str(payload.get("session_id") or "")
    turn_id = str(payload.get("turn_id") or "")
    if not turn_buffer.is_active(root, session_id, turn_id):
        print(json.dumps({"continue": True}))
        return

    tool_name = str(payload.get("tool_name") or "").strip()
    command = args.command or tool_command(payload)
    output = tool_response_text(payload, raw)
    if not output and not args.command:
        print(json.dumps({"continue": True}))
        return

    cfg = recall_config.load_config_if_present(root)
    mode = str(cfg.get("capture_mode", "standard"))
    content = compact_tool_response(tool_name, command, output)
    safe_content = security.redact_text(content)
    decision = capture_policy.classify_tool_capture(
        root=root,
        payload=payload,
        tool_name=tool_name,
        command=command or "",
        content=safe_content,
        patch_targets=patch_targets(command or "") if tool_name == "apply_patch" else None,
        mode=mode,
    )
    if decision is None:
        print(json.dumps({"continue": True}))
        return

    event = {
        "durable_candidate": True,
        "signal": decision.signal,
        "summary": decision.summary,
        "details": decision.details,
        "category_hint": decision.category,
        "tags": decision.tags,
        "importance": decision.importance,
        "confidence": decision.confidence,
        "record_kind": decision.record_kind,
        "tool_name": tool_name,
        "command": command,
        "tool_use_id": payload.get("tool_use_id"),
        "exit_code": capture_policy.exit_code(payload, safe_content),
        "idempotency_key": idempotency_key(payload, "PostToolUse"),
    }
    turn_buffer.append_event(root, session_id, turn_id, event)
    if cfg.get("observability_mode") == "debug":
        import observability
        observability.trace(root, "tool_evidence_buffered", {"signal": decision.signal, "record_kind": decision.record_kind})
    print(json.dumps({"continue": True}))


if __name__ == "__main__":
    main()
