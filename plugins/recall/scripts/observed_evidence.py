"""Authenticated local observations, bound to one exact factual revision.

Only normalized material hook results mint receipts. Public card metadata never
does. This protects API trust boundaries, not against the local account, which
controls both source code and receipt keys. No remote attestation is claimed.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import tempfile
from typing import Any

import config as recall_config
from store_lock import exclusive_lock
import turn_policy


def factual_revision(category: str, content: str, metadata: dict[str, Any]) -> str:
    facts = {"category": category, "content": content}
    for name in ("claim_key", "claim_value", "source_path", "source_hash", "source_revision"):
        if metadata.get(name) not in (None, ""):
            facts[name] = metadata[name]
    return hashlib.sha256(json.dumps(facts, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _folder(root: str | Path | None) -> Path:
    return recall_config.memory_dir(root) / "runtime" / "observed_evidence"


def _lock_path(root: str | Path | None) -> Path:
    return _folder(root) / "observed_evidence.lock"


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temporary_name = handle.name
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if temporary_name:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass


def _key(root: str | Path | None, *, create: bool = False) -> bytes:
    path = _folder(root) / "receipt.key"
    with exclusive_lock(_lock_path(root)):
        if create and not path.exists():
            _atomic_write(path, secrets.token_bytes(32))
        try:
            return path.read_bytes()
        except OSError:
            return b""


def _signature(receipt: dict[str, Any], key: bytes) -> str:
    fields = {name: value for name, value in receipt.items() if name != "signature"}
    return hmac.new(key, json.dumps(fields, sort_keys=True, ensure_ascii=False).encode("utf-8"), hashlib.sha256).hexdigest()


def observed_content(command: str, response: dict[str, Any]) -> str:
    output = "\n".join(str(response.get(key) or "").strip() for key in ("stdout", "stderr", "output", "message") if response.get(key))
    return f"Command: {command}\n{output}\nexit_code: {response.get('exit_code')}"[:1200]


def observe_tool_result(root: str | Path | None, event: dict[str, Any]) -> dict[str, Any] | None:
    """Hook-only adapter. A command string or claimed success flag is insufficient."""
    if root is None or turn_policy.policy_status(root, event.get("session_id"), event.get("turn_id"))["disabled"]:
        return None
    import capture_policy
    response = event.get("tool_response")
    if not isinstance(response, dict) or not capture_policy.observed_material_success(str(event.get("command") or ""), response):
        return None
    content = str(event.get("details") or "")
    category = str(event.get("category_hint") or "commands")
    if category != "commands" or not content or event.get("signal") not in {"test_pass", "build_pass", "release_pass"}:
        return None
    # Only the statement about the observed command/result is eligible.
    command = str(event.get("command") or "")
    if content != observed_content(command, response):
        return None
    event_id = str(event.get("event_id") or event.get("idempotency_key") or secrets.token_hex(16))
    receipt: dict[str, Any] = {
        "schema": "recall.observed_evidence.v1", "evidence_type": "observed_tool_success",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "factual_revision": factual_revision(category, content, {}),
        "event_id": event_id, "session_id": str(event.get("session_id") or ""),
        "turn_id": str(event.get("turn_id") or ""),
        "result_sha256": hashlib.sha256(json.dumps(response, sort_keys=True).encode("utf-8")).hexdigest(),
    }
    receipt["signature"] = _signature(receipt, _key(root, create=True))
    path = _folder(root) / (hashlib.sha256(event_id.encode("utf-8")).hexdigest() + ".json")
    with exclusive_lock(_lock_path(root)):
        _atomic_write(path, json.dumps(receipt, sort_keys=True).encode("utf-8"))
    return receipt


def has_observed_evidence(root: str | Path | None, category: str, content: str, metadata: dict[str, Any]) -> bool:
    receipt = metadata.get("observed_evidence")
    if not isinstance(receipt, dict) or receipt.get("schema") != "recall.observed_evidence.v1":
        return False
    if receipt.get("factual_revision") != factual_revision(category, content, metadata):
        return False
    if receipt.get("evidence_type") != "observed_tool_success" or not receipt.get("observed_at"):
        return False
    key = _key(root)
    return bool(key and hmac.compare_digest(str(receipt.get("signature") or ""), _signature(receipt, key)))


def evidence_for_card(root: str | Path | None, category: str, content: str, metadata: dict[str, Any], evidence_ids: Any,
                      session_id: str, turn_id: str) -> dict[str, Any] | None:
    if not isinstance(evidence_ids, list):
        return None
    for event_id in evidence_ids:
        path = _folder(root) / (hashlib.sha256(str(event_id).encode("utf-8")).hexdigest() + ".json")
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(receipt, dict) or (receipt.get("session_id"), receipt.get("turn_id")) != (session_id, turn_id):
            continue
        if has_observed_evidence(root, category, content, {**metadata, "observed_evidence": receipt}):
            return receipt
    return None
