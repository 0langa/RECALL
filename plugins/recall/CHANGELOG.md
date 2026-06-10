# Changelog

## Unreleased

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
