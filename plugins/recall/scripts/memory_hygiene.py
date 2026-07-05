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
from embedder import embed, tokenize
import index_store
import memory_lifecycle
import memory_noise
from services import provenance_service
import security
import storage


NEAR_DUPLICATE_THRESHOLD = 0.72
CURRENT_STATUSES = {"active", "validated", "open", "hypothesis"}
SAFE_ACTIONS = {"stale", "prune", "merge", "supersede", "needs_confirmation", "refresh_source", "redact_secret"}
SNAPSHOT_CATEGORIES = {"project_state", "session_summaries", "integrations", "tooling_quirks"}
SNAPSHOT_STALE_DAYS = 45.0
RAW_LOG_MIN_CHARS = 1200
RAW_LOG_MARKERS = ("traceback (most recent call last)", "stack trace", "==== ", "----", "\n\n\n")
VAGUE_MAX_CHARS = 60
VAGUE_PATTERNS = (
    "it works now",
    "fixed the bug",
    "made progress",
    "did some work",
    "updated stuff",
    "misc changes",
    "everything is fine",
)
# Doc-duplication detection is fully local (deterministic token containment,
# no model or network calls). Repo docs win over memory, so memories that just
# restate README/docs content are flagged for review — never auto-pruned.
DOC_DUPLICATE_CONTAINMENT = 0.8
DOC_DUPLICATE_MIN_TOKENS = 10
DOC_PARAGRAPH_MIN_TOKENS = 8
DOC_CORPUS_MAX_FILES = 200
DOC_CORPUS_MAX_BYTES_PER_FILE = 200_000
DOC_STOPWORDS = frozenset(
    "the and for with that this from into onto over under are is was were been being have has had "
    "will would should could must may might can not all any each when where which while there their "
    "them they its our your you use used using also than then such only more most some does did".split()
)


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
            pair = (min(left.id, right.id), max(left.id, right.id))
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


def _record_age_days(record: storage.MemoryRecord) -> float:
    metadata = record.metadata or {}
    freshest = record.timestamp
    for key in ("last_confirmed", "updated_at", "edited_at"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip() > str(freshest):
            freshest = value
    try:
        parsed = datetime.fromisoformat(str(freshest).replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds() / 86400)


def _secret_proposal(record: storage.MemoryRecord) -> HygieneProposal | None:
    """Stored secret-shaped content must be repaired even though writes redact."""
    metadata = record.metadata or {}
    if not security.contains_secret(record.content, metadata.get("summary"), metadata.get("details")):
        return None
    return HygieneProposal(
        record.id,
        "redact_secret",
        0.99,
        "content contains secret-shaped values; redact immediately (policy: secrets must never be stored)",
        True,
    )


def _raw_log_proposal(record: storage.MemoryRecord) -> HygieneProposal | None:
    if not _is_current(record):
        return None
    content = record.content or ""
    if len(content) < RAW_LOG_MIN_CHARS:
        return None
    lowered = content.lower()
    line_count = content.count("\n") + 1
    marker_hit = any(marker in lowered for marker in RAW_LOG_MARKERS)
    if marker_hit or line_count >= 25:
        return HygieneProposal(
            record.id,
            "prune",
            0.86,
            "looks like a raw log/output dump; archive it and save a one-line insight instead",
            True,
        )
    return None


def _vague_proposal(record: storage.MemoryRecord) -> HygieneProposal | None:
    if not _is_current(record):
        return None
    metadata = record.metadata or {}
    content = " ".join((record.content or "").split())
    lowered = content.lower()
    too_short = len(content) <= VAGUE_MAX_CHARS and not metadata.get("summary") and not metadata.get("details")
    pattern_hit = any(pattern in lowered for pattern in VAGUE_PATTERNS)
    if pattern_hit or (too_short and len(content.split()) <= 4):
        return HygieneProposal(
            record.id,
            "review_vague",
            0.7,
            "memory is too vague to act on; rewrite it as a specific verifiable fact or prune it",
            False,
        )
    return None


def _snapshot_age_proposal(
    record: storage.MemoryRecord,
    stale_days: float = SNAPSHOT_STALE_DAYS,
) -> HygieneProposal | None:
    if record.category not in SNAPSHOT_CATEGORIES or not _is_current(record):
        return None
    age_days = _record_age_days(record)
    if age_days <= stale_days:
        return None
    return HygieneProposal(
        record.id,
        "stale",
        0.84,
        f"point-in-time `{record.category}` snapshot is {int(age_days)} days old; verify it or supersede it with a current snapshot",
        True,
    )


def _metadata_gap_proposal(record: storage.MemoryRecord) -> HygieneProposal | None:
    if not _is_current(record):
        return None
    metadata = record.metadata or {}
    missing = [field for field in ("source", "status") if not str(metadata.get(field) or "").strip()]
    if not record.timestamp:
        missing.append("timestamp")
    if not missing:
        return None
    return HygieneProposal(
        record.id,
        "review_metadata",
        0.65,
        f"memory lacks useful provenance ({', '.join(missing)}); add it or the card cannot be trusted or aged correctly",
        False,
    )


def _content_tokens(text: str) -> set[str]:
    return {token for token in tokenize(text) if token not in DOC_STOPWORDS}


def _docs_corpus(root: str | Path | None) -> list[tuple[str, list[set[str]]]]:
    """Load README + docs/ markdown as per-paragraph token sets. Local-only."""
    base = recall_config.project_root(root)
    candidates: list[Path] = []
    for name in ("README.md", "readme.md"):
        path = base / name
        if path.is_file():
            candidates.append(path)
            break
    docs_dir = base / "docs"
    if docs_dir.is_dir():
        candidates.extend(sorted(docs_dir.rglob("*.md"))[: DOC_CORPUS_MAX_FILES])
    corpus: list[tuple[str, list[set[str]]]] = []
    for path in candidates[:DOC_CORPUS_MAX_FILES]:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")[:DOC_CORPUS_MAX_BYTES_PER_FILE]
        except OSError:
            continue
        paragraphs = [
            tokens
            for block in re.split(r"\n\s*\n", text)
            if len(tokens := _content_tokens(block)) >= DOC_PARAGRAPH_MIN_TOKENS
        ]
        if paragraphs:
            corpus.append((path.relative_to(base).as_posix(), paragraphs))
    return corpus


def _doc_duplicate_proposals(
    records: list[storage.MemoryRecord],
    root: str | Path | None,
) -> list[HygieneProposal]:
    corpus = _docs_corpus(root)
    if not corpus:
        return []
    proposals: list[HygieneProposal] = []
    for record in records:
        if not _is_current(record):
            continue
        memory_tokens = _content_tokens(_record_text(record))
        if len(memory_tokens) < DOC_DUPLICATE_MIN_TOKENS:
            continue
        best_path: str | None = None
        best_containment = 0.0
        for doc_path, paragraphs in corpus:
            for paragraph in paragraphs:
                containment = len(memory_tokens & paragraph) / len(memory_tokens)
                if containment > best_containment:
                    best_containment = containment
                    best_path = doc_path
        if best_path is not None and best_containment >= DOC_DUPLICATE_CONTAINMENT:
            proposals.append(
                HygieneProposal(
                    record.id,
                    "review_doc_duplicate",
                    min(0.95, best_containment),
                    (
                        f"memory restates `{best_path}` ({int(best_containment * 100)}% of its terms appear in "
                        "one doc paragraph); repo docs win — prune it or rewrite it to add non-doc insight"
                    ),
                    False,
                    details={"doc_path": best_path, "overlap": round(best_containment, 4)},
                )
            )
    return proposals


def _single_record_proposals(records: list[storage.MemoryRecord], root: str | Path | None) -> list[HygieneProposal]:
    stale_days = float(
        recall_config.load_config_if_present(root).get("staleness", {}).get("snapshot_stale_days", SNAPSHOT_STALE_DAYS)
    )
    proposals: list[HygieneProposal] = []
    for record in records:
        for proposal in (
            _secret_proposal(record),
            _source_proposal(record, root),
            _command_stale_proposal(record),
            _preference_proposal(record),
            _raw_log_proposal(record),
            _vague_proposal(record),
            _snapshot_age_proposal(record, stale_days),
            _metadata_gap_proposal(record),
        ):
            if proposal is not None:
                proposals.append(proposal)
    proposals.extend(_noise_proposals(records))
    return proposals


def _dedupe_proposals(proposals: list[HygieneProposal]) -> list[HygieneProposal]:
    priority = {
        "redact_secret": 0,
        "merge": 1,
        "supersede": 2,
        "stale": 3,
        "prune": 4,
        "needs_confirmation": 5,
        "refresh_source": 6,
        "review_near_duplicate": 7,
        "review_vague": 8,
        "review_metadata": 9,
        "review_doc_duplicate": 10,
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
            *_doc_duplicate_proposals(inspected_records, root),
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


SCAN_MAX_LISTED_PROPOSALS = 20


def hygiene_scan(root: str | Path | None = None, *, limit: int | None = None) -> dict[str, Any]:
    plan = hygiene_plan(root, limit=limit)
    counts: dict[str, int] = {}
    for proposal in plan["proposals"]:
        counts[proposal["proposed_action"]] = counts.get(proposal["proposed_action"], 0) + 1
    next_action = None
    if counts.get("redact_secret"):
        next_action = "secret-shaped content found; run hygiene-apply --safe NOW to redact it"
    elif plan["safe_to_apply_count"]:
        next_action = f"{plan['safe_to_apply_count']} safe repair(s) available; run hygiene-apply --safe"
    elif plan["requires_confirmation"]:
        next_action = "only review-required proposals remain; inspect the listed ids and fix them via manage-memory"
    # Token diet: scan is the agent-facing audit entry, so cap the listed
    # proposals; counts and candidate_ids stay complete, and hygiene-plan
    # remains the uncapped detail view.
    listed = plan["proposals"][:SCAN_MAX_LISTED_PROPOSALS]
    omitted = len(plan["proposals"]) - len(listed)
    response = {
        "action": "hygiene-scan",
        "inspected": plan["inspected"],
        "candidate_ids": [proposal["id"] for proposal in plan["proposals"] if proposal["id"] is not None],
        "counts": counts,
        "proposals": listed,
        "omitted_proposals": omitted,
        "requires_confirmation": plan["requires_confirmation"],
    }
    if omitted:
        response["proposals_note"] = f"{omitted} proposal(s) omitted for brevity; run hygiene-plan for the full list"
    if next_action:
        response["next_action"] = next_action
    return response


def _apply_proposal(proposal: dict[str, Any], root: str | Path | None) -> dict[str, Any]:
    action = str(proposal["proposed_action"])
    record_id = proposal.get("id")
    related_ids = list(proposal.get("related_ids") or [])
    reason = str(proposal.get("reason") or "Applied by memory hygiene.")
    if action not in SAFE_ACTIONS:
        return {"id": record_id, "action": action, "applied": False, "reason": "not safe action"}
    if record_id is None:
        return {"id": None, "action": action, "applied": False, "reason": "missing target id"}
    if action == "redact_secret":
        record = memory_lifecycle.get_required(int(record_id), root)
        metadata = dict(record.metadata or {})
        safe_content = security.redact_text(record.content or "")
        for key in ("summary", "details"):
            value = metadata.get(key)
            if isinstance(value, str):
                metadata[key] = security.redact_text(value)
        metadata["redacted_at"] = utc_now()
        metadata["lifecycle_note"] = reason
        updated = storage.update_record(
            int(record_id),
            category=record.category,
            content=safe_content,
            metadata=metadata,
            embedding=embed(safe_content),
            root=root,
        )
        index_store.rebuild(root)
    elif action == "stale":
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
