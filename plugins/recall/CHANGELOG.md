# Changelog

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
- Added `save_insight`, `retrieve_memory`, and `define_category` skills.
- Added a narrow `recall_skill.py` adapter so bundled skills use a public plugin action surface instead of the backend maintenance CLI.
- Added lifecycle hooks for session start, compaction, tool use, prompt inspection, and stop.
- Added compact hook payload parsing for Codex-shaped events.
- Added source and installed-cache smoke harnesses.
- Added built-zip marketplace smoke testing through a temporary Codex marketplace.
- Added public manifest metadata, local icon/logo assets, privacy terms, and release checklist.
- Added package inspection and build gates for tests, plugin validation, smoke, zip creation, and artifact inspection.
