#!/usr/bin/env python3
"""Gate RECALL end-of-turn memory finalization."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import _recall_path  # noqa: F401
import capture_policy
import config as recall_config
from finalizer_prompt import build_finalizer_prompt
from hook_io import normalize_hook_event, read_hook_input
import observability
import security
from services.finalizer_service import apply_finalizer_batch
import turn_buffer


QUIET_SAVE_SIGNALS = {"explicit_requirement", "explicit_decision", "explicit_correction", "test_fail", "error_root_cause", "read_failure"}
FAILURE_SIGNALS = {"test_fail", "error_root_cause", "read_failure"}
FINALIZER_META_MARKERS = (
    "RECALL_FINALIZER_REQUEST",
    "recall.finalizer_batch.v1",
    "apply-finalizer-batch",
    "finalizer pass complete",
)


def plugin_root() -> Path:
    env_root = os.environ.get("PLUGIN_ROOT")
    if env_root:
        return Path(env_root).resolve()
    return Path(__file__).resolve().parents[2]


def output(payload: dict) -> None:
    print(json.dumps(payload))


def finalizer_meta_text(text: str) -> bool:
    return any(marker.lower() in text.lower() for marker in FINALIZER_META_MARKERS)


def quiet_card_from_event(event: dict, *, session_id: str, turn_id: str) -> dict | None:
    signal = str(event.get("signal") or "")
    if signal not in QUIET_SAVE_SIGNALS:
        return None

    summary = str(event.get("summary") or "").strip()
    details = str(event.get("details") or summary).strip()
    if not summary or finalizer_meta_text(f"{summary}\n{details}"):
        return None

    explicit = bool(event.get("explicit_user_evidence"))
    category = str(event.get("category_hint") or ("debug_history" if signal in FAILURE_SIGNALS else "project_state"))
    if signal in FAILURE_SIGNALS:
        category = "debug_history"

    tags = event.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    evidence_id = str(event.get("event_id") or f"{session_id}:{turn_id}:{signal}").strip()
    status = "validated" if explicit and category in {"requirements", "constraints", "decisions"} else "active"
    card = {
        "category": category,
        "content": details[:4000],
        "summary": summary[:220],
        "details": details[:4000],
        "status": status,
        "tags": [str(tag) for tag in tags if str(tag).strip()][:8],
        "evidence_ids": [evidence_id] if evidence_id else [],
        "explicit_user_evidence": explicit,
        "importance": float(event.get("importance", 0.78 if explicit else 0.72)),
        "confidence": float(event.get("confidence", 0.88 if explicit else 0.82)),
        "record_kind": "semantic_memory",
        "capture_reason": "quiet semantic turn finalization",
    }
    card.update(capture_policy.claim_metadata(category, details))
    return card


def quiet_finalizer_batch(events: list[dict], *, session_id: str, turn_id: str) -> dict:
    safe_session_id = session_id.strip() or "session"
    safe_turn_id = turn_id.strip() or "turn"
    operations = []
    seen: set[tuple[str, str]] = set()
    for event in events:
        card = quiet_card_from_event(event, session_id=safe_session_id, turn_id=safe_turn_id)
        if card is None:
            continue
        key = (card["category"], card["content"])
        if key in seen:
            continue
        seen.add(key)
        operations.append({"op": "save", "card": card})
        if len(operations) >= 3:
            break
    return {
        "schema": "recall.finalizer_batch.v1",
        "session_id": safe_session_id,
        "turn_id": safe_turn_id,
        "operations": operations,
    }


def quiet_result_message(result: dict) -> str | None:
    operations = result.get("operations", [])
    if not isinstance(operations, list):
        return None
    saved = [op for op in operations if isinstance(op, dict) and op.get("op") == "save" and op.get("action") == "saved"]
    corroborated = [op for op in operations if isinstance(op, dict) and op.get("action") == "corroborated"]
    if saved:
        noun = "memory" if len(saved) == 1 else "memories"
        return f"RECALL saved {len(saved)} {noun}."
    if corroborated:
        noun = "memory" if len(corroborated) == 1 else "memories"
        return f"RECALL updated {len(corroborated)} {noun}."
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    parser.add_argument("--provider", default="codex")
    args = parser.parse_args()
    try:
        payload, raw = read_hook_input()
        event = normalize_hook_event(
            payload,
            raw,
            fallback_event="Stop",
            provider=args.provider,
            fallback_root=args.root,
        )
        root = event.root
        session_id = event.session_id
        turn_id = event.turn_id
        if not turn_buffer.is_active(root, session_id, turn_id):
            output({"continue": True})
            return

        if event.stop_hook_active:
            turn_buffer.mark_finalized(root, session_id, turn_id)
            output({"continue": True})
            return

        notes = security.redact_text(event.stop_text())
        if capture_policy.should_store_stop_note(root, notes):
            turn_buffer.append_event(root, session_id, turn_id, {
                "durable_candidate": True,
                "signal": "assistant_turn_summary",
                "summary": notes.splitlines()[0][:220],
                "details": notes,
                "category_hint": "project_state",
                "tags": ["stop", "assistant-summary"],
                "record_kind": "turn_summary_evidence",
                **event.provider_metadata(capture_channel="hook"),
            })

        events = turn_buffer.load_events(root, session_id, turn_id)

        if not turn_buffer.is_dirty(events):
            output({"continue": True})
            return

        if turn_buffer.finalizer_status(root, session_id, turn_id) in {"requested", "finalized"}:
            output({"continue": True})
            return

        cfg = recall_config.load_config_if_present(root)
        if cfg.get("observability_mode") != "debug":
            result = apply_finalizer_batch(quiet_finalizer_batch(events, session_id=session_id, turn_id=turn_id), root)
            message = quiet_result_message(result)
            response = {"continue": True}
            if message:
                response["systemMessage"] = message
            output(response)
            return

        root_path = plugin_root()
        packet = turn_buffer.create_finalizer_request(
            root,
            session_id=session_id,
            turn_id=turn_id,
            cwd=str(event.cwd or root or ""),
            plugin_root=str(root_path),
            adapter=str(root_path / "scripts" / "recall_skill.py"),
            transcript_path=event.transcript_path,
            last_assistant_message=notes,
            events=events,
        )
        packet_payload = json.loads(packet.read_text(encoding="utf-8"))
        observability.trace(root, "finalizer_requested", {"session_id": session_id, "turn_id": turn_id, "candidate_count": packet_payload.get("candidate_count")})
        output({"continue": True, "decision": "block", "reason": build_finalizer_prompt(str(packet), packet_payload)})
    except Exception as exc:  # Hooks must not break the user turn.
        output({"continue": True, "systemMessage": f"RECALL finalizer failed: {type(exc).__name__}. Evidence was retained for retry."})


if __name__ == "__main__":
    main()
