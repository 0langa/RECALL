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
SAFE_ACTIONS = {"stale", "prune", "merge", "needs_confirmation", "refresh_source", "redact_secret"}
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


def _structured_claims_compatible(
    left_metadata: dict[str, Any] | None,
    right_metadata: dict[str, Any] | None,
) -> bool:
    left_metadata = left_metadata or {}
    right_metadata = right_metadata or {}
    claim_fields = ("claim_key", "claim_value")
    left_has_claim = any(field in left_metadata for field in claim_fields)
    right_has_claim = any(field in right_metadata for field in claim_fields)
    if not left_has_claim and not right_has_claim:
        return True
    if not all(field in left_metadata and field in right_metadata for field in claim_fields):
        return False
    # Claim fields are opaque project data. Prose normalization would erase
    # meaningful distinctions in paths, identifiers, and commands.
    left_pair = (left_metadata["claim_key"], left_metadata["claim_value"])
    right_pair = (right_metadata["claim_key"], right_metadata["claim_value"])
    if not all(isinstance(value, str) and value.strip() for value in (*left_pair, *right_pair)):
        return False
    return left_pair == right_pair


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
        if (
            (record.metadata or {}).get("recall_fingerprint") == fingerprint
            and _structured_claims_compatible(record.metadata, metadata)
        ):
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


def _source_proposal(
    record: storage.MemoryRecord,
    source_observations: dict[str, dict[str, Any]],
) -> HygieneProposal | None:
    metadata = record.metadata or {}
    if metadata.get("source_kind") != "file" or not metadata.get("source_path") or not _is_current(record):
        return None
    source_path = str(metadata["source_path"])
    observation = source_observations.get(source_path)
    if observation is None:
        return HygieneProposal(record.id, "stale", 0.85, "source observation is unavailable", True,
                               details={"source_path": source_path})
    if observation["state"] != "file":
        if observation["state"] == "missing":
            reason = "source_path no longer exists"
            confidence = 0.94
        else:
            reason = "source path cannot be read"
            confidence = 0.85
        return HygieneProposal(
            record.id,
            "stale",
            confidence,
            reason,
            True,
            details={"source_path": source_path, "source_observation": observation},
        )
    expected_hash = str(metadata.get("source_hash") or "")
    if expected_hash:
        observed_hash = str(observation["sha256"])
        if observed_hash != expected_hash:
            return HygieneProposal(
                record.id,
                "stale",
                0.91,
                "source_path content hash changed",
                True,
                details={"source_path": source_path, "observed_source_hash": observed_hash,
                         "source_observation": observation},
            )
    return HygieneProposal(
        record.id,
        "refresh_source",
        0.88,
        "source-backed memory still matches current file",
        True,
        details={"source_path": source_path, "source_observation": observation},
    )


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
    if _failure_history(record) and not validation:
        return None
    if validation in {"failed", "broken", "invalid"} or "validation failed" in text or "command failed" in text:
        return HygieneProposal(record.id, "stale", 0.9, "command memory validation failed", True)
    return None


def _preference_proposal(record: storage.MemoryRecord) -> HygieneProposal | None:
    if record.category != "preferences" or not _is_current(record):
        return None
    metadata = record.metadata or {}
    evidence_type = str(metadata.get("preference_evidence_type") or "").strip().lower()
    # Mirror the write contract (services/preference_service.py): an explicit
    # user declaration needs no decision_id; observed decisions do.
    has_evidence = bool(metadata.get("preference_key")) and (
        evidence_type == "explicit_declaration"
        or bool(evidence_type and metadata.get("decision_id"))
    )
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
        for index, primary in enumerate(ordered):
            if primary.id in exact_duplicate_ids:
                continue
            for duplicate in ordered[index + 1 :]:
                if duplicate.id in exact_duplicate_ids or not _structured_claims_compatible(
                    primary.metadata,
                    duplicate.metadata,
                ):
                    continue
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
        key = str(metadata.get("claim_key") or "")
        if not key.strip() or not _is_current(record):
            continue
        if claim_key and key != claim_key:
            continue
        groups.setdefault((record.category, key), []).append(record)
    for (_category, key), group in groups.items():
        values = {str((record.metadata or {}).get("claim_value") or "") for record in group}
        if len(values) < 2:
            continue
        ordered = sorted(group, key=lambda record: record.id)
        record_ids = tuple(record.id for record in ordered)
        proposals.append(
            HygieneProposal(
                ordered[0].id,
                "review_claim_conflict",
                1.0,
                (
                    f"current-truth claim `{key}` has conflicting values; review current evidence before "
                    "choosing a winner because status, confidence, age, and record order are not authority"
                ),
                False,
                related_ids=record_ids[1:],
                details={
                    "claim_key": key,
                    "record_ids": list(record_ids),
                    "values": sorted(values),
                    "resolution": "review_required",
                },
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
        if _failure_history(record):
            return HygieneProposal(record.id, "review_failure_history", 0.86,
                                   "raw failure history may contain a useful cause or repair; review before archival", False)
        return HygieneProposal(
            record.id,
            "prune",
            0.86,
            "looks like a raw log/output dump; archive it and save a one-line insight instead",
            True,
        )
    return None


def _failure_history(record: storage.MemoryRecord) -> bool:
    return bool(re.search(r"(?i)\b(fail(?:ed|ure|ing)?|error|exception|traceback)\b", _record_text(record)))


def _review_noise_proposal(record: storage.MemoryRecord) -> HygieneProposal | None:
    """Bounded lexical review cues, never a semantic truth or deletion decision."""
    if not _is_current(record):
        return None
    metadata = record.metadata or {}
    text = " ".join(record.content.split()).lower()
    source = str(metadata.get("source") or "").lower()
    reason = None
    if record.category in {"commands", "debug_history"}:
        # Raw exploration failures are review candidates. An interpreted cause,
        # repair or lesson remains useful history and must not be auto-archived.
        if ("tool:" in text and "command:" in text and _failure_history(record)
                and re.search(r"\b(ls|dir|which|where|rg|get-command|get-childitem)\b", text)
                and not re.search(r"\b(root cause|fixed by|resolved by|workaround|because|lesson)\b", text)):
            reason = "raw exploration failure lacks an interpreted cause or repair; review its value"
    elif source in {"finalizer", "user_prompt", "prompt_inspector", "user_prompt_submit", "session_summary"}:
        if re.fullmatch(r"(?:hi|hello|hey|thanks|thank you|ok|okay|continue|go on|yes|no)[.!?]*", text):
            reason = "conversation reply or session control is not a durable project fact"
        elif ("?" in text or re.search(
                r"\b(no idea|not sure|dont know|don't know|my suspicion|i have a feeling|"
                r"would like to know|what this actually means)\b", text)):
            reason = "question or uncertainty needs review before it can represent an accepted fact"
        elif re.search(
                r"\b(your task|your job|my request|give me (?:some|a few)|"
                r"write the release notes|please find out|pause when|restart (?:the )?pc|"
                r"actually commit|you are a delegated|read-only analyze job|files mentioned by the user)\b", text):
            reason = "task request, delegation, attachment wrapper or one-time permission needs review"
    if reason is None:
        return None
    return HygieneProposal(record.id, "review_noise", 0.85, reason, False,
                           details={"detection_scope": "bounded_lexical_cues", "semantic_truth": "unknown"})


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


def _single_record_proposals(
    records: list[storage.MemoryRecord],
    root: str | Path | None,
    source_observations: dict[str, dict[str, Any]],
) -> list[HygieneProposal]:
    stale_days = float(
        recall_config.load_config_if_present(root).get("staleness", {}).get("snapshot_stale_days", SNAPSHOT_STALE_DAYS)
    )
    proposals: list[HygieneProposal] = []
    for record in records:
        for proposal in (
            _secret_proposal(record),
            _source_proposal(record, source_observations),
            _command_stale_proposal(record),
            _preference_proposal(record),
            _raw_log_proposal(record),
            _vague_proposal(record),
            _snapshot_age_proposal(record, stale_days),
            _metadata_gap_proposal(record),
            _review_noise_proposal(record),
        ):
            if proposal is not None:
                proposals.append(proposal)
    proposals.extend(_noise_proposals(records))
    return proposals


def _dedupe_proposals(proposals: list[HygieneProposal]) -> list[HygieneProposal]:
    priority = {
        "redact_secret": 0,
        "merge": 1,
        "stale": 2,
        "prune": 3,
        "needs_confirmation": 4,
        "refresh_source": 5,
        "review_claim_conflict": 6,
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
    return sorted(best.values(), key=lambda item: (
        priority.get(item.proposed_action, 99), item.id is None, item.id or 0, item.related_ids, item.reason,
    ))


PLAN_VERSION = 1


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode("utf-8")).hexdigest()


def _operation_digest(operation: dict[str, Any]) -> str:
    return _digest({key: value for key, value in operation.items()
                    if key not in {"operation_id", "reason", "confidence"}})


def _record_state(record: storage.MemoryRecord) -> str:
    # Exact opaque claim values, content and all metadata participate. The
    # rebuildable embedding/index and query score do not describe factual state.
    return _digest([record.id, record.category, record.timestamp, record.content, record.metadata])


def _store_identity(root: str | Path | None) -> str:
    return _digest([str(recall_config.memory_dir(root).resolve()), storage.backend(root)])


def _limit_value(value: int | None, name: str) -> int | None:
    if value is not None and (type(value) is not int or value < 0):
        raise ValueError(f"{name} must be a non-negative integer.")
    return value


def _source_observation(root: str | Path | None, source_path: str) -> dict[str, Any]:
    """Capture one source result for every plan field that depends on it."""

    try:
        descriptor = provenance_service.describe_file(root or Path.cwd(), source_path)
    except FileNotFoundError:
        return {"source_path": source_path, "state": "missing"}
    except (OSError, ValueError):
        return {"source_path": source_path, "state": "unreadable"}
    descriptor.pop("source_checked_at", None)
    return {
        "source_path": source_path,
        "state": "file",
        "sha256": descriptor["source_hash"],
        "descriptor": descriptor,
    }


def _source_observations(
    records: list[storage.MemoryRecord], root: str | Path | None,
) -> dict[str, dict[str, Any]]:
    paths = sorted({
        str(metadata["source_path"])
        for record in records
        if (metadata := record.metadata or {}).get("source_kind") == "file"
        and metadata.get("source_path")
    })
    return {source_path: _source_observation(root, source_path) for source_path in paths}


def _source_state(root: str | Path | None, source_path: str) -> dict[str, Any]:
    try:
        path = _project_file(root, source_path)
        if not path.is_file():
            return {"source_path": source_path, "state": "missing"}
        return {"source_path": source_path, "state": "file", "sha256": provenance_service.hash_file(path)}
    except (OSError, ValueError):
        return {"source_path": source_path, "state": "unreadable"}


def _operation(
    proposal: HygieneProposal,
    records: dict[int, storage.MemoryRecord],
    source_observations: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    payload = proposal.to_dict()
    ids = sorted({int(proposal.id), *proposal.related_ids}) if proposal.id is not None else []
    payload["preconditions"] = {str(record_id): _record_state(records[record_id]) for record_id in ids}
    paths = sorted({str(records[i].metadata["source_path"]) for i in ids
                    if records[i].metadata.get("source_kind") == "file" and records[i].metadata.get("source_path")})
    observations: list[dict[str, Any]] = []
    for path in paths:
        observation = source_observations.get(path)
        if observation is None:
            raise ValueError("Hygiene operation is missing a source observation.")
        observations.append(observation)
    payload["source_preconditions"] = [
        {
            key: observation[key]
            for key in ("source_path", "state", "sha256")
            if key in observation
        }
        for observation in observations
    ]
    if proposal.proposed_action == "refresh_source":
        assert proposal.id is not None
        source_path = str(records[int(proposal.id)].metadata["source_path"])
        observation = source_observations.get(source_path)
        if observation is None or observation["state"] != "file":
            raise ValueError("Hygiene refresh operation has no readable source observation.")
        payload["source_descriptor"] = dict(observation["descriptor"])
    payload["operation_id"] = _operation_digest(payload)
    return payload


@storage.atomic_write
def hygiene_plan(
    root: str | Path | None = None,
    *,
    limit: int | None = None,
    scan_limit: int | None = None,
    output_limit: int | None = None,
    action_limit: int | None = None,
    scope: str = "project",
    claim_key: str | None = None,
) -> dict[str, Any]:
    if limit is not None and scan_limit is not None and limit != scan_limit:
        raise ValueError("limit and scan_limit disagree.")
    scan_limit = _limit_value(scan_limit if scan_limit is not None else limit, "scan_limit")
    output_limit = _limit_value(output_limit, "output_limit")
    action_limit = _limit_value(action_limit, "action_limit")
    records = sorted(storage.iter_records(root), key=lambda record: record.id)
    inspected_records = records[:scan_limit] if scan_limit is not None else records
    source_observations = _source_observations(inspected_records, root)
    proposals = _dedupe_proposals(
        [
            *_single_record_proposals(inspected_records, root, source_observations),
            *_duplicate_proposals(inspected_records),
            *_claim_conflict_proposals(inspected_records, claim_key),
            *_doc_duplicate_proposals(inspected_records, root),
        ]
    )
    record_map = {record.id: record for record in records}
    candidates = [_operation(proposal, record_map, source_observations) for proposal in proposals]
    # A merge also updates its primary. Reserve every touched card so later
    # stale/archive/refresh operations cannot overwrite that relation or status.
    touched: set[str] = set()
    coherent: list[dict[str, Any]] = []
    collisions: list[str] = []
    for candidate in candidates:
        if candidate["safe_to_apply"]:
            affected = set(candidate["preconditions"])
            if affected & touched:
                collisions.append(candidate["operation_id"])
                continue
            touched.update(affected)
        coherent.append(candidate)
    visible = coherent[:output_limit] if output_limit is not None else coherent
    safe_operations = [proposal for proposal in visible if proposal["safe_to_apply"]]
    operations = safe_operations[:action_limit] if action_limit is not None else safe_operations
    requires_confirmation = list(
        dict.fromkeys(
            proposal["id"]
            for proposal in visible
            if proposal["id"] is not None and not proposal["safe_to_apply"]
        )
    )
    proposed_ids = {proposal.id for proposal in proposals}
    omissions = {
        "unscanned_record_ids": [record.id for record in records[len(inspected_records):]],
        "scanned_without_proposal_ids": [record.id for record in inspected_records if record.id not in proposed_ids],
        "output_operation_ids": [proposal["operation_id"] for proposal in coherent[len(visible):]],
        "action_operation_ids": [proposal["operation_id"] for proposal in safe_operations[len(operations):]],
        "conflicting_operations": collisions,
    }
    payload = {
        "action": "hygiene-plan",
        "plan_version": PLAN_VERSION,
        "store_identity": _store_identity(root),
        "snapshot_identity": _digest({str(record.id): _record_state(record) for record in records}),
        "scope": scope,
        "claim_key": claim_key,
        "limits": {"scan_limit": scan_limit, "output_limit": output_limit, "action_limit": action_limit},
        "store_record_count": len(records),
        "inspected": len(inspected_records),
        "proposals": visible,
        "operations": operations,
        "omissions": omissions,
        "truncated": any(omissions[key] for key in omissions if key != "scanned_without_proposal_ids"),
        "candidate_count": len(candidates),
        "unscanned_secret_status": "unknown" if len(records) > len(inspected_records) else "scanned",
        "requires_confirmation": requires_confirmation,
        "safe_to_apply_count": len(operations),
        "detection_scope": "bounded lexical rules; broad semantic truth is not determined",
    }
    payload["plan_id"] = _digest(payload)
    return payload


SCAN_MAX_LISTED_PROPOSALS = 20


def hygiene_scan(root: str | Path | None = None, *, limit: int | None = None,
                 scan_limit: int | None = None, output_limit: int | None = None,
                 action_limit: int | None = None) -> dict[str, Any]:
    output_limit = _limit_value(output_limit, "output_limit")
    plan = hygiene_plan(
        root,
        limit=limit,
        scan_limit=scan_limit,
        output_limit=output_limit,
        action_limit=action_limit,
    )
    counts: dict[str, int] = {}
    for proposal in plan["proposals"]:
        counts[proposal["proposed_action"]] = counts.get(proposal["proposed_action"], 0) + 1
    next_action = None
    if counts.get("redact_secret"):
        next_action = "secret-shaped content found; save a hygiene-plan and apply it with hygiene-apply --safe --plan-file"
    elif plan["safe_to_apply_count"]:
        next_action = (f"{plan['safe_to_apply_count']} safe repair(s) available; save a hygiene-plan, "
                       "then run hygiene-apply --safe --plan-file")
    elif plan["requires_confirmation"]:
        next_action = "only review-required proposals remain; inspect the listed ids and fix them via manage-memory"
    # Token diet: the default scan display is capped while its counts and ids
    # stay complete. An explicit output limit becomes part of the saved plan,
    # so the omitted operations remain visible in that plan's omissions.
    listed = plan["proposals"] if output_limit is not None else plan["proposals"][:SCAN_MAX_LISTED_PROPOSALS]
    omitted = len(plan["omissions"]["output_operation_ids"]) + len(plan["proposals"]) - len(listed)
    response = {
        "action": "hygiene-scan",
        "inspected": plan["inspected"],
        "candidate_ids": [proposal["id"] for proposal in plan["proposals"] if proposal["id"] is not None],
        "counts": counts,
        "proposals": listed,
        "omitted_proposals": omitted,
        "requires_confirmation": plan["requires_confirmation"],
        "omissions": plan["omissions"],
        "truncated": plan["truncated"] or bool(omitted),
        "store_record_count": plan["store_record_count"],
        "unscanned_secret_status": plan["unscanned_secret_status"],
        "detection_scope": plan["detection_scope"],
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
        metadata = memory_lifecycle.invalidate_verification(metadata, metadata, utc_now())
        metadata.pop("claim_key", None)
        metadata.pop("claim_value", None)
        if metadata.get("status") == "validated":
            metadata["status"] = "active"
        metadata["recall_fingerprint"] = content_fingerprint(record.category, safe_content, metadata)
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
        def rebuild_index() -> None:
            index_store.rebuild(root)

        storage.after_commit(rebuild_index, root)
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
    elif action == "refresh_source":
        metadata = dict(memory_lifecycle.get_required(int(record_id), root).metadata or {})
        source_path = metadata.get("source_path")
        if not source_path:
            return {"id": record_id, "action": action, "applied": False, "reason": "missing source_path"}
        descriptor = dict(proposal["source_descriptor"])
        descriptor["source_checked_at"] = utc_now()
        descriptor["last_confirmed"] = utc_now()
        updated = memory_lifecycle.update_metadata(int(record_id), descriptor, root)
    else:
        return {"id": record_id, "action": action, "applied": False, "reason": "unsupported action"}
    return {"id": updated.id, "action": action, "applied": True, "status": updated.metadata.get("status")}


def _validate_plan(plan: dict[str, Any], root: str | Path | None) -> None:
    if not isinstance(plan, dict):
        raise ValueError("Hygiene plan must be a JSON object.")
    if type(plan.get("plan_version")) is not int or plan.get("plan_version") != PLAN_VERSION or plan.get("action") != "hygiene-plan":
        raise ValueError("Unsupported hygiene plan version or action.")
    if plan.get("store_identity") != _store_identity(root):
        raise ValueError("Hygiene plan belongs to a different store.")
    if plan.get("plan_id") != _digest({key: value for key, value in plan.items() if key != "plan_id"}):
        raise ValueError("Hygiene plan integrity check failed; review a new plan.")
    operations = plan.get("operations")
    proposals = plan.get("proposals")
    if not isinstance(operations, list) or not isinstance(proposals, list):
        raise ValueError("Hygiene plan is missing operations or proposals.")
    touched: set[str] = set()
    for operation in operations:
        if (not isinstance(operation, dict) or operation not in proposals
                or operation.get("safe_to_apply") is not True
                or operation.get("proposed_action") not in SAFE_ACTIONS
                or type(operation.get("id")) is not int):
            raise ValueError("Hygiene plan contains an invalid safe operation.")
        if operation.get("operation_id") != _operation_digest(operation):
            raise ValueError("Hygiene operation integrity check failed.")
        preconditions = operation.get("preconditions")
        required = {str(operation["id"]), *(str(i) for i in operation.get("related_ids", []))}
        if not isinstance(preconditions, dict) or set(preconditions) != required or required & touched:
            raise ValueError("Hygiene operation has missing or conflicting record preconditions.")
        sources = operation.get("source_preconditions")
        if not isinstance(sources, list) or any(
            not isinstance(source, dict) or not isinstance(source.get("source_path"), str)
            or source.get("state") not in {"file", "missing", "unreadable"} for source in sources
        ):
            raise ValueError("Hygiene operation has invalid source preconditions.")
        if operation["proposed_action"] == "refresh_source":
            descriptor = operation.get("source_descriptor")
            if (
                not isinstance(descriptor, dict)
                or len(sources) != 1
                or sources[0].get("state") != "file"
                or descriptor.get("source_kind") != "file"
                or descriptor.get("source_path") != sources[0].get("source_path")
                or descriptor.get("source_hash") != sources[0].get("sha256")
            ):
                raise ValueError("Hygiene refresh operation has inconsistent source observation.")
        touched.update(required)


def hygiene_apply(
    root: str | Path | None = None,
    *,
    safe: bool = False,
    limit: int | None = None,
    plan: dict[str, Any] | None = None,
    action_limit: int | None = None,
) -> dict[str, Any]:
    if not safe:
        raise ValueError("hygiene-apply requires --safe.")
    if plan is None:
        raise ValueError("hygiene-apply requires an explicit reviewed plan.")
    if limit is not None and action_limit is not None and limit != action_limit:
        raise ValueError("limit and action_limit disagree.")
    action_limit = _limit_value(action_limit if action_limit is not None else limit, "action_limit")
    plan = json.loads(json.dumps(plan))
    _validate_plan(plan, root)
    selected = plan["operations"][:action_limit] if action_limit is not None else plan["operations"]
    applied = []
    with storage.write_transaction(root):
        for operation in selected:
            reason = None
            for record_id, expected in operation["preconditions"].items():
                record = storage.get_record(int(record_id), root)
                if record is None:
                    reason = "record_missing"
                    break
                if _record_state(record) != expected:
                    reason = "record_state_changed"
                    break
            if reason is None:
                for expected_source in operation["source_preconditions"]:
                    if _source_state(root, expected_source["source_path"]) != expected_source:
                        reason = "source_state_changed"
                        break
            if reason:
                outcome = {"id": operation["id"], "action": operation["proposed_action"],
                           "applied": False, "reason": reason}
            else:
                outcome = _apply_proposal(operation, root)
            outcome["operation_id"] = operation["operation_id"]
            applied.append(outcome)
    unresolved_conflicts = [
        proposal
        for proposal in plan["proposals"]
        if proposal.get("proposed_action") == "review_claim_conflict"
    ]
    return {
        "action": "hygiene-apply",
        "mode": "safe",
        "plan_id": plan["plan_id"],
        "snapshot_identity": plan["snapshot_identity"],
        "inspected": plan["inspected"],
        "applied": applied,
        "applied_count": sum(1 for item in applied if item.get("applied")),
        "unresolved_conflicts": unresolved_conflicts,
        "skipped_confirmation_ids": plan["requires_confirmation"],
        "skipped_action_limit_ids": [op["operation_id"] for op in plan["operations"][len(selected):]],
        "omissions": plan["omissions"],
    }


def reconcile_current_truth(
    root: str | Path | None = None,
    *,
    claim_key: str,
    limit: int | None = None,
    scan_limit: int | None = None,
    output_limit: int | None = None,
    action_limit: int | None = None,
) -> dict[str, Any]:
    # Keep the established read-only projection for callers that request a
    # claim review, but attach the unmodified, integrity-checked plan so a
    # caller that needs an applyable artifact never has to replan.
    plan = hygiene_plan(
        root,
        limit=limit,
        scan_limit=scan_limit,
        output_limit=output_limit,
        action_limit=action_limit,
        scope="claim",
        claim_key=claim_key,
    )
    proposals = [
        proposal
        for proposal in plan["proposals"]
        if proposal.get("details", {}).get("claim_key") == claim_key
    ]
    return {
        "action": "reconcile-current-truth",
        "claim_key": claim_key,
        "inspected": plan["inspected"],
        "proposals": proposals,
        "requires_confirmation": [proposal["id"] for proposal in proposals if not proposal["safe_to_apply"]],
        "plan": plan,
    }


def refresh_source_backed(root: str | Path | None = None, *, limit: int | None = None) -> dict[str, Any]:
    plan = hygiene_plan(root, limit=limit)
    refreshes = [
        proposal
        for proposal in plan["operations"]
        if proposal.get("proposed_action") == "refresh_source" and proposal.get("safe_to_apply")
    ]
    plan["operations"] = refreshes
    plan["plan_id"] = _digest({key: value for key, value in plan.items() if key != "plan_id"})
    applied = hygiene_apply(root, safe=True, plan=plan)["applied"]
    return {
        "action": "refresh-source-backed",
        "checked": plan["inspected"],
        "refreshed": sum(1 for item in applied if item.get("applied")),
        "applied": applied,
    }
