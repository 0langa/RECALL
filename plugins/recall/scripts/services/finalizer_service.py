#!/usr/bin/env python3
"""Atomic semantic finalization for one RECALL turn."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import config as recall_config
from embedder import embed
import index_store
import memory_hygiene
import observability
import security
import storage
import turn_buffer
import turn_policy
import observed_evidence


SCHEMA = "recall.finalizer_batch.v1"
ALLOWED_OPERATIONS = {"save", "confirm", "supersede", "resolve"}
EXPLICIT_CATEGORIES = {"requirements", "constraints", "decisions"}
CURRENT_STATUSES = {"hypothesis", "active", "validated", "open"}
PROMPT_PLAN_MARKERS = (
    "please implement this plan",
    "## summary",
    "## key changes",
    "make a plan now",
    "do you think it is in shape",
    "whatever you decide on is accepted",
    "whatever you decide on is accpeted",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _required_string(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"finalizer batch requires non-empty {name}.")
    return value.strip()


def _load_metadata(connection, record_id: int) -> tuple[str, dict[str, Any]]:
    row = connection.execute("SELECT timestamp, metadata FROM memories WHERE id = ?", (record_id,)).fetchone()
    if row is None:
        raise KeyError(f"RECALL memory #{record_id} was not found.")
    return str(row[0]), json.loads(row[1] or "{}")


def _update_metadata(connection, record_id: int, timestamp: str, metadata: dict[str, Any]) -> None:
    safe = security.redact_value(metadata)
    normalized = storage._normalized_fields(safe, timestamp)
    assignments = ", ".join(f"{name} = ?" for name in normalized)
    connection.execute(
        f"UPDATE memories SET metadata = ?, {assignments} WHERE id = ?",
        (json.dumps(safe, sort_keys=True), *normalized.values(), record_id),
    )


def _confirmation_sessions(metadata: dict[str, Any]) -> list[str]:
    values = metadata.get("confirmation_sessions", [])
    if not isinstance(values, list):
        values = []
    return [str(value) for value in values if str(value).strip()]


def _confirm_metadata(metadata: dict[str, Any], session_id: str, *, explicit: bool = False) -> dict[str, Any]:
    updated = dict(metadata)
    sessions = _confirmation_sessions(updated)
    if session_id and session_id not in sessions:
        sessions.append(session_id)
    updated["confirmation_sessions"] = sessions
    updated["confirmed_count"] = len(sessions)
    updated["last_confirmed"] = utc_now()
    if updated.get("status") in (None, "", "stale", "hypothesis"):
        updated["status"] = "active"
    updated["updated_at"] = utc_now()
    return updated


def _confirm_record(connection, record_id: int, session_id: str, turn_id: str, root: str | Path | None,
                    evidence_ids: Any = None, provider: str = "codex") -> None:
    row = connection.execute("SELECT category, content, timestamp, metadata FROM memories WHERE id = ?", (record_id,)).fetchone()
    if row is None:
        raise KeyError(f"RECALL memory #{record_id} was not found.")
    category, content, timestamp = str(row[0]), str(row[1]), str(row[2])
    metadata = _confirm_metadata(json.loads(row[3] or "{}"), session_id)
    receipt = observed_evidence.evidence_for_card(
        root, category, content, metadata, evidence_ids, session_id, turn_id, provider
    )
    if receipt:
        metadata["observed_evidence"] = receipt
    if observed_evidence.has_observed_evidence(root, category, content, metadata):
        metadata["status"] = "validated"
        metadata["validated_at"] = metadata["observed_evidence"]["observed_at"]
    elif metadata.get("status") == "validated":
        metadata["status"] = "active"
        metadata.pop("validated_at", None)
    _update_metadata(connection, record_id, timestamp, metadata)


def _prepare_card(
    card: dict[str, Any],
    session_id: str,
    turn_id: str,
    root: str | Path | None = None,
    provider: str = "codex",
) -> dict[str, Any]:
    category = recall_config.normalize_category(_required_string(card, "category"))
    content = _required_string(card, "content")
    summary = _required_string(card, "summary")
    details = str(card.get("details") or "").strip()
    if security.redact_text(content) != content or security.redact_text(summary) != summary or security.redact_text(details) != details:
        raise ValueError("finalizer batch contains secret-like text and was not stored.")
    explicit = bool(card.get("explicit_user_evidence"))
    status = str(card.get("status") or ("active" if explicit else "hypothesis"))
    if status not in {"hypothesis", "active", "validated", "open", "resolved"}:
        raise ValueError(f"unsupported finalizer status: {status}")
    tags = card.get("tags", [])
    if not isinstance(tags, list):
        raise ValueError("finalizer card tags must be a list.")
    normalized_tags = [str(tag) for tag in tags if str(tag).strip()]
    if _looks_like_raw_prompt_card(content, summary, details, normalized_tags):
        return {
            "ignored": True,
            "reason": "raw_prompt_transcript",
            "category": category,
            "content": content,
            "metadata": {
                "source": "finalizer",
                "status": "ignored",
                "reason": "raw_prompt_transcript",
                "session_id": session_id,
                "turn_id": turn_id,
            },
        }
    if _looks_like_raw_tool_wrapper_card(content, summary, details, normalized_tags):
        return {
            "ignored": True,
            "reason": "raw_tool_wrapper",
            "category": category,
            "content": content,
            "metadata": {
                "source": "finalizer",
                "status": "ignored",
                "reason": "raw_tool_wrapper",
                "session_id": session_id,
                "turn_id": turn_id,
            },
        }
    metadata = {
        "schema": "recall.turn_card.v1",
        "summary": summary,
        "details": details,
        "tags": normalized_tags,
        "source": "finalizer",
        "status": status,
        "importance": float(card.get("importance", 0.7)),
        "confidence": float(card.get("confidence", 0.75)),
        "session_id": session_id,
        "turn_id": turn_id,
        "origin_provider": provider,
        "confirmation_sessions": [session_id],
        "confirmed_count": 1,
        "capture_reason": str(card.get("capture_reason") or "semantic turn finalization"),
        "evidence_ids": card.get("evidence_ids", []),
        "explicit_user_evidence": explicit,
        "record_kind": str(card.get("record_kind") or "semantic_memory"),
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    for key in ("claim_key", "claim_value", "source_path", "source_hash", "source_revision", "merged_from"):
        if card.get(key) not in (None, "", []):
            metadata[key] = card[key]
    receipt = observed_evidence.evidence_for_card(
        root, category, content, metadata, card.get("evidence_ids"), session_id, turn_id, provider
    )
    if receipt:
        metadata["observed_evidence"] = receipt
        metadata["validated_at"] = receipt["observed_at"]
        metadata["status"] = "validated"
    elif metadata["status"] == "validated":
        metadata["status"] = "active"
    metadata["recall_fingerprint"] = memory_hygiene.content_fingerprint(category, content, metadata)
    return {"category": category, "content": content, "metadata": security.redact_value(metadata), "embedding": embed(content)}


def _looks_like_raw_prompt_card(content: str, summary: str, details: str, tags: list[str]) -> bool:
    """Detect finalizer cards that copied the user prompt instead of distilling it."""

    if len(content) < 400:
        return False
    lowered = content.casefold()
    tag_set = {tag.casefold() for tag in tags}
    prompt_tagged = bool(tag_set & {"user-prompt", "correction"})
    marker_count = sum(1 for marker in PROMPT_PLAN_MARKERS if marker in lowered)
    duplicated_prompt = bool(summary and details and summary.strip() == details.strip() and content.startswith(summary[:200]))
    return prompt_tagged and (marker_count >= 2 or duplicated_prompt)


def _looks_like_raw_tool_wrapper_card(content: str, summary: str, details: str, tags: list[str]) -> bool:
    """Detect finalizer cards that copied local tool JSON envelopes instead of a distilled fact."""

    combined = f"{content}\n{summary}\n{details}"
    lowered = combined.casefold()
    tag_set = {tag.casefold() for tag in tags}
    tool_tagged = bool(tag_set & {"tool-use", "bash", "failure", "tests"})
    has_json_wrapper = '{"code":' in lowered and '"message":' in lowered
    has_tool_prefix = "tool: bash" in lowered or "tool: " in lowered
    return tool_tagged and has_json_wrapper and has_tool_prefix


def _flag_conflicting_claims(connection, new_id: int, category: str, metadata: dict[str, Any]) -> list[int]:
    claim_key = metadata.get("claim_key")
    claim_value = metadata.get("claim_value")
    if not isinstance(claim_key, str) or not claim_key.strip() or not isinstance(claim_value, str) or not claim_value.strip():
        return []

    conflicts: list[int] = []
    rows = connection.execute(
        "SELECT id, timestamp, metadata FROM memories WHERE category = ? AND id != ?",
        (category, new_id),
    ).fetchall()
    for row in rows:
        old_id = int(row[0])
        old_timestamp = str(row[1])
        old_metadata = json.loads(row[2] or "{}")
        old_status = str(old_metadata.get("status") or "active").lower()
        if old_status not in CURRENT_STATUSES:
            continue
        if str(old_metadata.get("claim_key") or "") != claim_key:
            continue
        if str(old_metadata.get("claim_value") or "") == claim_value:
            continue

        # Claim values are opaque. New text is not authority to pick a winner.
        old_metadata.update({"review_claim_conflict": True, "updated_at": utc_now()})
        metadata.update({"review_claim_conflict": True, "updated_at": utc_now()})
        _update_metadata(connection, old_id, old_timestamp, old_metadata)
        conflicts.append(old_id)
    if conflicts:
        new_timestamp, current = _load_metadata(connection, new_id)
        current.update(metadata)
        _update_metadata(connection, new_id, new_timestamp, current)
    return conflicts


def apply_finalizer_batch(batch: dict[str, Any], root: str | Path | None) -> dict[str, Any]:
    provider = str(batch.get("origin_provider") or batch.get("provider") or "codex").strip().lower()
    if turn_policy.policy_status(
        root, batch.get("session_id"), batch.get("turn_id"), provider=provider
    )["disabled"]:
        return turn_policy.disabled_result()
    if batch.get("schema") != SCHEMA:
        raise ValueError(f"finalizer batch schema must be {SCHEMA}.")
    session_id = _required_string(batch, "session_id")
    turn_id = _required_string(batch, "turn_id")
    operations = batch.get("operations")
    if not isinstance(operations, list):
        raise ValueError("finalizer batch operations must be a list.")
    if len(operations) > 8:
        raise ValueError("finalizer batch permits at most eight operations.")
    save_operations = [op for op in operations if isinstance(op, dict) and op.get("op") == "save"]
    if len(save_operations) > 3:
        raise ValueError("finalizer batch permits at most three new cards.")
    for operation in operations:
        if not isinstance(operation, dict) or operation.get("op") not in ALLOWED_OPERATIONS:
            raise ValueError("finalizer batch contains an unsupported operation.")

    prepared_cards = [
        _prepare_card(dict(operation.get("card") or {}), session_id, turn_id, root, provider)
        for operation in save_operations
    ]
    storage.init_store(root)
    if storage.backend(root) != "sqlite":
        raise ValueError("atomic finalizer batches require the SQLite backend.")
    idempotency_key = f"finalizer:{provider}:{session_id}:{turn_id}"
    results: list[dict[str, Any]] = []
    card_index = 0
    changed = False
    with closing(storage.connect_sqlite(root)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        replay = connection.execute("SELECT value FROM recall_meta WHERE key = ?", (idempotency_key,)).fetchone()
        if replay is not None:
            connection.rollback()
            return {"action": "ignored", "reason": "idempotent_replay", "session_id": session_id, "turn_id": turn_id}
        try:
            for operation in operations:
                kind = operation["op"]
                if kind == "save":
                    prepared = prepared_cards[card_index]
                    card_index += 1
                    if prepared.get("ignored"):
                        results.append({
                            "op": "save",
                            "action": "ignored",
                            "reason": str(prepared.get("reason") or "not_durable"),
                        })
                        continue
                    duplicate = connection.execute(
                        "SELECT id, timestamp, metadata FROM memories WHERE category = ? AND content = ? ORDER BY id DESC LIMIT 1",
                        (prepared["category"], prepared["content"]),
                    ).fetchone()
                    if duplicate is not None:
                        duplicate_id = int(duplicate[0])
                        metadata = json.loads(duplicate[2] or "{}")
                        if str(metadata.get("session_id") or "") != session_id:
                            _confirm_record(
                                connection,
                                duplicate_id,
                                session_id,
                                turn_id,
                                root,
                                prepared["metadata"].get("evidence_ids"),
                                provider,
                            )
                            changed = True
                            results.append({"op": "save", "action": "corroborated", "id": duplicate_id})
                        else:
                            results.append({"op": "save", "action": "ignored_same_session_duplicate", "id": duplicate_id})
                        continue
                    timestamp = utc_now()
                    normalized = storage._normalized_fields(prepared["metadata"], timestamp)
                    cursor = connection.execute(
                        """INSERT INTO memories (
                            category, timestamp, content, metadata, embedding,
                            memory_type, title, status, trust, confidence, importance,
                            source_kind, source_path, source_hash, source_revision,
                            created_at, updated_at, confirmed_at, accessed_at, expires_at, lineage
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (prepared["category"], timestamp, prepared["content"], json.dumps(prepared["metadata"], sort_keys=True),
                         json.dumps(prepared["embedding"]), *normalized.values()),
                    )
                    new_id = int(cursor.lastrowid or 0)
                    conflicts = _flag_conflicting_claims(connection, new_id, prepared["category"], prepared["metadata"])
                    changed = True
                    result = {"op": "save", "action": "saved", "id": new_id}
                    if conflicts:
                        result["conflicting_ids"] = conflicts
                    results.append(result)
                elif kind == "confirm":
                    record_id = int(operation["id"])
                    _confirm_record(
                        connection, record_id, session_id, turn_id, root, operation.get("evidence_ids"), provider
                    )
                    changed = True
                    results.append({"op": kind, "id": record_id})
                elif kind == "resolve":
                    record_id = int(operation["id"])
                    timestamp, metadata = _load_metadata(connection, record_id)
                    metadata.update({"status": "resolved", "resolved_at": utc_now(), "updated_at": utc_now()})
                    _update_metadata(connection, record_id, timestamp, metadata)
                    changed = True
                    results.append({"op": kind, "id": record_id})
                elif kind == "supersede":
                    old_id, new_id = int(operation["old_id"]), int(operation["new_id"])
                    old_timestamp, old_metadata = _load_metadata(connection, old_id)
                    new_timestamp, new_metadata = _load_metadata(connection, new_id)
                    new_record = connection.execute("SELECT category, content FROM memories WHERE id = ?", (new_id,)).fetchone()
                    if not observed_evidence.has_observed_evidence(root, str(new_record[0]), str(new_record[1]), new_metadata):
                        raise ValueError("Finalizer supersession requires observed evidence for the replacement revision.")
                    old_metadata.update({"status": "superseded", "superseded_by": new_id, "superseded_at": utc_now(), "updated_at": utc_now()})
                    supersedes = new_metadata.get("supersedes", [])
                    if not isinstance(supersedes, list):
                        supersedes = []
                    if old_id not in supersedes:
                        supersedes.append(old_id)
                    new_metadata.update({"supersedes": supersedes, "updated_at": utc_now()})
                    _update_metadata(connection, old_id, old_timestamp, old_metadata)
                    _update_metadata(connection, new_id, new_timestamp, new_metadata)
                    changed = True
                    results.append({"op": kind, "old_id": old_id, "new_id": new_id})
            connection.execute("INSERT INTO recall_meta (key, value) VALUES (?, ?)", (idempotency_key, utc_now()))
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    if changed:
        index_store.rebuild(root)
    turn_buffer.mark_finalized(root, session_id, turn_id, provider=provider)
    turn_policy.finish_turn(root, session_id, turn_id, provider=provider)
    observability.trace(
        root,
        "finalizer_applied",
        {"session_id": session_id, "turn_id": turn_id, "origin_provider": provider, "operations": results},
    )
    cfg = recall_config.load_config_if_present(root)
    turn_buffer.cleanup_success(
        root,
        session_id,
        turn_id,
        provider=provider,
        keep_request=cfg.get("observability_mode") == "debug",
    )
    return {
        "action": "applied",
        "session_id": session_id,
        "turn_id": turn_id,
        "origin_provider": provider,
        "operations": results,
    }
