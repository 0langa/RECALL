# RECALL Development Workflow

This document defines how RECALL work must proceed while the product is still alpha-stage.

## Change classification

Classify every change before editing code. Pick the highest-risk class that applies.

Agents must classify work explicitly before code changes begin.

| Change class | Examples | Minimum test layers to touch |
|---|---|---|
| Docs-only | Clarify README, runbook, rubrics, release notes | Docs contract tests if suite discoverability changes |
| Pure refactor | Rename helpers, extract functions, no behavior change | Existing affected unit/integration tests; add regression test if risk is non-trivial |
| Behavior change | Retrieval ranking, lifecycle commands, redaction, hook summaries | Unit or integration test for changed behavior, plus smoke if public workflow changes |
| Storage/schema | SQLite/JSONL metadata, rebuild, doctor, repair, migration behavior | Unit/integration tests, smoke, performance benchmark, corruption/recovery coverage |
| Hook behavior | SessionStart, UserPromptSubmit, PostToolUse, PreCompact, Stop | Hook lifecycle contract tests, targeted regression tests, smoke when installed behavior could drift |
| Public surface | `recall_skill.py`, skill names, manifest, install/build/package flow | CLI contract tests, static contract tests, smoke, package hygiene, install-lifecycle docs |
| Memory-quality evolution | Retrieval heuristics, stale handling, contradiction handling, review UX | Source-blind retrieval tests, fixture updates, human-eval prep updates, performance if query/write cost changes |
| Release process | Gates, rubrics, release docs, packaging standards | Static docs/discoverability tests, release checklist, package hygiene expectations |

When a change spans classes, satisfy all listed layers.

## Required workflow

1. Read first:
   `README.md`, `RUNBOOK.md`, `docs/TEST_PLAN.md`, this file, `docs/TDD_PROCESS.md`, `docs/RELEASE_ROADMAP_GATES.md`, `rubrics/production_release_criteria.md`, `rubrics/source_blind_quality_gate.md`, `plugins/recall/README.md`, and `plugins/recall/docs/RELEASE_CHECKLIST.md`.
2. State current stage truth in your notes. Until the stage gates prove otherwise, RECALL remains alpha-stage.
3. Classify the change.
4. Write or update the failing test first when the change affects behavior or suite discoverability.
5. Make the smallest behavior-preserving implementation that satisfies the failing test set, but do not prefer shallow fixes over higher-value corrections when root-cause improvement is obvious and safe.
6. Refactor only after green.
7. Run the validation commands required by the change class.
8. Update docs, fixtures, and blockers before final reporting.

## Validation command matrix

Run from repo root unless noted otherwise.

| Change class | Required validation |
|---|---|
| Docs-only in suite | `python RECALL_quality_suite/scripts/run_recall_quality_suite.py --repo-root . --quick` |
| Plugin code touched | `cd plugins/recall`, `python -m unittest discover -s tests`, `python ./scripts/smoke_recall.py --json`, then repo-root quick suite |
| Hook/storage/retrieval touched | Full plugin tests, smoke, repo-root quick suite, and performance benchmark if cost profile may change |
| Packaging/install touched | Plugin tests, smoke, build, package inspection/hygiene, repo-root full suite when feasible |
| Release-prep touched | Full suite, full plugin validation, build/package checks, release checklist review |

Minimum suite command:

```bash
python RECALL_quality_suite/scripts/run_recall_quality_suite.py --repo-root . --quick
```

Escalate to full suite when performance, package, or release evidence changed:

```bash
python RECALL_quality_suite/scripts/run_recall_quality_suite.py --repo-root .
```

## When docs must be updated

Update docs in the same change whenever you alter:

- User-visible behavior.
- Public CLI or skill names.
- Hook behavior or hook trust expectations.
- Storage shape, lifecycle metadata, or repair/doctor semantics.
- Validation commands.
- Release criteria, roadmap stage meaning, or source-blind scoring.

At minimum, update whichever of these are affected:

- `plugins/recall/README.md`
- `plugins/recall/docs/RELEASE_CHECKLIST.md`
- `RECALL_quality_suite/README.md`
- `RECALL_quality_suite/RUNBOOK.md`
- `RECALL_quality_suite/docs/TEST_PLAN.md`
- `RECALL_quality_suite/docs/EXTENDING.md`
- Roadmap/rubric docs in this suite

## When source-blind fixtures must be updated

Update `fixtures/source_blind_memory_cards.json` and related tests when the change affects:

- What a fresh source-blind agent should know.
- Which memories should rank as current versus stale or superseded.
- Important architecture, decision, risk, or implementation-plan context.
- Honesty boundaries about what memory cannot know without source access.

Do not add fake code-level certainty to fixtures. Favor project-history-backed facts over polished synthetic summaries whenever maintainers can verify them.

## How release blockers are recorded

Any gap that prevents stage promotion must be recorded in two places:

1. Add or update an item under `Open release blockers` in `rubrics/production_release_criteria.md`.
2. Mention the blocker and its evidence in the final status report for the task.

A blocker entry must include:

- What is failing.
- Which stage it blocks.
- What evidence showed the problem.
- What kind of follow-up is needed.

Every release blocker entry should use that structure.

Do not remove a blocker just because a local branch passes current tests. Remove it only when the blocker condition is actually resolved.

## Memory discipline during RECALL development

RECALL must be developed without teaching itself lies.

This section is the memory discipline rule set for RECALL development.

- Use the public adapter and real hook flows when validating user-facing memory behavior.
- Treat stored memory as evidence to inspect, not as unquestioned truth.
- Mark stale or superseded memories instead of silently overwriting history.
- Preserve missing-information honesty. If memory cannot justify a claim, docs and fixtures must say that plainly.
- Keep source of truth in storage and verified repo state; vector index remains rebuildable.
- Never describe alpha behavior as final just because it passed one run.
