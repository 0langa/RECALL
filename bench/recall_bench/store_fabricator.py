"""Deterministic store fabrication for benchmark tiers.

Builds .recall stores at defined sizes with realistic category mixes, plus
optional golden retrieval targets and planted-bad hygiene packs. Fabrication
imports the engine directly (it is setup, not measurement) and is fully
seeded: same seed -> byte-identical store content (timestamps derive from a
fixed epoch, never wall clock).
"""

from __future__ import annotations

import random
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "plugins" / "recall" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import config as recall_config  # noqa: E402
from embedder import embed  # noqa: E402
import index_store  # noqa: E402
import storage  # noqa: E402


# Card timestamps are now-relative with deterministic per-index offsets kept
# under the 30-day retrieval-aging window (max 500 cards * 60min ≈ 21 days),
# so fabricated CURRENT cards never trip snapshot-age checks. Ageing fixtures
# set their age explicitly. Wall-clock components are normalized out of the
# determinism hash by the recorder.

TIER_SIZES = {"fresh": 0, "working": 50, "mature": 500}

CATEGORY_MIX = [
    ("decisions", 0.14),
    ("architecture", 0.10),
    ("requirements", 0.08),
    ("constraints", 0.07),
    ("commands", 0.16),
    ("debug_history", 0.16),
    ("project_state", 0.08),
    ("preferences", 0.05),
    ("tasks", 0.06),
    ("lessons_learned", 0.05),
    ("tooling_quirks", 0.03),
    ("integrations", 0.02),
]

TOPICS = [
    "auth middleware", "payment webhook", "sqlite migration", "docker build",
    "ci pipeline", "retry logic", "cache invalidation", "logging format",
    "api pagination", "feature flags", "config loader", "test fixtures",
    "release script", "index rebuild", "session handling", "rate limiter",
]

TEMPLATES = {
    "decisions": "Chose {a} over {b} for the {topic} because {a} keeps behavior deterministic under load.",
    "architecture": "The {topic} module owns its own state and exposes one entry point; callers never touch its internals.",
    "requirements": "The {topic} must keep backward compatibility for existing consumers until the next major release.",
    "constraints": "Never bypass validation in the {topic}; all inputs go through the shared checker first.",
    "commands": "Verified command for the {topic}: python -m pytest tests/test_{slug}.py -q (about {n} seconds).",
    "debug_history": "The {topic} failed with a timeout when {b} was misconfigured; fix was raising the pool size and pinning {a}.",
    "project_state": "The {topic} refactor is merged on main; remaining cleanup tracked for the next milestone.",
    "preferences": "Project prefers {a} style naming in the {topic} and rejects abbreviations in public names.",
    "tasks": "Open task: extend the {topic} with metrics before the next release window.",
    "lessons_learned": "Editing generated files in the {topic} causes drift; always change the generator and re-run it.",
    "tooling_quirks": "The {topic} CLI silently ignores unknown flags; always check the exit summary line.",
    "integrations": "The external service behind the {topic} rate-limits at {n} requests per minute on the shared plan.",
}

WORD_A = ["sqlite", "pathlib", "asyncio", "argparse", "hashing", "polling", "batching", "streaming"]
WORD_B = ["jsonl", "os.path", "threads", "click", "encryption", "webhooks", "single writes", "buffering"]

# Golden cards: retrieval ground truth. Each golden query must rank its card
# in the top-k. Content is distinctive on purpose.
GOLDEN_CARDS = [
    {"category": "decisions", "content": "Golden decision: the export pipeline uses zstandard compression level 7 as the accepted default.", "query": "export pipeline compression default", "tags": ["golden", "export"]},
    {"category": "commands", "content": "Golden command: run the nightly consolidation with python scripts/consolidate.py --window 24h --verify.", "query": "nightly consolidation command", "tags": ["golden", "consolidation"]},
    {"category": "debug_history", "content": "Golden fix: the flaky websocket reconnect was caused by a missing jitter on retry; adding 0-300ms jitter resolved it.", "query": "websocket reconnect flaky fix", "tags": ["golden", "websocket"]},
    {"category": "constraints", "content": "Golden constraint: the ledger table is append-only; updates must create correction rows, never mutate history.", "query": "ledger append only constraint", "tags": ["golden", "ledger"]},
    {"category": "architecture", "content": "Golden architecture: the ingest gateway fans out to three workers over a local queue; workers are stateless.", "query": "ingest gateway worker fanout", "tags": ["golden", "ingest"]},
    {"category": "requirements", "content": "Golden requirement: exported reports must include the generation timestamp in UTC in the footer.", "query": "report footer timestamp requirement", "tags": ["golden", "reports"]},
    {
        "category": "preferences",
        "content": "Golden preference: the user wants migration scripts reviewed in dry-run output form before apply.",
        "query": "migration dry run review preference",
        "tags": ["golden", "migrations"],
        # Preferences require durable evidence by contract; a bare preference
        # card would be a planted hygiene finding, not a golden card.
        "metadata": {"preference_key": "migration.review_style", "preference_evidence_type": "explicit_declaration"},
    },
    {"category": "tooling_quirks", "content": "Golden quirk: the deploy CLI requires --region before the subcommand or it exits zero without deploying.", "query": "deploy cli region flag order quirk", "tags": ["golden", "deploy"]},
    {"category": "integrations", "content": "Golden integration: the billing provider sandbox resets every Monday 03:00 UTC; test data does not survive.", "query": "billing sandbox weekly reset", "tags": ["golden", "billing"]},
    {"category": "lessons_learned", "content": "Golden lesson: bulk deletes without a row cap once locked the store; always chunk destructive operations.", "query": "bulk delete lock lesson", "tags": ["golden", "deletes"]},
]

# Lifecycle-state cards used to verify flag correctness in retrieval output.
FLAGGED_CARDS = [
    {"category": "decisions", "content": "Flagged stale: the report engine renders through the legacy template path.", "status": "stale", "query": "report engine template path"},
    {"category": "decisions", "content": "Flagged superseded: exports run synchronously in the request handler.", "status": "superseded", "query": "exports synchronous request handler"},
    {"category": "commands", "content": "Flagged deprecated: build with make all from the repository root.", "status": "deprecated", "query": "build make all root"},
    {"category": "architecture", "content": "Flagged hypothesis: the scheduler may move to cron-style expressions next quarter.", "status": "hypothesis", "query": "scheduler cron expressions"},
]

CONFLICT_CARDS = [
    {"category": "project_state", "content": "Current default branch policy is trunk.", "claim_key": "branch.policy", "claim_value": "trunk"},
    {"category": "project_state", "content": "Current default branch policy is gitflow.", "claim_key": "branch.policy", "claim_value": "gitflow"},
]

SECRET_MARKER = "sk-proj-BENCHMARKPLANTEDSECRETXYZ1234"

BAD_PACK = [
    {"kind": "secret", "category": "commands", "content": f"Deploy uses api_key = {SECRET_MARKER} against staging."},
    {"kind": "raw_log", "category": "debug_history", "content": "Traceback (most recent call last)\n" + "\n".join(f"line {i}: assertion failed in module_{i}" for i in range(60))},
    {"kind": "vague", "category": "lessons_learned", "content": "fixed the bug"},
    {"kind": "aged_snapshot", "category": "project_state", "content": "Release 0.4 in progress; two tests failing on macOS runners.", "age_days": 120},
    {"kind": "exact_duplicate", "category": "requirements", "content": "Duplicated requirement: exports must be reproducible byte for byte.", "count": 2},
    {"kind": "metadata_gap", "category": "decisions", "content": "Use WAL mode for every sqlite connection in the ingest path.", "bare": True},
]


def _timestamp(index: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=index * 60)).isoformat(timespec="seconds")


def _seed_card(root: Path, index: int, category: str, content: str, metadata: dict[str, Any], *, bare: bool = False) -> int:
    base = {} if bare else {"source": "skill", "status": "active", **metadata}
    record = storage.add_record(category, _timestamp(index), content, base, embed(content), root)
    return record.id


def fabricate(
    root: Path,
    *,
    tier: str,
    seed: int,
    golden: bool = True,
    flagged: bool = True,
    conflicts: bool = False,
    bad_pack: bool = False,
) -> dict[str, Any]:
    if tier not in TIER_SIZES:
        raise ValueError(f"Unknown store tier: {tier}")
    rng = random.Random(seed)
    recall_config.activate_project(root, activated_by="bench_fabricator")
    manifest: dict[str, Any] = {"tier": tier, "seed": seed, "golden": [], "flagged": [], "conflicts": [], "bad": []}
    index = 0

    filler_count = TIER_SIZES[tier]
    categories = [name for name, _ in CATEGORY_MIX]
    weights = [weight for _, weight in CATEGORY_MIX]
    for _ in range(filler_count):
        category = rng.choices(categories, weights=weights, k=1)[0]
        topic = rng.choice(TOPICS)
        content = TEMPLATES[category].format(
            topic=topic,
            slug=topic.replace(" ", "_"),
            a=rng.choice(WORD_A),
            b=rng.choice(WORD_B),
            n=rng.randint(2, 90),
        )
        _seed_card(root, index, category, content, {"summary": content[:120], "tags": ["bench-filler"]})
        index += 1

    if golden:
        for card in GOLDEN_CARDS:
            metadata = {"summary": card["content"][:120], "tags": card["tags"], **card.get("metadata", {})}
            record_id = _seed_card(root, index, card["category"], card["content"], metadata)
            manifest["golden"].append({"id": record_id, "query": card["query"], "category": card["category"]})
            index += 1

    if flagged:
        for card in FLAGGED_CARDS:
            record_id = _seed_card(root, index, card["category"], card["content"], {"status": card["status"]})
            manifest["flagged"].append({"id": record_id, "query": card["query"], "status": card["status"]})
            index += 1

    if conflicts:
        for card in CONFLICT_CARDS:
            record_id = _seed_card(
                root, index, card["category"], card["content"],
                {"claim_key": card["claim_key"], "claim_value": card["claim_value"]},
            )
            manifest["conflicts"].append({"id": record_id, "claim_key": card["claim_key"]})
            index += 1

    if bad_pack:
        for card in BAD_PACK:
            count = card.get("count", 1)
            for _ in range(count):
                age_days = card.get("age_days")
                stamp_index = index
                record_id = _seed_card(
                    root, stamp_index, card["category"],
                    card["content"] if card["kind"] != "secret" else "placeholder pending raw insert",
                    {}, bare=card.get("bare", False),
                )
                if age_days:
                    _age_record(root, record_id, age_days)
                if card["kind"] == "secret":
                    _raw_overwrite(root, record_id, card["content"])
                manifest["bad"].append({"id": record_id, "kind": card["kind"]})
                index += 1

    index_store.rebuild(root)
    return manifest


def _age_record(root: Path, record_id: int, days: float) -> None:
    aged = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    connection = sqlite3.connect(storage.db_path(root))
    try:
        connection.execute("UPDATE memories SET timestamp = ? WHERE id = ?", (aged, record_id))
        connection.commit()
    finally:
        connection.close()


def _raw_overwrite(root: Path, record_id: int, content: str) -> None:
    """Simulate a legacy store that already contains raw secrets: the normal
    write path always redacts, so plant via direct SQL like the unit fixtures."""
    connection = sqlite3.connect(storage.db_path(root))
    try:
        connection.execute("UPDATE memories SET content = ? WHERE id = ?", (content, record_id))
        connection.commit()
    finally:
        connection.close()
