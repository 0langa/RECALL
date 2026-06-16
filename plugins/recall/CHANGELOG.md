# Changelog

## Unreleased

- Added persistent project-scoped activation with Git/manifest root resolution, explicit greenfield initialization, activation status, and non-destructive deactivation.
- Changed `PostToolUse` and `Stop` from direct durable writes to redacted turn evidence plus one atomic, idempotent semantic finalizer batch.
- Added relevance and sufficiency gating, command-category suppression for non-tooling prompts, quiet conflict alerts, and seven-day debug traces.
- Added batch ingest with one SQLite transaction and one index rebuild; 500-record seed time is now below one second on the release workstation.
- Added non-destructive corpus migration with pre-apply backup, evidence lineage, command synthesis, and historical score/checkpoint consolidation.
- Migrated the repository corpus from 18 active automatic noise records to zero while preserving all source IDs and history.

- Added automatic schema-v2 migration with a one-time v1 SQLite backup, WAL mode, foreign keys, bounded lock waits, normalized lifecycle/provenance columns, indexes, and optional FTS5.
- Extended `doctor` with SQLite concurrency, FTS, and migration-backup diagnostics.
- Added file provenance hashes, project-scope path checks, source refresh/invalidation, and repository reconciliation for modified, deleted, or moved sources.
- Added hypothesis/validated/deprecated lifecycle states, trust promotion, explicit claim-slot conflict clusters, conflict resolution, and validated-truth protection.
- Added durable preference evidence policy, hook-delivery idempotency keys, and explainable token-budgeted context packets with diversity and omission reporting.
- Redacted secret-like values recursively in persisted metadata and added deterministic replay keys for identified hook deliveries.
- Added portable export/import and timestamped backup/restore workflows that preserve memory IDs, lifecycle, provenance, and relationships.
- Separated `manual`, `relevant`, and `always` recall activation from automatic capture mode.
- Added three-platform CI, clean installed-cache verification, and an evidence report that records unresolved human and evaluator certification gates.
- Removed the unsupported `UpdateCategories` hook wrapper and documented category normalization as an explicit support command.
- Added regression coverage to keep category maintenance out of the hook surface.
- Added golden retrieval quality fixtures with status-aware and field-aware ranking.
- Added automatic hook memory hygiene for duplicate suppression and near-duplicate linking.
- Changed `SessionStart` to a quiet compatibility hook; explicit `@recall` prompt retrieval now injects curated grouped context.
- Exposed safe `doctor`, `repair`, and `list-categories` actions through `recall_skill.py`.
- Added lifecycle operations for confirming, resolving, marking stale, superseding, merging, and non-destructively pruning memories.
- Added hook write policy classification for ignored, refreshed, new, related, and superseding automatic memories.
- Added CLI-first memory review summaries through `recall_skill.py review-memory`.
- Added discoverable memory-control skills for finalizer cards, review, confirm, resolve, stale, supersede, merge, prune, doctor, and repair workflows.
- Added explicit `edit-memory` and confirmation-gated `delete-memory` public adapter commands and skills.
- Changed automatic hooks to stay idle unless the current user prompt explicitly invokes RECALL with `@recall`, `plugin://recall`, or `$recall:`.
- Added `archive-noise` dry-run/apply cleanup for old low-value automatic hook command memories.
- Compacted Stop finalizer continuation prompts with inline `PACKET=` JSON instead of requiring a packet-file read first.

## 0.1.0 - 2026-06-06

- Added validation-ready Codex plugin manifest.
- Moved the installable plugin to the official repo marketplace layout at `plugins/recall`.
- Added repo-root marketplace and build wrappers.
- Added RECALL memory categories and project-local configuration.
- Added SQLite and JSONL storage support.
- Added dedicated storage, index, and retrieval backend modules.
- Added structured memory cards with summary, details, tags, source, status, importance, and confidence metadata.
- Added deterministic local retrieval scoring, lexical boosts, status filters, and heuristic summarization.
- Added rebuildable `vector_index.bin` support with `rebuild-index`, `doctor`, and `repair` commands.
- Added malformed JSONL row tolerance and index integrity diagnostics.
- Added `save-insight`, `retrieve-memory`, and `define-category` skills.
- Added a narrow `recall_skill.py` adapter so bundled skills use a public plugin action surface instead of the backend maintenance CLI.
- Added lifecycle hooks for session start, compaction, tool use, prompt inspection, and stop.
- Added compact hook payload parsing for Codex-shaped events.
- Added source and installed-cache smoke harnesses.
- Added built-zip marketplace smoke testing through a temporary Codex marketplace.
- Added public manifest metadata, local icon/logo assets, privacy terms, and release checklist.
- Added package inspection and build gates for tests, plugin validation, smoke, zip creation, and artifact inspection.
