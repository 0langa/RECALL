"""Policy-only turn identity and no-memory interlock. Never stores prompt text.

The current scope is re-read for every action, including long-lived MCP servers.
No scope means SessionStart must defer memory-data reads. A disabled latest turn
cannot be bypassed by sending an older ID. A new prompt establishes a new scope.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import time
from typing import Any
import uuid

import config as recall_config

MAX_AGE = 7 * 86400


def _folder(root: str | Path) -> Path:
    return recall_config.memory_dir(root) / "runtime" / "policy"


def _key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict) and time.time() - float(value.get("updated_at", 0)) < MAX_AGE:
            return value
    except (OSError, ValueError, TypeError):
        pass
    return {}


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def normalize_identity(event):
    """Correlate missing IDs from explicit prompt boundaries, never prompt hashes.

    A provider without any session/transcript identity shares a workspace bucket.
    Concurrent anonymous sessions cannot be disambiguated without host identity.
    """
    if not event.root:
        return replace(event, session_id=event.session_id or uuid.uuid4().hex, turn_id=event.turn_id or uuid.uuid4().hex)
    folder = _folder(event.root)
    bucket = _key(event.provider + ":" + (event.session_id or event.transcript_path or "anonymous"))
    path = folder / (bucket + ".json")
    current = _read(path)
    session_id = event.session_id or str(current.get("session_id") or ("session-" + uuid.uuid4().hex))
    is_prompt = event.event_name == "UserPromptSubmit"
    delivery = str(event.raw_payload.get("hook_event_id") or event.raw_payload.get("delivery_id") or "")
    delivery_key = _key(delivery) if delivery else ""
    replay = bool(is_prompt and delivery_key and current.get("delivery_key") == delivery_key)
    if event.event_name == "SessionStart":
        current = {}
        if not event.session_id:
            session_id = "session-" + uuid.uuid4().hex
    if event.turn_id:
        turn_id = event.turn_id
    elif (not is_prompt or replay) and current.get("turn_id"):
        turn_id = str(current["turn_id"])
    else:
        turn_id = "turn-" + uuid.uuid4().hex
    if is_prompt:
        import capture_policy
        # Evaluate before activation, tracing, capture, or any memory-data read.
        state = {"scope_known": True, "disabled": capture_policy.no_memory_requested(event.prompt),
                 "session_id": session_id, "turn_id": turn_id, "provider": event.provider,
                 "delivery_key": delivery_key, "updated_at": time.time(), "closed": False}
        if replay:
            state["closed"] = bool(current.get("closed"))
        _write(path, state)
    elif not current:
        _write(path, {"scope_known": False, "disabled": False, "session_id": session_id,
                      "turn_id": turn_id, "provider": event.provider, "updated_at": time.time(), "closed": False})
    return replace(event, session_id=session_id, turn_id=turn_id)


def policy_status(root: str | Path | None, session_id: str | None = None, turn_id: str | None = None) -> dict[str, Any]:
    if root is None:
        return {"scope_known": False, "disabled": False, "reason": "scope_unknown"}
    folder = _folder(root)
    states = [_read(path) for path in folder.glob("*.json")] if folder.exists() else []
    states = [state for state in states if state]
    matching = [state for state in states if state.get("session_id") == session_id] if session_id else []
    if matching and turn_id:
        exact_turn = [state for state in matching if state.get("turn_id") == turn_id]
        if exact_turn:
            matching = exact_turn
    # A fabricated/stale session label cannot bypass a currently disabled scope.
    if not matching:
        active = [state for state in states if not state.get("closed")]
        # A completed no-memory turn remains conservative until a later prompt
        # establishes a new scope. It must not override that newer normal turn.
        matching = active or states
    disabled = [state for state in matching if state.get("disabled")]
    selected = max(disabled or matching, key=lambda state: float(state.get("updated_at", 0)), default={})
    known = bool(selected.get("scope_known"))
    off = bool(selected.get("disabled"))
    return {"scope_known": known, "disabled": off, "reason": "task_no_memory" if off else ("enabled" if known else "scope_unknown"),
            "session_id": selected.get("session_id"), "turn_id": selected.get("turn_id"), "closed": bool(selected.get("closed"))}


def disabled_result(*, hook: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {"action": "disabled", "reason": "task_no_memory", "memory_action": "disabled"}
    if hook:
        result["continue"] = True
        result["systemMessage"] = "RECALL is disabled for this turn."
    return result


def finish_turn(root: str | Path | None, session_id: str, turn_id: str) -> None:
    if root is None:
        return
    for path in _folder(root).glob("*.json"):
        state = _read(path)
        if state.get("session_id") == session_id and state.get("turn_id") == turn_id:
            state["closed"] = True
            # Keep the no-memory interlock until the next UserPromptSubmit.
            _write(path, state)


def cleanup_expired(root: str | Path | None) -> None:
    if root is None:
        return
    for path in _folder(root).glob("*.json"):
        if not _read(path) and time.time() - path.stat().st_mtime > MAX_AGE:
            path.unlink(missing_ok=True)
