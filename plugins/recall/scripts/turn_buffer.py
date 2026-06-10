"""Runtime-only turn evidence for RECALL hooks."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_EVENT = "recall.turn_event.v1"
SCHEMA_FINALIZER = "recall.finalizer_request.v1"
SCHEMA_ACTIVATION = "recall.turn_activation.v1"
MAX_EVENT_DETAILS = 1200
MAX_LAST_MESSAGE = 1600


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_name(value: str | None, fallback: str) -> str:
    text = (value or "").strip() or fallback
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", text)[:160] or fallback


def memory_dir(root: str | Path | None) -> Path:
    base = Path(root or os.getcwd()).resolve()
    return base / ".codex_memory"


def runtime_dir(root: str | Path | None) -> Path:
    return memory_dir(root) / "runtime"


def turn_events_path(root: str | Path | None, session_id: str | None, turn_id: str | None) -> Path:
    return runtime_dir(root) / "turns" / safe_name(session_id, "session") / f"{safe_name(turn_id, 'turn')}.jsonl"


def finalizer_request_path(root: str | Path | None, session_id: str | None, turn_id: str | None) -> Path:
    request_name = f"{safe_name(session_id, 'session')}-{safe_name(turn_id, 'turn')}.json"
    return runtime_dir(root) / "finalizer_requests" / request_name


def activation_path(root: str | Path | None, session_id: str | None, turn_id: str | None) -> Path:
    activation_name = f"{safe_name(session_id, 'session')}-{safe_name(turn_id, 'turn')}.json"
    return runtime_dir(root) / "activations" / activation_name


def truncate(text: str, limit: int) -> str:
    clean = text.strip()
    if len(clean) <= limit:
        return clean
    return clean[:limit].rstrip() + "\n[truncated]"


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def append_event(root: str | Path | None, session_id: str | None, turn_id: str | None, event: dict[str, Any]) -> Path:
    path = turn_events_path(root, session_id, turn_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(event)
    payload.setdefault("schema", SCHEMA_EVENT)
    payload.setdefault("session_id", session_id)
    payload.setdefault("turn_id", turn_id)
    payload.setdefault("timestamp", utc_now())
    if isinstance(payload.get("details"), str):
        payload["details"] = truncate(payload["details"], MAX_EVENT_DETAILS)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return path


def load_events(root: str | Path | None, session_id: str | None, turn_id: str | None) -> list[dict[str, Any]]:
    path = turn_events_path(root, session_id, turn_id)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    quarantine_dir = runtime_dir(root) / "quarantine"
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            quarantine_dir.mkdir(parents=True, exist_ok=True)
            quarantine = quarantine_dir / f"{path.stem}-{line_number}.txt"
            quarantine.write_text(line, encoding="utf-8")
            continue
        if isinstance(item, dict):
            events.append(item)
    return events


def mark_active(root: str | Path | None, session_id: str | None, turn_id: str | None, prompt: str) -> Path:
    path = activation_path(root, session_id, turn_id)
    payload = {
        "schema": SCHEMA_ACTIVATION,
        "status": "active",
        "created_at": utc_now(),
        "session_id": session_id,
        "turn_id": turn_id,
        "reason": "explicit-recall-mention",
        "prompt_excerpt": truncate(prompt, 500),
    }
    atomic_write_json(path, payload)
    return path


def is_active(root: str | Path | None, session_id: str | None, turn_id: str | None) -> bool:
    path = activation_path(root, session_id, turn_id)
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return isinstance(payload, dict) and payload.get("status") == "active"


def is_dirty(events: list[dict[str, Any]]) -> bool:
    for event in events:
        if event.get("durable_candidate") is True and event.get("signal") != "generic_low_signal":
            return True
    return False


def summarize_events(events: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for event in events:
        if event.get("durable_candidate") is not True:
            continue
        summary.append(
            {
                "signal": event.get("signal"),
                "summary": event.get("summary"),
                "command": event.get("command"),
                "details_excerpt": truncate(str(event.get("details") or ""), 260) if event.get("details") else None,
                "category_hint": event.get("category_hint"),
                "tags": event.get("tags", []),
            }
        )
        if len(summary) >= limit:
            break
    return summary


def finalizer_status(root: str | Path | None, session_id: str | None, turn_id: str | None) -> str:
    path = finalizer_request_path(root, session_id, turn_id)
    if not path.exists():
        return "none"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "corrupt"
    status = str(payload.get("status") or "requested")
    return status if status in {"requested", "finalized", "corrupt"} else "requested"


def create_finalizer_request(
    root: str | Path | None,
    *,
    session_id: str | None,
    turn_id: str | None,
    cwd: str | None,
    plugin_root: str | None,
    adapter: str,
    transcript_path: str | None,
    last_assistant_message: str,
    events: list[dict[str, Any]],
) -> Path:
    path = finalizer_request_path(root, session_id, turn_id)
    payload = {
        "schema": SCHEMA_FINALIZER,
        "status": "requested",
        "created_at": utc_now(),
        "session_id": session_id,
        "turn_id": turn_id,
        "cwd": cwd,
        "plugin_root": plugin_root,
        "adapter": adapter,
        "transcript_path": transcript_path,
        "last_assistant_message": truncate(last_assistant_message, MAX_LAST_MESSAGE),
        "candidate_count": len([event for event in events if event.get("durable_candidate") is True]),
        "candidate_summary": summarize_events(events),
        "policy": {
            "max_new_cards": 5,
            "prefer_lifecycle_updates": True,
            "allowed_commands": [
                "review-memory",
                "retrieve-memory",
                "save-turn-card",
                "confirm-memory",
                "resolve-memory",
                "stale-memory",
                "supersede-memory",
                "merge-memories",
                "prune-memory",
            ],
            "write_scope": ".codex_memory only",
            "network": "not required",
        },
    }
    atomic_write_json(path, payload)
    return path


def mark_finalized(root: str | Path | None, session_id: str | None, turn_id: str | None) -> None:
    path = finalizer_request_path(root, session_id, turn_id)
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    if not isinstance(payload, dict):
        return
    payload["status"] = "finalized"
    payload["finalized_at"] = utc_now()
    atomic_write_json(path, payload)
