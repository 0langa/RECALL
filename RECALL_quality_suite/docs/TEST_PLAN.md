# RECALL Test Plan

## Goal

Prove that RECALL is safe and reliable enough to act as a persistent project-memory operating layer for Codex agents during active development and before production release.

This suite must also govern the path from alpha-stage to final product, not merely confirm today's implementation.

## Surfaces under test

1. Plugin metadata and marketplace shape.
2. `.recall/` project-local runtime storage, plus legacy `.codex_memory/` fallback and migration behavior.
3. SQLite and JSONL storage behavior.
4. Deterministic local embedding/index behavior.
5. Weighted retrieval and structured memory-card ranking.
6. Public skill adapter: `scripts/recall_skill.py`.
7. Internal maintenance CLI: `scripts/memory_manager.py`.
8. Lifecycle hooks:
   - `SessionStart`
   - `UserPromptSubmit`
   - `PostToolUse`
   - `PreCompact`
   - `Stop`
9. Smoke harness and installed-plugin compatibility.
10. Package hygiene and release artifact safety.
11. Source-blind memory usefulness.

## Mandatory gates

A Release Candidate or stronger claim must pass:

- Existing unit tests.
- Added static-contract tests.
- Added skill CLI contract tests.
- Added hook lifecycle contract tests.
- Added source-blind retrieval-readiness tests.
- Smoke harness.
- Performance benchmark under configured thresholds. Quick runs use the quick benchmark profile; release evidence uses the full profile.
- Package hygiene check for the built release ZIP.
- Human source-blind agent evaluation using the hidden ground-truth rubric.

See `docs/RELEASE_ROADMAP_GATES.md` for stage-by-stage expectations and `rubrics/production_release_criteria.md` for promotion blockers.

## Non-goals

This suite does not prove that Codex itself will always run hooks in every future app version. That must remain a live install verification step because plugin hook trust and Codex payloads can change externally.
