"""Helpers for Codex hook stdin/stdout handling."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


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
        return fallback
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        return str(Path(cwd).resolve())
    return None


def additional_context(event_name: str, text: str) -> dict[str, Any]:
    return {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": text,
        },
    }
