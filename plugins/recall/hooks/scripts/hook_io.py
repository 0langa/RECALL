"""Helpers for Codex hook stdin/stdout handling."""

from __future__ import annotations

import json
import hashlib
import re
import sys
from pathlib import Path
from typing import Any

import _recall_path  # noqa: F401
import project_context


def idempotency_key(payload: dict[str, Any], fallback_event: str) -> str | None:
    """Return a stable hook-delivery key when Codex provides delivery identity."""

    event = event_name(payload, fallback_event)
    tool_use_id = string_field(payload, "tool_use_id")
    session_id = string_field(payload, "session_id")
    turn_id = string_field(payload, "turn_id")
    if not tool_use_id and not turn_id:
        return None
    identity = {
        "event": event,
        "session_id": session_id,
        "turn_id": turn_id,
        "tool_use_id": tool_use_id,
        "trigger": string_field(payload, "trigger"),
    }
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()
    return f"hook:{digest}"


def read_hook_input() -> tuple[dict[str, Any], str]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}, ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}, raw
    return payload if isinstance(payload, dict) else {}, raw


def root_from_payload(payload: dict[str, Any], fallback: str | None = None) -> str | None:
    if fallback:
        return str(Path(fallback).resolve())
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        resolved = project_context.resolve_project_root(cwd)
        return str(resolved) if resolved is not None else None
    return None


def cwd_from_payload(payload: dict[str, Any], fallback: str | None = None) -> str | None:
    if fallback:
        return str(Path(fallback).resolve())
    cwd = payload.get("cwd")
    return str(Path(cwd).resolve()) if isinstance(cwd, str) and cwd.strip() else None


def event_name(payload: dict[str, Any], fallback: str) -> str:
    value = payload.get("hook_event_name")
    return value if isinstance(value, str) and value.strip() else fallback


def string_field(payload: dict[str, Any], *names: str) -> str:
    for name in names:
        value = payload.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def first_present(*values: str) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def strings_from_messages(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    extracted: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).lower()
        content = item.get("content")
        if role not in {"assistant", "user", "system", ""}:
            continue
        if isinstance(content, str) and content.strip():
            extracted.append(content.strip())
        elif isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    parts.append(part["text"].strip())
            if parts:
                extracted.append("\n".join(part for part in parts if part))
    return extracted


def compact_json(value: Any, max_chars: int = 1200) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, sort_keys=True)
        except TypeError:
            text = str(value)
    text = text.strip()
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "\n[truncated]"
    return text


def pre_compact_text(payload: dict[str, Any], raw: str) -> str:
    direct = first_present(
        string_field(payload, "summary", "compaction_summary", "context", "notes"),
        string_field(payload, "last_assistant_message", "assistant_message"),
    )
    if direct:
        return direct
    messages = strings_from_messages(payload.get("messages") or payload.get("transcript"))
    if messages:
        return "\n".join(messages[-8:])
    return ""


def stop_text(payload: dict[str, Any], raw: str) -> str:
    direct = string_field(
        payload,
        "last_assistant_message",
        "assistant_message",
        "final_assistant_message",
        "summary",
    )
    if direct:
        return direct
    messages = strings_from_messages(payload.get("messages") or payload.get("transcript"))
    if messages:
        return messages[-1]
    return ""


def tool_command(payload: dict[str, Any]) -> str:
    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    return string_field(tool_input, "command", "cmd", "description")


def tool_response_text(payload: dict[str, Any], raw: str) -> str:
    response = payload.get("tool_response")
    if isinstance(response, dict):
        return "\n".join(
            part
            for part in [
                compact_json(response.get("stdout"), 1500),
                compact_json(response.get("stderr"), 1500),
                compact_json(response.get("output"), 1500),
                compact_json(response.get("message"), 800),
                f"exit_code: {response.get('exit_code')}" if response.get("exit_code") is not None else "",
                "success: true" if response.get("success") is True else "",
                "success: false" if response.get("success") is False else "",
            ]
            if part
        )
    return compact_json(response, 2000)


def patch_targets(command: str) -> list[str]:
    targets: list[str] = []
    for match in re.finditer(r"^\*\*\* (?:Update|Add|Delete) File: (.+)$", command, re.MULTILINE):
        target = match.group(1).strip()
        if target and target not in targets:
            targets.append(target)
    return targets


def additional_context(event_name: str, text: str) -> dict[str, Any]:
    return {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": text,
        },
    }
