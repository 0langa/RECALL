#!/usr/bin/env python3
"""Ranking and result shaping for RECALL retrieval."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import config as recall_config
from embedder import cosine, embed, tokenize
import index_store
import security
import storage
from summarizer import summarize_records


STATUS_WEIGHTS = {
    "validated": 1.1,
    "active": 1.0,
    "hypothesis": 0.72,
    "open": 0.95,
    "resolved": 0.65,
    "stale": 0.35,
    "superseded": 0.25,
    "deprecated": 0.2,
    "archived": 0.15,
}
DEFAULT_STATUS_WEIGHT = 0.8
DEFAULT_QUERY_STATUSES = {"validated", "active", "open", "resolved", "unspecified"}
SOURCE_WEIGHTS = {
    "skill": 1.05,
    "user": 1.05,
    "prompt_inspector": 1.0,
    "finalizer": 1.0,
    "smoke_recall": 1.0,
    "stop": 0.92,
    "pre_compact": 0.82,
    "post_tool_use": 0.68,
}
DEFAULT_SOURCE_WEIGHT = 0.9
CURRENT_DURABLE_CATEGORIES = {"requirements", "constraints", "decisions", "architecture", "risks", "tasks", "project_state"}
CURRENT_STATUSES = {"validated", "active", "open"}
SOURCE_BLIND_MEMORY_RE = {"recall memory", "project memory", "automatically provided", "without running commands", "without reading source"}
CATEGORY_TERMS = {
    "requirements": {"requirement", "requirements", "accepted requirements"},
    "constraints": {"constraint", "constraints"},
    "risks": {"risk", "risks", "blocker", "blockers"},
    "architecture": {"architecture", "design"},
    "decisions": {"decision", "decisions", "accepted"},
    "tasks": {"next engineer", "next work", "next steps", "todo", "tasks"},
    "project_state": {"current state", "status", "project state"},
}


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def recency_timestamp(record: storage.MemoryRecord) -> datetime:
    metadata = record.metadata or {}
    for key in ("last_confirmed", "updated_at", "timestamp"):
        value = metadata.get(key) if key != "timestamp" else record.timestamp
        if isinstance(value, str) and value.strip():
            try:
                return parse_timestamp(value)
            except ValueError:
                continue
    return parse_timestamp(record.timestamp)


def record_status(record: storage.MemoryRecord) -> str:
    status = str((record.metadata or {}).get("status", "")).strip().lower()
    return status or "unspecified"


def passes_filters(
    record: storage.MemoryRecord,
    categories: set[str] | None,
    exclude_categories: set[str] | None,
    since: datetime | None,
    statuses: set[str] | None = None,
) -> bool:
    if categories is not None and record.category not in categories:
        return False
    if exclude_categories is not None and record.category in exclude_categories:
        return False
    if since is not None and parse_timestamp(record.timestamp) < since:
        return False
    if statuses is not None and record_status(record) not in statuses:
        return False
    return True


def searchable_text(record: storage.MemoryRecord) -> str:
    metadata = record.metadata or {}
    parts = [record.content]
    for key in ("summary", "details", "source", "status"):
        value = metadata.get(key)
        if isinstance(value, str):
            parts.append(value)
    tags = metadata.get("tags")
    if isinstance(tags, list):
        parts.extend(str(tag) for tag in tags)
    elif isinstance(tags, str):
        parts.append(tags)
    return "\n".join(part for part in parts if part)


def lexical_overlap_score(query_text: str, content: str) -> float:
    query_tokens = set(tokenize(query_text))
    if not query_tokens:
        return 0.0
    content_tokens = set(tokenize(content))
    return len(query_tokens & content_tokens) / len(query_tokens)


def weighted_lexical_score(query_text: str, record: storage.MemoryRecord) -> float:
    metadata = record.metadata or {}
    query_tokens = set(tokenize(query_text))
    if not query_tokens:
        return 0.0

    score = 0.0
    fields: list[tuple[float, str]] = [(0.35, record.content)]
    for weight, key in ((0.9, "summary"), (0.65, "details"), (0.25, "source"), (0.2, "status")):
        value = metadata.get(key)
        if isinstance(value, str):
            fields.append((weight, value))
    tags = metadata.get("tags")
    if isinstance(tags, list):
        fields.append((1.0, " ".join(str(tag) for tag in tags)))
    elif isinstance(tags, str):
        fields.append((1.0, tags))

    for weight, text in fields:
        content_tokens = set(tokenize(text))
        if content_tokens:
            score += weight * (len(query_tokens & content_tokens) / len(query_tokens))
    return score


GATE_STOPWORDS = frozenset(
    "the and for with that this from into onto over under are is was were been being have has had "
    "will would should could must may might can not all any each when where which while there their "
    "them they its our your you use used using also than then such only more most some does did what "
    "how why who whom about after before again against because between during under above below off "
    "out own same too very just now here once more please okay ok run make give want need lets let".split()
)


def gate_tokens(text: str) -> set[str]:
    """Stopword-filtered, naively singularized tokens for gate matching only.

    The plural strip ("reports" -> "report") closes real match gaps between
    prompts and cards; crude, but gate-local so ranking is unaffected.
    """
    tokens = set()
    for token in tokenize(text):
        if token in GATE_STOPWORDS:
            continue
        if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]
        tokens.add(token)
    return tokens


def gate_match_count(query_text: str, record: storage.MemoryRecord) -> int:
    """Count distinct non-stopword query terms found in agent-facing card text."""
    query_tokens = gate_tokens(query_text)
    if not query_tokens:
        return 0
    metadata = record.metadata or {}
    texts = [record.content]
    for key in ("summary", "details"):
        value = metadata.get(key)
        if isinstance(value, str):
            texts.append(value)
    tags = metadata.get("tags")
    if isinstance(tags, list):
        texts.append(" ".join(str(tag) for tag in tags))
    elif isinstance(tags, str):
        texts.append(tags)
    content_tokens: set[str] = set()
    for text in texts:
        content_tokens.update(gate_tokens(text))
    return len(query_tokens & content_tokens)


def normalized_lexical_overlap(query_text: str, record: storage.MemoryRecord) -> float:
    """Stable 0..1 overlap used by automatic-injection gating.

    Stopword-filtered: without this, function words shared with almost every
    card ("the", "into", "five") let generic memories cross the injection
    threshold on unrelated prompts, and dilute genuinely matching prompts.
    Ranking scores are intentionally NOT filtered — this affects the gate only.
    """
    query_tokens = gate_tokens(query_text)
    if not query_tokens:
        return 0.0
    metadata = record.metadata or {}
    score = 0.0
    fields: list[tuple[float, str]] = [(0.35, record.content)]
    for weight, key in ((0.9, "summary"), (0.65, "details")):
        value = metadata.get(key)
        if isinstance(value, str):
            fields.append((weight, value))
    tags = metadata.get("tags")
    if isinstance(tags, list):
        fields.append((1.0, " ".join(str(tag) for tag in tags)))
    for weight, text in fields:
        content_tokens = gate_tokens(text)
        if content_tokens:
            score += weight * (len(query_tokens & content_tokens) / len(query_tokens))
    return min(1.0, score)


def _document_tokens(record: storage.MemoryRecord) -> set[str]:
    metadata = record.metadata or {}
    texts = [record.content]
    for key in ("summary", "details"):
        value = metadata.get(key)
        if isinstance(value, str):
            texts.append(value)
    tags = metadata.get("tags")
    if isinstance(tags, list):
        texts.append(" ".join(str(tag) for tag in tags))
    elif isinstance(tags, str):
        texts.append(tags)
    tokens: set[str] = set()
    for text in texts:
        tokens.update(gate_tokens(text))
    return tokens


def build_term_document_frequencies(records: list[storage.MemoryRecord]) -> tuple[dict[str, int], int]:
    """Corpus-wide document frequency per gate token, for IDF downweighting.

    Store-frequent tokens (repeated filler vocabulary like "script" or
    "release") should count for less in ranking than distinctive terms
    ("zstandard", "websocket") that appear on only one or two cards.
    """
    doc_freq: dict[str, int] = {}
    for record in records:
        for token in _document_tokens(record):
            doc_freq[token] = doc_freq.get(token, 0) + 1
    return doc_freq, len(records)


def idf_weight(token: str, doc_freq: dict[str, int], total_docs: int) -> float:
    frequency = doc_freq.get(token, 0)
    return math.log((total_docs + 1) / (frequency + 1)) + 1.0


def idf_weighted_overlap(
    query_text: str,
    record: storage.MemoryRecord,
    doc_freq: dict[str, int],
    total_docs: int,
) -> float:
    """IDF-downweighted variant of `normalized_lexical_overlap`, ranking only.

    A matched rare token (e.g. "zstandard") now counts for more than a
    matched store-frequent one (e.g. "script"), so a single distinctive
    overlap can outrank a card that only shares generic filler vocabulary.
    The gate's own threshold check keeps using flat overlap unchanged.
    """
    query_tokens = gate_tokens(query_text)
    if not query_tokens:
        return 0.0
    query_weight_total = sum(idf_weight(token, doc_freq, total_docs) for token in query_tokens)
    if query_weight_total <= 0:
        return 0.0
    metadata = record.metadata or {}
    score = 0.0
    fields: list[tuple[float, str]] = [(0.35, record.content)]
    for weight, key in ((0.9, "summary"), (0.65, "details")):
        value = metadata.get(key)
        if isinstance(value, str):
            fields.append((weight, value))
    tags = metadata.get("tags")
    if isinstance(tags, list):
        fields.append((1.0, " ".join(str(tag) for tag in tags)))
    for weight, text in fields:
        content_tokens = gate_tokens(text)
        if not content_tokens:
            continue
        matched = query_tokens & content_tokens
        matched_weight = sum(idf_weight(token, doc_freq, total_docs) for token in matched)
        score += weight * (matched_weight / query_weight_total)
    return min(1.0, score)


def rank_lexical_score(
    query_text: str,
    record: storage.MemoryRecord,
    doc_freq: dict[str, int] | None = None,
    total_docs: int = 0,
) -> float:
    """Filtered lexical score for ranking.

    Raw lexical overlap lets repeated filler words ("the", "for", "with") beat
    distinctive cards in large stores. Reuse gate tokens for rank lexical
    signal while keeping vector/category/status/source weighting unchanged.
    When corpus document frequencies are supplied, store-frequent terms count
    for less than rare ones (`idf_weighted_overlap`); callers without corpus
    stats fall back to the flat gate-token overlap.
    """
    if doc_freq is not None:
        return idf_weighted_overlap(query_text, record, doc_freq, total_docs)
    return normalized_lexical_overlap(query_text, record)


FTS_RERANK_WEIGHT = 0.35


def fts5_rerank_bonus(record_id: int, bm25_scores: dict[int, float]) -> float:
    """Min-max normalized bm25 bonus: 1.0 = strongest fts5 match in this
    candidate set, 0.0 = not matched by fts5 at all (or fts5 unavailable).

    Complements vector cosine + gate-token overlap with SQLite FTS5's
    rarity-aware bm25 ranking, which can surface a distinctive-term match
    (e.g. rare "export") that flat token-overlap counting and a noisy
    low-dimensional hash-embedding cosine can both miss or rank low.
    """
    if not bm25_scores or record_id not in bm25_scores:
        return 0.0
    best = min(bm25_scores.values())
    worst = max(bm25_scores.values())
    if worst == best:
        return 1.0
    return (worst - bm25_scores[record_id]) / (worst - best)


def source_blind_memory_request(query_text: str) -> bool:
    lowered = query_text.casefold()
    return any(marker in lowered for marker in SOURCE_BLIND_MEMORY_RE)


def requested_categories(query_text: str) -> set[str]:
    lowered = query_text.casefold()
    requested: set[str] = set()
    for category, terms in CATEGORY_TERMS.items():
        if any(term in lowered for term in terms):
            requested.add(category)
    return requested


def status_weight(record: storage.MemoryRecord) -> float:
    return STATUS_WEIGHTS.get(record_status(record), DEFAULT_STATUS_WEIGHT)


def source_weight(record: storage.MemoryRecord) -> float:
    source = str((record.metadata or {}).get("source", "")).strip().lower()
    return SOURCE_WEIGHTS.get(source, DEFAULT_SOURCE_WEIGHT)


def score_record(
    record: storage.MemoryRecord,
    query_text: str,
    query_vector: list[float],
    index: dict[int, dict[str, Any]],
    cfg: dict[str, Any],
    doc_freq: dict[str, int] | None = None,
    total_docs: int = 0,
    bm25_scores: dict[int, float] | None = None,
) -> float:
    indexed_embedding = index.get(record.id, {}).get("embedding")
    embedding = indexed_embedding if isinstance(indexed_embedding, list) else record.embedding or embed(record.content)
    score = cosine(query_vector, embedding)
    score += 0.45 * rank_lexical_score(query_text, record, doc_freq, total_docs)
    score += FTS_RERANK_WEIGHT * fts5_rerank_bonus(record.id, bm25_scores or {})
    try:
        score += 0.15 * float(record.metadata.get("importance", 0.0))
    except (TypeError, ValueError):
        pass
    score *= recall_config.category_weight(cfg, record.category)
    score *= status_weight(record)
    score *= source_weight(record)
    age_days = max(0.0, (datetime.now(timezone.utc) - recency_timestamp(record)).total_seconds() / 86400)
    score += 0.03 / (1.0 + age_days)
    return score


SNAPSHOT_CATEGORIES = {"project_state", "integrations", "tooling_quirks", "session_summaries"}
SNAPSHOT_AGING_DAYS = 30.0
FLAG_CURRENT = "current"
FLAG_STALE = "stale"
FLAG_SUPERSEDED = "superseded"
FLAG_DEPRECATED = "deprecated"
FLAG_NEEDS_VERIFICATION = "needs_verification"
FLAG_CONFLICTING = "conflicting"


def health_flag(record: storage.MemoryRecord, aging_days: float = SNAPSHOT_AGING_DAYS) -> tuple[str, str | None]:
    """Classify a record's trustworthiness for retrieval output."""
    status = record_status(record)
    if status == "stale":
        return FLAG_STALE, "source changed since capture; verify against the repository"
    if status == "superseded":
        return FLAG_SUPERSEDED, "replaced by a newer memory; follow superseded_by instead"
    if status in {"deprecated", "archived"}:
        return FLAG_DEPRECATED, "retired memory; do not act on it"
    if status == "hypothesis":
        return FLAG_NEEDS_VERIFICATION, "unconfirmed hypothesis; verify before trusting"
    age_days = max(0.0, (datetime.now(timezone.utc) - recency_timestamp(record)).total_seconds() / 86400)
    if record.category in SNAPSHOT_CATEGORIES and age_days > aging_days:
        return FLAG_NEEDS_VERIFICATION, (
            f"point-in-time snapshot is {int(age_days)} days old; verify it still holds"
        )
    return FLAG_CURRENT, None


def compact_result(item: dict[str, Any]) -> dict[str, Any]:
    """Token-lean result shape for agent-facing surfaces.

    Keeps what an agent needs to act (identity, trust signals, text) and drops
    the metadata blob (fingerprints, session ids, provenance internals), which
    dominates injected token cost. Full metadata stays available via verbose.
    """
    metadata = item.get("metadata") or {}
    compact: dict[str, Any] = {
        "id": item["id"],
        "category": item["category"],
        "timestamp": item["timestamp"],
        "score": item["score"],
        "flag": item.get("flag", FLAG_CURRENT),
        "content": item["content"],
    }
    if item.get("flag_reason"):
        compact["flag_reason"] = item["flag_reason"]
    for key in ("status", "summary", "source"):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            compact[key] = value
    return compact


def mark_conflicts(results: list[dict[str, Any]]) -> None:
    """Mark results whose claim_key collides with a different claim_value."""
    claims: dict[tuple[str, str], set[str]] = {}
    for item in results:
        metadata = item.get("metadata") or {}
        claim_key = metadata.get("claim_key")
        claim_value = metadata.get("claim_value")
        if not claim_key or claim_value is None:
            continue
        claims.setdefault((item["category"], str(claim_key)), set()).add(str(claim_value))
    for item in results:
        metadata = item.get("metadata") or {}
        claim_key = metadata.get("claim_key")
        if not claim_key:
            continue
        values = claims.get((item["category"], str(claim_key)), set())
        if len(values) > 1:
            item["flag"] = FLAG_CONFLICTING
            item["flag_reason"] = (
                f"multiple memories disagree on claim `{claim_key}`; reconcile before trusting"
            )


def health_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for item in results:
        flag = item.get("flag", FLAG_CURRENT)
        counts[flag] = counts.get(flag, 0) + 1
    next_action = None
    if counts.get(FLAG_CONFLICTING):
        next_action = "conflicting memories returned; run memory-hygiene reconcile-current-truth before relying on them"
    elif counts.get(FLAG_STALE) or counts.get(FLAG_NEEDS_VERIFICATION):
        next_action = "some results need verification; check them against the repository before acting"
    elif counts.get(FLAG_SUPERSEDED) or counts.get(FLAG_DEPRECATED):
        next_action = "retired memories matched; prefer their replacements or current repository state"
    summary: dict[str, Any] = {"flag_counts": counts}
    if next_action:
        summary["next_action"] = next_action
    return summary


def query(
    query_text: str,
    categories: list[str] | None = None,
    exclude_categories: list[str] | None = None,
    limit: int = 8,
    root: str | Path | None = None,
    summarize: bool = False,
    statuses: list[str] | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    cfg = recall_config.load_config(root)
    aging_days = float(cfg.get("staleness", {}).get("retrieval_aging_days", SNAPSHOT_AGING_DAYS))
    include_set = {recall_config.normalize_category(value) for value in categories} if categories else None
    exclude_set = (
        {recall_config.normalize_category(value) for value in exclude_categories}
        if exclude_categories
        else None
    )
    status_set = {value.strip().lower() for value in statuses} if statuses else set(DEFAULT_QUERY_STATUSES)
    since = None
    if cfg.get("recency_days") is not None:
        since = datetime.now(timezone.utc) - timedelta(days=int(cfg["recency_days"]))

    records = list(storage.iter_records(root))
    index = index_store.ensure_complete_for_records(records, root)
    query_vector = embed(query_text)
    doc_freq, total_docs = build_term_document_frequencies(records)
    record_texts = {record.id: searchable_text(record) for record in records}
    bm25_scores = storage.fts5_rerank_scores(record_texts, gate_tokens(query_text))
    ranked: list[storage.MemoryRecord] = []
    for record in records:
        if not passes_filters(record, include_set, exclude_set, since, status_set):
            continue
        record.score = score_record(record, query_text, query_vector, index, cfg, doc_freq, total_docs, bm25_scores)
        ranked.append(record)

    ranked.sort(key=lambda item: (item.score, parse_timestamp(item.timestamp), item.id), reverse=True)
    results = []
    for record in ranked[:limit]:
        flag, flag_reason = health_flag(record, aging_days)
        # Defense in depth: writes redact, but legacy/imported stores can hold
        # raw secret-shaped content — never emit it through retrieval.
        item: dict[str, Any] = {
            "id": record.id,
            "category": record.category,
            "timestamp": record.timestamp,
            "score": round(record.score, 4),
            "content": security.redact_text(record.content),
            "metadata": security.redact_value(record.metadata),
            "flag": flag,
        }
        if flag_reason:
            item["flag_reason"] = flag_reason
        results.append(item)
    mark_conflicts(results)
    health = health_summary(results)
    summary_text = summarize_records(results, cfg["token_budget"]) if summarize else None
    if not verbose:
        results = [compact_result(item) for item in results]
    response: dict[str, Any] = {"query": query_text, "results": results, "health": health}
    if summary_text is not None:
        response["summary"] = summary_text
    return response


def assess_relevance(
    query_text: str,
    *,
    root: str | Path | None,
    categories: list[str] | None = None,
    exclude_categories: list[str] | None = None,
    statuses: list[str] | None = None,
) -> dict[str, Any]:
    response = query(
        query_text,
        categories=categories,
        exclude_categories=exclude_categories,
        limit=3,
        root=root,
        statuses=statuses,
    )
    results = response.get("results", [])
    top = results[0] if results else None
    lexical = 0.0
    match_count = 0
    if top is not None:
        record = storage.get_record(int(top["id"]), root)
        if record is not None:
            lexical = normalized_lexical_overlap(query_text, record)
            match_count = gate_match_count(query_text, record)
    cfg = recall_config.load_config_if_present(root)
    thresholds = cfg.get("relevance", {})
    minimum_score = float(thresholds.get("minimum_score", 0.75))
    minimum_lexical = float(thresholds.get("minimum_lexical_overlap", 0.15))
    raw_score = float(top.get("score", 0.0)) if top else 0.0
    relevance_score = max(raw_score, lexical + 0.25) if top else 0.0
    category_match = False
    if top is not None and top.get("category") in CURRENT_DURABLE_CATEGORIES:
        status = str(((top.get("metadata") or {}).get("status") or "")).strip().lower()
        requested = requested_categories(query_text)
        category_match = source_blind_memory_request(query_text) and top.get("category") in requested and status in CURRENT_STATUSES
        if category_match:
            relevance_score = max(relevance_score, 0.8)
        if status in CURRENT_STATUSES and lexical >= minimum_lexical:
            relevance_score = max(relevance_score, lexical + 0.45)
    relevant = bool(top and relevance_score >= minimum_score and (lexical >= minimum_lexical or category_match))
    return {
        "relevant": relevant,
        "sufficient": relevant and len(results) > 0,
        "top_score": round(relevance_score, 4),
        "raw_rank_score": round(raw_score, 4),
        "lexical_overlap": round(lexical, 4),
        "gate_match_count": match_count,
        "category_match": category_match,
        "result_ids": [int(item["id"]) for item in results],
        "thresholds": {"minimum_score": minimum_score, "minimum_lexical_overlap": minimum_lexical},
    }
