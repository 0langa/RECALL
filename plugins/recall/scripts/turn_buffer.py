"""Runtime-only turn evidence for RECALL hooks."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config as recall_config


SCHEMA_EVENT = "recall.turn_event.v1"
SCHEMA_FINALIZER = "recall.finalizer_request.v1"
SCHEMA_ACTIVATION = "recall.turn_activation.v1"
MAX_EVENT_DETAILS = 1200
MAX_LAST_MESSAGE = 1600
MAX_INLINE_SUMMARY = 120
MAX_INLINE_COMMAND = 80
MAX_INLINE_DETAILS = 120


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_name(value: str | None, fallback: str) -> str:
    text = (value or "").strip() or fallback
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", text)[:160] or fallback


def memory_dir(root: str | Path | None) -> Path:
    base = Path(root or os.getcwd()).resolve()
    return recall_config.memory_dir(base)


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


def one_line(value: Any, limit: int) -> str | None:
    if value in (None, ""):
        return None
    text = " ".join(str(value).split())
    if not text:
        return None
    return truncate(text, limit).replace("\n", " ")


def compact_event_summary(event: dict[str, Any]) -> str | None:
    signal = str(event.get("signal") or "")
    summary = str(event.get("summary") or "")
    if signal == "file_patch" or str(event.get("record_kind") or "") == "file_edit":
        files = re.findall(r"([^\\/:,]+?\.[A-Za-z0-9_.-]+)", summary)
        unique = []
        for name in files:
            if name not in unique:
                unique.append(name)
        if unique:
            shown = ", ".join(unique[:3])
            suffix = f" (+{len(unique) - 3} more)" if len(unique) > 3 else ""
            return f"Edited {shown}{suffix}"
        return "Edited files"
    if signal in {"build_pass", "test_pass"}:
        return one_line(signal.replace("_", " "), MAX_INLINE_SUMMARY)
    return one_line(summary, MAX_INLINE_SUMMARY)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def append_event(root: str | Path | None, session_id: str | None, turn_id: str | None, event: dict[str, Any]) -> Path:
    path = turn_events_path(root, session_id, turn_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(event)
    idempotency_key = str(payload.get("idempotency_key") or "").strip()
    if path.exists():
        for existing in load_events(root, session_id, turn_id):
            same_delivery = idempotency_key and str(existing.get("idempotency_key") or "") == idempotency_key
            same_evidence = all(
                existing.get(key) == payload.get(key)
                for key in ("signal", "summary", "details", "command", "record_kind")
            )
            if same_delivery or same_evidence:
                return path
    payload.setdefault("schema", SCHEMA_EVENT)
    payload.setdefault("session_id", session_id)
    payload.setdefault("turn_id", turn_id)
    payload.setdefault("timestamp", utc_now())
    payload.setdefault("event_id", idempotency_key or f"{safe_name(session_id, 'session')}:{safe_name(turn_id, 'turn')}:{path.stat().st_size if path.exists() else 0}")
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
        "reason": "persistently-activated-project",
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


def summarize_events(events: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for event in events:
        if event.get("durable_candidate") is not True:
            continue
        compact: dict[str, Any] = {
            "event_id": one_line(event.get("event_id"), 80),
            "signal": one_line(event.get("signal"), 40),
            "category_hint": one_line(event.get("category_hint"), 32),
            "summary": compact_event_summary(event),
            "record_kind": one_line(event.get("record_kind"), 40),
        }
        command = one_line(event.get("command"), MAX_INLINE_COMMAND)
        if command and event.get("signal") in {"test_fail", "error_root_cause"} and not command.startswith("*** Begin Patch"):
            compact["command_hint"] = command
        if event.get("exit_code") not in (None, ""):
            compact["exit_code"] = event.get("exit_code")
        tags = event.get("tags")
        if isinstance(tags, list) and tags:
            compact["tags"] = [str(tag)[:32] for tag in tags[:4]]
        details = one_line(event.get("details"), MAX_INLINE_DETAILS)
        if details and event.get("signal") in {"test_fail", "error_root_cause", "explicit_requirement", "explicit_decision", "explicit_correction"}:
            compact["details_hint"] = details
        summary.append({key: value for key, value in compact.items() if value not in (None, "", [])})
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
            "max_new_cards": 3,
            "max_lifecycle_operations": 8,
            "prefer_lifecycle_updates": True,
            "allowed_commands": [
                "review-memory",
                "retrieve-memory",
                "apply-finalizer-batch",
            ],
            "write_scope": f"{recall_config.memory_dir(root).name} only",
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


def cleanup_success(root: str | Path | None, session_id: str | None, turn_id: str | None, *, keep_request: bool = False) -> None:
    """Remove transient evidence after a successful quiet-mode finalization."""

    for path in (turn_events_path(root, session_id, turn_id), activation_path(root, session_id, turn_id)):
        path.unlink(missing_ok=True)
        parent = path.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
    request = finalizer_request_path(root, session_id, turn_id)
    if not keep_request:
        request.unlink(missing_ok=True)


def cleanup_expired(root: str | Path | None, retention_days: int = 7) -> None:
    cutoff = datetime.now(timezone.utc).timestamp() - max(1, retention_days) * 86400
    runtime = runtime_dir(root)
    if not runtime.exists():
        return
    for folder_name in ("turns", "finalizer_requests", "activations"):
        folder = runtime / folder_name
        if not folder.exists():
            continue
        for path in folder.rglob("*"):
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        for directory in sorted((path for path in folder.rglob("*") if path.is_dir()), reverse=True):
            if not any(directory.iterdir()):
                directory.rmdir()
