#!/usr/bin/env python3
"""Memory hygiene helpers and planning for RECALL memory stores."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, NamedTuple

import config as recall_config
from embedder import tokenize
import memory_lifecycle
import memory_noise
from services import provenance_service
import security
import storage


NEAR_DUPLICATE_THRESHOLD = 0.72
CURRENT_STATUSES = {"active", "validated", "open", "hypothesis"}
SAFE_ACTIONS = {"stale", "prune", "merge", "supersede", "needs_confirmation", "refresh_source"}


@dataclass(frozen=True)
class HygieneProposal:
    id: int | None
    proposed_action: str
    confidence: float
    reason: str
    safe_to_apply: bool
    related_ids: tuple[int, ...] = ()
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "proposed_action": self.proposed_action,
            "confidence": round(self.confidence, 4),
            "reason": self.reason,
            "safe_to_apply": self.safe_to_apply,
        }
        if self.related_ids:
            payload["related_ids"] = list(self.related_ids)
        if self.details:
            payload["details"] = self.details
        return payload


class RelatedRecord(NamedTuple):
    kind: str
    record: storage.MemoryRecord
    similarity: float


def normalized_metadata_value(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.lower().split())
    if isinstance(value, list):
        return sorted(str(item).lower().strip() for item in value if str(item).strip())
    return value


def content_fingerprint(category: str, content: str, metadata: dict[str, Any] | None = None) -> str:
    metadata = metadata or {}
    payload = {
        "category": recall_config.normalize_category(category),
        "content": " ".join(content.lower().split()),
        "source": normalized_metadata_value(metadata.get("source")),
        "tool_name": normalized_metadata_value(metadata.get("tool_name")),
        "command": normalized_metadata_value(metadata.get("command")),
        "status": normalized_metadata_value(metadata.get("status")),
        "tags": normalized_metadata_value(metadata.get("tags", [])),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def token_jaccard(left: str, right: str) -> float:
    left_tokens = set(tokenize(left))
    right_tokens = set(tokenize(right))
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def same_memory_family(record: storage.MemoryRecord, category: str, metadata: dict[str, Any]) -> bool:
    if record.category != recall_config.normalize_category(category):
        return False
    record_metadata = record.metadata or {}
    for key in ("source", "tool_name"):
        requested = str(metadata.get(key) or "").strip().lower()
        existing = str(record_metadata.get(key) or "").strip().lower()
        if requested or existing:
            return requested == existing
    return True


def find_related_record(
    category: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    root: str | None = None,
) -> RelatedRecord | None:
    metadata = metadata or {}
    fingerprint = content_fingerprint(category, content, metadata)
    best: RelatedRecord | None = None
    for record in storage.iter_records(root):
        if not same_memory_family(record, category, metadata):
            continue
        if (record.metadata or {}).get("recall_fingerprint") == fingerprint:
            return RelatedRecord("exact", record, 1.0)
        similarity = token_jaccard(content, record.content)
        if similarity >= NEAR_DUPLICATE_THRESHOLD and (best is None or similarity > best.similarity):
            best = RelatedRecord("near", record, similarity)
    return best


def _record_text(record: storage.MemoryRecord) -> str:
    metadata = record.metadata or {}
    return " ".join(
        str(value)
        for value in (
            record.content,
            metadata.get("summary"),
            metadata.get("details"),
        )
        if value
    )


def _status(record: storage.MemoryRecord) -> str:
    return str((record.metadata or {}).get("status") or "active").lower()


def _is_current(record: storage.MemoryRecord) -> bool:
    return _status(record) in CURRENT_STATUSES


def _confidence(record: storage.MemoryRecord) -> float:
    metadata = record.metadata or {}
    values = [
        float(metadata.get("importance", 0.5) or 0.5),
        float(metadata.get("confidence", 0.5) or 0.5),
        float(metadata.get("trust", metadata.get("confidence", 0.5)) or 0.5),
    ]
    return sum(values) / len(values)


def _fingerprint(record: storage.MemoryRecord) -> str:
    metadata = record.metadata or {}
    return str(metadata.get("recall_fingerprint") or content_fingerprint(record.category, record.content, metadata))


def _project_file(root: str | Path | None, source_path: str) -> Path:
    return recall_config.project_root(root) / provenance_service.project_relative_path(root or Path.cwd(), source_path)


def route_memory(candidate_fact: str) -> dict[str, Any]:
    """Route a candidate fact to the right long-term surface."""

    text = " ".join(candidate_fact.strip().split())
    lowered = text.lower()
    if not text:
        return {
            "action": "route-memory",
            "route": "current_chat_only",
            "confidence": 1.0,
            "reason": "empty candidate has no durable content",
            "follow_up": "none",
        }
    if security.contains_secret(text):
        return {
            "action": "route-memory",
            "route": "reject",
            "confidence": 1.0,
            "reason": "secret-like content must not be stored",
            "follow_up": "redact secret and keep only non-sensitive operational fact",
        }
    if any(marker in lowered for marker in ("skill.md", "skills/", ".codex-plugin", ".claude-plugin", "kimi.plugin.json", "hooks.json", "plugin manifest")):
        return {
            "action": "route-memory",
            "route": "skill_or_plugin_instructions",
            "confidence": 0.86,
            "reason": "candidate changes reusable agent/plugin behavior, so source instructions should own it",
            "follow_up": "edit repo skill/plugin docs, then save only durable project decision if needed",
        }
    if any(marker in lowered for marker in ("agents.md", "claude.md", "config.toml", "settings.json", "provider config", "codex settings", "kimi code config")):
        return {
            "action": "route-memory",
            "route": "provider_config",
            "confidence": 0.82,
            "reason": "candidate describes agent/provider configuration rather than project memory",
            "follow_up": "update provider config or agent guidance file",
        }
    if any(marker in lowered for marker in ("readme", "docs/", ".md", "release notes", "architecture doc", "runbook", "install guide")):
        return {
            "action": "route-memory",
            "route": "repo_docs",
            "confidence": 0.8,
            "reason": "candidate describes documented project truth that belongs in repository docs",
            "follow_up": "update docs first; save a concise Recall pointer only if future agents need retrieval",
        }
    if any(marker in lowered for marker in ("temporary", "draft", "scratch", "this chat only", "do not remember", "one-off")):
        return {
            "action": "route-memory",
            "route": "current_chat_only",
            "confidence": 0.84,
            "reason": "candidate appears temporary or explicitly scoped to current conversation",
            "follow_up": "do not write Recall memory",
        }
    return {
        "action": "route-memory",
        "route": "recall_memory",
        "confidence": 0.72,
        "reason": "candidate looks like durable project context",
        "follow_up": "use save-insight after category and evidence are clear",
    }


def _source_proposal(record: storage.MemoryRecord, root: str | Path | None) -> HygieneProposal | None:
    metadata = record.metadata or {}
    if metadata.get("source_kind") != "file" or not metadata.get("source_path") or not _is_current(record):
        return None
    try:
        source_path = str(metadata["source_path"])
        path = _project_file(root, source_path)
    except Exception as exc:  # noqa: BLE001 - hygiene report should not abort scan.
        return HygieneProposal(record.id, "stale", 0.85, f"source path is invalid: {exc}", True)
    if not path.is_file():
        return HygieneProposal(record.id, "stale", 0.94, "source_path no longer exists", True, details={"source_path": source_path})
    expected_hash = str(metadata.get("source_hash") or "")
    if expected_hash:
        observed_hash = provenance_service.hash_file(path)
        if observed_hash != expected_hash:
            return HygieneProposal(
                record.id,
                "stale",
                0.91,
                "source_path content hash changed",
                True,
                details={"source_path": source_path, "observed_source_hash": observed_hash},
            )
    return HygieneProposal(record.id, "refresh_source", 0.88, "source-backed memory still matches current file", True, details={"source_path": source_path})


def _command_stale_proposal(record: storage.MemoryRecord) -> HygieneProposal | None:
    if record.category != "commands" or not _is_current(record):
        return None
    metadata = record.metadata or {}
    validation = str(
        metadata.get("validation_status")
        or metadata.get("validation_result")
        or metadata.get("last_validation_result")
        or ""
    ).lower()
    text = _record_text(record).lower()
    if validation in {"failed", "broken", "invalid"} or "validation failed" in text or "command failed" in text:
        return HygieneProposal(record.id, "stale", 0.9, "command memory validation failed", True)
    return None


def _preference_proposal(record: storage.MemoryRecord) -> HygieneProposal | None:
    if record.category != "preferences" or not _is_current(record):
        return None
    metadata = record.metadata or {}
    has_evidence = bool(metadata.get("preference_key") and metadata.get("preference_evidence_type") and metadata.get("decision_id"))
    if has_evidence:
        return None
    return HygieneProposal(
        record.id,
        "needs_confirmation",
        0.82,
        "preference memory lacks durable evidence fields",
        True,
    )


def _duplicate_proposals(records: list[storage.MemoryRecord]) -> list[HygieneProposal]:
    proposals: list[HygieneProposal] = []
    exact_duplicate_ids: set[int] = set()
    by_fingerprint: dict[tuple[str, str], list[storage.MemoryRecord]] = {}
    for record in records:
        if not _is_current(record):
            continue
        by_fingerprint.setdefault((record.category, _fingerprint(record)), []).append(record)
    for group in by_fingerprint.values():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=lambda item: item.id)
        primary = ordered[0]
        for duplicate in ordered[1:]:
            exact_duplicate_ids.add(duplicate.id)
            proposals.append(
                HygieneProposal(
                    duplicate.id,
                    "merge",
                    0.97,
                    f"exact duplicate of memory #{primary.id}",
                    True,
                    related_ids=(primary.id,),
                )
            )
    seen_pairs: set[tuple[int, int]] = set()
    current = [record for record in records if _is_current(record)]
    for index, left in enumerate(current):
        if left.id in exact_duplicate_ids:
            continue
        for right in current[index + 1 :]:
            if right.id in exact_duplicate_ids:
                continue
            if left.category != right.category:
                continue
            pair = tuple(sorted((left.id, right.id)))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            if _fingerprint(left) == _fingerprint(right):
                continue
            similarity = token_jaccard(left.content, right.content)
            if similarity >= NEAR_DUPLICATE_THRESHOLD:
                lower_confidence = min(0.89, similarity)
                primary = left if _confidence(left) >= _confidence(right) else right
                secondary = right if primary.id == left.id else left
                proposals.append(
                    HygieneProposal(
                        secondary.id,
                        "review_near_duplicate",
                        lower_confidence,
                        f"near-duplicate of memory #{primary.id}",
                        False,
                        related_ids=(primary.id,),
                        details={"similarity": round(similarity, 4)},
                    )
                )
    return proposals


def _claim_conflict_proposals(records: list[storage.MemoryRecord], claim_key: str | None = None) -> list[HygieneProposal]:
    proposals: list[HygieneProposal] = []
    groups: dict[tuple[str, str], list[storage.MemoryRecord]] = {}
    for record in records:
        metadata = record.metadata or {}
        key = str(metadata.get("claim_key") or "").strip()
        if not key or not _is_current(record):
            continue
        if claim_key and key.casefold() != claim_key.casefold():
            continue
        groups.setdefault((record.category, key.casefold()), []).append(record)
    for (_category, key), group in groups.items():
        values = {str((record.metadata or {}).get("claim_value") or "").casefold() for record in group}
        if len(values) < 2:
            continue
        winners = sorted(
            group,
            key=lambda record: (
                str((record.metadata or {}).get("status", "")).lower() == "validated",
                _confidence(record),
                record.id,
            ),
            reverse=True,
        )
        winner = winners[0]
        winner_validated = str((winner.metadata or {}).get("status", "")).lower() == "validated"
        for loser in winners[1:]:
            safe = winner_validated and _confidence(winner) >= 0.75
            proposals.append(
                HygieneProposal(
                    loser.id,
                    "supersede",
                    0.92 if safe else 0.66,
                    f"current-truth claim `{key}` conflicts with memory #{winner.id}",
                    safe,
                    related_ids=(winner.id,),
                    details={"claim_key": key, "winner_id": winner.id},
                )
            )
    return proposals


def _noise_proposals(records: Iterable[storage.MemoryRecord]) -> list[HygieneProposal]:
    proposals = []
    for record in records:
        reason = memory_noise.archive_reason(record)
        if reason:
            proposals.append(HygieneProposal(record.id, "prune", 0.88, reason, True))
    return proposals


def _single_record_proposals(records: list[storage.MemoryRecord], root: str | Path | None) -> list[HygieneProposal]:
    proposals: list[HygieneProposal] = []
    for record in records:
        for proposal in (
            _source_proposal(record, root),
            _command_stale_proposal(record),
            _preference_proposal(record),
        ):
            if proposal is not None:
                proposals.append(proposal)
    proposals.extend(_noise_proposals(records))
    return proposals


def _dedupe_proposals(proposals: list[HygieneProposal]) -> list[HygieneProposal]:
    priority = {
        "merge": 0,
        "supersede": 1,
        "stale": 2,
        "prune": 3,
        "needs_confirmation": 4,
        "refresh_source": 5,
        "review_near_duplicate": 6,
    }
    best: dict[tuple[int | None, str, tuple[int, ...]], HygieneProposal] = {}
    for proposal in proposals:
        key = (proposal.id, proposal.proposed_action, proposal.related_ids)
        if key not in best or proposal.confidence > best[key].confidence:
            best[key] = proposal
    return sorted(best.values(), key=lambda item: (item.id is None, item.id or 0, priority.get(item.proposed_action, 99)))


def hygiene_plan(
    root: str | Path | None = None,
    *,
    limit: int | None = None,
    scope: str = "project",
    claim_key: str | None = None,
) -> dict[str, Any]:
    records = list(storage.iter_records(root))
    inspected_records = records[:limit] if limit is not None else records
    proposals = _dedupe_proposals(
        [
            *_single_record_proposals(inspected_records, root),
            *_duplicate_proposals(inspected_records),
            *_claim_conflict_proposals(inspected_records, claim_key),
        ]
    )
    if limit is not None:
        proposals = proposals[:limit]
    requires_confirmation = [
        proposal.id
        for proposal in proposals
        if proposal.id is not None and not proposal.safe_to_apply
    ]
    return {
        "action": "hygiene-plan",
        "scope": scope,
        "inspected": len(inspected_records),
        "proposals": [proposal.to_dict() for proposal in proposals],
        "requires_confirmation": requires_confirmation,
        "safe_to_apply_count": sum(1 for proposal in proposals if proposal.safe_to_apply),
    }


def hygiene_scan(root: str | Path | None = None, *, limit: int | None = None) -> dict[str, Any]:
    plan = hygiene_plan(root, limit=limit)
    counts: dict[str, int] = {}
    for proposal in plan["proposals"]:
        counts[proposal["proposed_action"]] = counts.get(proposal["proposed_action"], 0) + 1
    return {
        "action": "hygiene-scan",
        "inspected": plan["inspected"],
        "candidate_ids": [proposal["id"] for proposal in plan["proposals"] if proposal["id"] is not None],
        "counts": counts,
        "proposals": plan["proposals"],
        "requires_confirmation": plan["requires_confirmation"],
    }


def _apply_proposal(proposal: dict[str, Any], root: str | Path | None) -> dict[str, Any]:
    action = str(proposal["proposed_action"])
    record_id = proposal.get("id")
    related_ids = list(proposal.get("related_ids") or [])
    reason = str(proposal.get("reason") or "Applied by memory hygiene.")
    if action not in SAFE_ACTIONS:
        return {"id": record_id, "action": action, "applied": False, "reason": "not safe action"}
    if record_id is None:
        return {"id": None, "action": action, "applied": False, "reason": "missing target id"}
    if action == "stale":
        updated = memory_lifecycle.mark_stale(int(record_id), root, reason)
    elif action == "prune":
        updated = memory_lifecycle.prune(int(record_id), root, reason)
    elif action == "needs_confirmation":
        updated = memory_lifecycle.update_metadata(
            int(record_id),
            {
                "status": "needs_confirmation",
                "needs_confirmation_at": utc_now(),
                "lifecycle_note": reason,
            },
            root,
        )
    elif action == "merge":
        if not related_ids:
            return {"id": record_id, "action": action, "applied": False, "reason": "missing primary id"}
        result = memory_lifecycle.merge(int(related_ids[0]), [int(record_id)], root, reason)
        return {
            "id": record_id,
            "action": action,
            "applied": True,
            "primary_id": result["primary"].id,
            "status": result["merged"][0].metadata.get("status") if result["merged"] else None,
        }
    elif action == "supersede":
        winner_id = int((proposal.get("details") or {}).get("winner_id") or (related_ids[0] if related_ids else 0))
        if not winner_id:
            return {"id": record_id, "action": action, "applied": False, "reason": "missing winner id"}
        result = memory_lifecycle.supersede(int(record_id), winner_id, root, reason)
        return {"id": record_id, "action": action, "applied": True, "status": result["old"].metadata.get("status"), "winner_id": winner_id}
    elif action == "refresh_source":
        metadata = dict(memory_lifecycle.get_required(int(record_id), root).metadata or {})
        source_path = metadata.get("source_path")
        if not source_path:
            return {"id": record_id, "action": action, "applied": False, "reason": "missing source_path"}
        descriptor = provenance_service.describe_file(root or Path.cwd(), str(source_path))
        descriptor["source_checked_at"] = utc_now()
        descriptor["last_confirmed"] = utc_now()
        updated = memory_lifecycle.update_metadata(int(record_id), descriptor, root)
    else:
        return {"id": record_id, "action": action, "applied": False, "reason": "unsupported action"}
    return {"id": updated.id, "action": action, "applied": True, "status": updated.metadata.get("status")}


def hygiene_apply(
    root: str | Path | None = None,
    *,
    safe: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    if not safe:
        raise ValueError("hygiene-apply requires --safe.")
    plan = hygiene_plan(root, limit=limit)
    applied = [
        _apply_proposal(proposal, root)
        for proposal in plan["proposals"]
        if proposal.get("safe_to_apply") is True
    ]
    return {
        "action": "hygiene-apply",
        "mode": "safe",
        "inspected": plan["inspected"],
        "applied": applied,
        "applied_count": sum(1 for item in applied if item.get("applied")),
        "skipped_confirmation_ids": plan["requires_confirmation"],
    }


def reconcile_current_truth(
    root: str | Path | None = None,
    *,
    claim_key: str,
) -> dict[str, Any]:
    plan = hygiene_plan(root, scope="claim", claim_key=claim_key)
    proposals = [
        proposal
        for proposal in plan["proposals"]
        if proposal.get("details", {}).get("claim_key") == claim_key.casefold()
    ]
    return {
        "action": "reconcile-current-truth",
        "claim_key": claim_key,
        "inspected": plan["inspected"],
        "proposals": proposals,
        "requires_confirmation": [proposal["id"] for proposal in proposals if not proposal["safe_to_apply"]],
    }


def refresh_source_backed(root: str | Path | None = None, *, limit: int | None = None) -> dict[str, Any]:
    plan = hygiene_plan(root, limit=limit)
    refreshes = [
        proposal
        for proposal in plan["proposals"]
        if proposal.get("proposed_action") == "refresh_source" and proposal.get("safe_to_apply")
    ]
    applied = [_apply_proposal(proposal, root) for proposal in refreshes]
    return {
        "action": "refresh-source-backed",
        "checked": plan["inspected"],
        "refreshed": sum(1 for item in applied if item.get("applied")),
        "applied": applied,
    }
