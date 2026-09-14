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
CURRENT_SCOPE_FILE = "current-scope.json"


def _folder(root: str | Path) -> Path:
    return recall_config.memory_dir(root) / "runtime" / "policy"


def _key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _turn_path(root: str | Path, provider: str, session_id: str, turn_id: str) -> Path:
    identity = f"turn:{provider}:{session_id}:{turn_id}"
    return _folder(root) / f"turn-{_key(identity)}.json"


def _session_pointer_path(root: str | Path, provider: str, session_token: str) -> Path:
    return _folder(root) / f"session-{_key(f'{provider}:{session_token}')}.json"


def _current_scope_path(root: str | Path) -> Path:
    return _folder(root) / CURRENT_SCOPE_FILE


def _turn_states(root: str | Path) -> list[dict[str, Any]]:
    folder = _folder(root)
    if not folder.exists():
        return []
    return [state for path in folder.glob("turn-*.json") if (state := _read(path))]


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
    session_token = event.session_id or event.transcript_path or "anonymous"
    session_pointer = _read(_session_pointer_path(event.root, event.provider, session_token))
    session_id = event.session_id or str(session_pointer.get("session_id") or ("session-" + uuid.uuid4().hex))
    is_prompt = event.event_name == "UserPromptSubmit"
    delivery = str(event.raw_payload.get("hook_event_id") or event.raw_payload.get("delivery_id") or "")
    delivery_key = _key(delivery) if delivery else ""
    if event.event_name == "SessionStart":
        if not event.session_id:
            session_id = "session-" + uuid.uuid4().hex
    replay_state: dict[str, Any] = {}
    if is_prompt and not event.turn_id and delivery_key:
        replay_state = max(
            (
                state for state in _turn_states(event.root)
                if state.get("provider") == event.provider
                and state.get("session_id") == session_id
                and state.get("delivery_key") == delivery_key
            ),
            key=lambda state: float(state.get("updated_at", 0)),
            default={},
        )
    if event.turn_id:
        turn_id = event.turn_id
    elif replay_state.get("turn_id"):
        turn_id = str(replay_state["turn_id"])
    elif (not is_prompt) and session_pointer.get("turn_id"):
        turn_id = str(session_pointer["turn_id"])
    else:
        turn_id = "turn-" + uuid.uuid4().hex
    path = _turn_path(event.root, event.provider, session_id, turn_id)
    current = _read(path)
    replay = bool(is_prompt and delivery_key and current.get("delivery_key") == delivery_key)
    if is_prompt:
        if replay:
            # The first delivery owns the policy. A retry keeps that turn's
            # closed/open state and must not replace a newer current scope.
            return replace(event, session_id=session_id, turn_id=turn_id)
        previous_turn_id = str(session_pointer.get("turn_id") or "")
        if previous_turn_id and previous_turn_id != turn_id:
            # A new prompt in the same host session is a new turn boundary.
            # Close the prior scope before publishing the new current scope.
            finish_turn(event.root, session_id, previous_turn_id, provider=event.provider)
        import capture_policy
        # Evaluate before activation, tracing, capture, or any memory-data read.
        state = {"scope_known": True, "disabled": capture_policy.no_memory_requested(event.prompt),
                 "session_id": session_id, "turn_id": turn_id, "provider": event.provider,
                 "delivery_key": delivery_key, "updated_at": time.time(), "closed": False}
        _write(path, state)
        _write(_session_pointer_path(event.root, event.provider, session_token), state)
        _write(_current_scope_path(event.root), state)
    return replace(event, session_id=session_id, turn_id=turn_id)


def policy_status(
    root: str | Path | None,
    session_id: str | None = None,
    turn_id: str | None = None,
    *,
    provider: str | None = None,
) -> dict[str, Any]:
    if root is None:
        return {"scope_known": False, "disabled": False, "reason": "scope_unknown"}
    states = _turn_states(root)
    provider_states = [state for state in states if state.get("provider") == provider] if provider else states
    active_disabled = [state for state in provider_states if state.get("disabled") and not state.get("closed")]
    selected: dict[str, Any] = {}
    if session_id and turn_id:
        exact = [
            state for state in provider_states
            if state.get("session_id") == session_id and state.get("turn_id") == turn_id
        ]
        if exact:
            # A current private scope blocks every automatic action. Otherwise,
            # preserve the exact historical turn policy for late deliveries.
            selected = max(active_disabled or exact, key=lambda state: float(state.get("updated_at", 0)))
        elif active_disabled:
            selected = max(active_disabled, key=lambda state: float(state.get("updated_at", 0)))
        elif states:
            # Once any prompt establishes policy, an event with a different
            # explicit identity is untrusted. Fail closed before memory data
            # access. Legacy activated projects with no prompt state remain
            # compatible through the scope_unknown result below.
            selected = {"scope_known": True, "disabled": True, "closed": True,
                        "session_id": session_id, "turn_id": turn_id}
        else:
            return {"scope_known": False, "disabled": False, "reason": "scope_unknown"}
    elif session_id:
        matching = [state for state in provider_states if state.get("session_id") == session_id]
        selected = max(active_disabled or matching, key=lambda state: float(state.get("updated_at", 0)), default={})
    else:
        # Contextless callers use the latest prompt scope after all active
        # scopes close. An active no-memory turn always remains conservative.
        selected = max(active_disabled, key=lambda state: float(state.get("updated_at", 0)), default={})
        if not selected:
            selected = _read(_current_scope_path(root))
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


def finish_turn(
    root: str | Path | None,
    session_id: str,
    turn_id: str,
    *,
    provider: str | None = None,
) -> None:
    if root is None:
        return
    for path in _folder(root).glob("turn-*.json"):
        state = _read(path)
        if (
            state.get("session_id") == session_id
            and state.get("turn_id") == turn_id
            and (provider is None or state.get("provider") == provider)
        ):
            state["closed"] = True
            # Keep the no-memory interlock until the next UserPromptSubmit.
            _write(path, state)
            current = _read(_current_scope_path(root))
            if current.get("session_id") == session_id and current.get("turn_id") == turn_id:
                _write(_current_scope_path(root), state)
            for pointer_path in _folder(root).glob("session-*.json"):
                pointer = _read(pointer_path)
                if (
                    pointer.get("session_id") == session_id
                    and pointer.get("turn_id") == turn_id
                    and (provider is None or pointer.get("provider") == provider)
                ):
                    _write(pointer_path, state)


def cleanup_expired(root: str | Path | None) -> None:
    if root is None:
        return
    for path in _folder(root).glob("*.json"):
        if not _read(path) and time.time() - path.stat().st_mtime > MAX_AGE:
            path.unlink(missing_ok=True)
