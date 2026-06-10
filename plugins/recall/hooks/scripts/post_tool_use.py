#!/usr/bin/env python3
"""Capture useful command and debugging memories after tool use."""

from __future__ import annotations

import argparse
import json
import re

import _recall_path  # noqa: F401
from hook_io import (
    event_name,
    patch_targets,
    read_hook_input,
    root_from_payload,
    tool_command,
    tool_response_text,
)
import memory_manager
import turn_buffer


ERROR_RE = re.compile(r"(?i)\b(error|exception|traceback|failed|failure)\b")
SUCCESS_RE = re.compile(r"(?i)\b(passed|success|succeeded|done|0 failures|exit[_ ]code: 0)\b")
MAX_CAPTURE_CHARS = 700
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
READ_ONLY_COMMAND_RE = re.compile(
    r"(?i)^\s*(?:Get-Content|Get-ChildItem|Select-String|Select-Object|Get-Location|"
    r"rg\b|git\s+status\b|git\s+log\b|git\s+show\b|dir\b|ls\b|pwd\b|cat\b|type\b)"
)
TEST_COMMAND_RE = re.compile(r"(?i)\b(pytest|unittest|npm\s+test|pnpm\s+test|yarn\s+test|go\s+test|cargo\s+test)\b")
BUILD_COMMAND_RE = re.compile(r"(?i)\b(build|build_plugin|package|inspect_package|smoke_recall)\b")


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
        if ERROR_RE.search(line) or SUCCESS_RE.search(line):
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


def classify_signal(tool_name: str, command: str | None, content: str) -> tuple[str, bool, float, list[str]]:
    command = (command or "").strip()
    exit_code = exit_code_from_output(content)
    if ERROR_RE.search(content) or (exit_code is not None and exit_code != 0):
        return "test_fail" if TEST_COMMAND_RE.search(command) else "error_root_cause", True, 0.85, ["failure"]
    if tool_name == "apply_patch":
        return "file_patch", True, 0.75, ["file-edit", "patch"]
    if READ_ONLY_COMMAND_RE.search(command):
        return "generic_low_signal", False, 0.1, ["read-only"]
    if TEST_COMMAND_RE.search(command) and SUCCESS_RE.search(content):
        return "test_pass", True, 0.65, ["tests"]
    if BUILD_COMMAND_RE.search(command) and SUCCESS_RE.search(content):
        return "build_pass", True, 0.65, ["build"]
    if command and SUCCESS_RE.search(content):
        return "generic_low_signal", False, 0.2, ["command"]
    return "generic_low_signal", False, 0.1, ["tool-use"]


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

    content = compact_tool_response(tool_name, command, output)
    category = "debug_history" if ERROR_RE.search(content) else "commands"
    if category == "commands" and tool_name != "apply_patch" and not SUCCESS_RE.search(content) and not command:
        print(json.dumps({"continue": True}))
        return

    safe_content = memory_manager.redact_secrets(content)
    signal, durable_candidate, importance, tags = classify_signal(tool_name, command, safe_content)
    if not durable_candidate:
        print(json.dumps({"continue": True}))
        return

    turn_buffer.append_event(
        root,
        session_id,
        turn_id,
        {
            "event": "post_tool_use",
            "source": "PostToolUse",
            "hook_event": event_name(payload, "PostToolUse"),
            "tool_name": tool_name,
            "command": command,
            "tool_use_id": payload.get("tool_use_id"),
            "signal": signal,
            "summary": clean_output_line(safe_content.splitlines()[-1]) if safe_content.splitlines() else signal,
            "details": safe_content,
            "durable_candidate": durable_candidate,
            "importance_hint": importance,
            "tags": ["tool-use", tool_name.lower() if tool_name else "tool", *tags],
            "category_hint": category,
            "exit_code": exit_code_from_output(safe_content),
        },
    )
    print(json.dumps({"continue": True}))


if __name__ == "__main__":
    main()
