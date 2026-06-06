# Changelog

## 0.1.0

- Added validation-ready Codex plugin manifest.
- Added RECALL memory categories and project-local configuration.
- Added SQLite and JSONL storage support.
- Added dedicated storage, index, and retrieval backend modules.
- Added deterministic local retrieval scoring, lexical boosts, and heuristic summarization.
- Added rebuildable `vector_index.bin` support with `rebuild-index` and `doctor` commands.
- Added `save_insight`, `retrieve_memory`, and `define_category` skills.
- Added lifecycle hook script stubs for session start, compaction, tool use, prompt inspection, stop, and category reload.
- Added unit tests and packaging scripts.
