"""Helpers for Codex hook stdin/stdout handling."""

from __future__ import annotations

import json
import hashlib
import re
import sys
from pathlib import Path
from typing import Any

import _recall_path  # noqa: F401
from hook_events import HookEvent
import project_context


def normalize_hook_event(
    payload: dict[str, Any],
    raw: str = "",
    *,
    fallback_event: str,
    provider: str = "codex",
    fallback_root: str | None = None,
) -> HookEvent:
    return HookEvent.from_payload(
        payload,
        raw,
        fallback_event=fallback_event,
        provider=provider,
        fallback_root=fallback_root,
    )


def idempotency_key(payload: dict[str, Any], fallback_event: str) -> str | None:
    """Return a stable hook-delivery key when Codex provides delivery identity."""

    return normalize_hook_event(payload, fallback_event=fallback_event).idempotency_key(fallback_event)


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
    return normalize_hook_event(payload, fallback_event=fallback).event_name


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
    return normalize_hook_event(payload, raw, fallback_event="PreCompact").compaction_text()


def stop_text(payload: dict[str, Any], raw: str) -> str:
    return normalize_hook_event(payload, raw, fallback_event="Stop").stop_text()


def tool_command(payload: dict[str, Any]) -> str:
    return normalize_hook_event(payload, fallback_event="PostToolUse").command


def tool_response_text(payload: dict[str, Any], raw: str) -> str:
    return normalize_hook_event(payload, raw, fallback_event="PostToolUse").output_text()


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
