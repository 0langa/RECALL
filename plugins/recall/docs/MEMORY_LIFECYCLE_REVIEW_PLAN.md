# RECALL Memory Lifecycle, Write Policy, And Review UX Implementation Plan

> **For agentic workers:** Execute task-by-task. Keep RECALL stdlib-only and local-first. Keep public user workflow on bundled skills/hooks plus `scripts/recall_skill.py`; keep `memory_manager.py` as backend/support plumbing.

**Goal:** Add first-class lifecycle relationships, smarter hook write policy, and a CLI-first memory review/prune UX so RECALL can manage memory quality over time instead of accumulating passive notes.

**Architecture:** Storage remains the source of truth and keeps the existing schema. Lifecycle state is stored in record metadata so SQLite and JSONL stay compatible without migration. Hooks classify automatic writes before storing; explicit user saves remain append-only unless the user invokes review/lifecycle actions.

**Tech Stack:** Python stdlib, SQLite/JSONL, existing RECALL hooks, existing `recall_skill.py` adapter, existing plugin package/validator gates.

---

## Task 1: Storage Update Primitives

**Files:**
- Modify: `scripts/storage.py`
- Modify: `scripts/memory_manager.py`
- Test: `tests/test_memory_lifecycle.py`

- Add `storage.get_record(record_id, root)` and `storage.update_record_metadata(record_id, metadata, root)` for both SQLite and JSONL.
- JSONL update rewrites the affected category file only and preserves malformed-row tolerance by skipping malformed rows during rewrite.
- Add backend-level wrappers in `memory_manager.py`.
- Verify update works for SQLite and JSONL without changing ids, content, category, or timestamps.

## Task 2: Lifecycle Relationships

**Files:**
- Create: `scripts/memory_lifecycle.py`
- Modify: `scripts/memory_manager.py`
- Modify: `scripts/retrieval.py`
- Test: `tests/test_memory_lifecycle.py`

- Add metadata fields: `related_to`, `supersedes`, `superseded_by`, `source_session`, `last_confirmed`, `resolved_at`, `superseded_at`, `stale_at`, `archived_at`, `merged_from`, `lifecycle_note`.
- Add operations: confirm, resolve, mark-stale, supersede, merge, prune.
- Extend valid statuses with `stale`; retrieval scores `stale` lower than active/open but above superseded/archived.
- Use `last_confirmed` as the recency anchor when available so old confirmed memories can still rank, while old unconfirmed memories decay.
- Verify a fresh correction supersedes an older decision and broad queries prefer the correction.

## Task 3: Better Hook Write Policy

**Files:**
- Create: `scripts/write_policy.py`
- Modify: `scripts/memory_hygiene.py`
- Modify: `scripts/memory_manager.py`
- Modify: `hooks/scripts/post_tool_use.py`
- Modify: `hooks/scripts/pre_compact.py`
- Modify: `hooks/scripts/stop.py`
- Test: `tests/test_write_policy.py`
- Test: `tests/test_hooks.py`

- Classify automatic writes as `ignore`, `update_existing`, `save_new`, or `mark_stale`.
- Ignore low-signal successful read/listing commands and empty/generic checkpoints.
- Exact duplicates update existing `last_confirmed`, `confirmed_count`, and `source_session` instead of writing a new record.
- Near duplicates save a linked record with `related_to` and `related_similarity`.
- Explicit conflict cues in hook content, such as `supersedes memory #N` or `correction to memory #N`, save the new memory and mark the old memory superseded.
- Preserve secret redaction and existing hook output shapes.

## Task 4: CLI-First Review UX

**Files:**
- Create: `scripts/memory_review.py`
- Modify: `scripts/recall_skill.py`
- Modify: `skills/retrieve-memory/SKILL.md`
- Modify: `skills/save-insight/SKILL.md`
- Modify: `skills/define-category/SKILL.md`
- Modify: `README.md`
- Modify: `docs/INSTALL.md`
- Test: `tests/test_memory_review.py`
- Test: `tests/test_recall_skill.py`

- Add `recall_skill.py review-memory` with filters for status, category, source, and limit. Output JSON with totals, status counts, category counts, and concise memory cards including relationship metadata.
- Add `confirm-memory`, `resolve-memory`, `stale-memory`, `supersede-memory`, `merge-memories`, and `prune-memory`.
- `prune-memory` is non-destructive: it marks status `archived` and records `archived_at`.
- Keep all commands JSON-first and safe for installed-plugin usage.
- Update docs to explain review/prune and lifecycle operations without advertising broad backend CLI usage.

## Task 5: Smoke, Package, And Evaluation

**Files:**
- Modify: `scripts/smoke_recall.py`
- Modify: `tests/test_package_metadata.py`
- Modify: `CHANGELOG.md`
- Optionally create plugin-eval output under docs only if the command supports a non-mutating markdown report.

- Smoke should exercise review-memory and at least one lifecycle action through `recall_skill.py`.
- Package metadata tests ensure skills remain local-only and use `recall_skill.py`.
- Run `plugin-eval` analysis if available without introducing required runtime dependencies.
- Run full validation: unit tests, plugin validator, source smoke, root build, package inspection, built-zip marketplace smoke.
