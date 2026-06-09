# AGENTS.md

Guidance for agents working in this repository.

## Repository Shape

This repository is a Codex plugin marketplace wrapper. The installable plugin lives in:

```text
plugins/recall/
```

The repo-root marketplace file is:

```text
.agents/plugins/marketplace.json
```

Do not treat the repository root as the plugin root for code changes unless you are editing wrapper scripts, marketplace metadata, or repository-level docs.

## Current Product Direction

RECALL is a local-first Codex plugin for project memory. It stores project-local data under:

```text
.codex_memory/
```

Core architecture decisions:

- Keep V1 stdlib-only and local-first.
- Do not add cloud services, local LLM runtimes, sentence-transformers, FAISS, or Chroma unless a later plan explicitly changes that.
- Storage is the source of truth; the vector index is rebuildable.
- Public workflow surface is skills/hooks plus `scripts/recall_skill.py`.
- `scripts/memory_manager.py` is internal backend and support plumbing.
- Runtime memory data must never be packaged into release artifacts.
- Hook output must use Codex `hookSpecificOutput.additionalContext` when injecting context.
- Secrets must be redacted before storage.

## Before Starting Work

Run from the repo root:

```powershell
git status --short --branch
```

Read these files before assuming what is missing:

```text
plugins/recall/docs/RECALL_V1_COMPLETION_PLAN.md
plugins/recall/docs/E2E_VERIFICATION_LOG.md
plugins/recall/docs/RELEASE_CHECKLIST.md
plugins/recall/docs/MEMORY_LIFECYCLE_REVIEW_PLAN.md
plugins/recall/docs/MEMORY_QUALITY_INGESTION_AUDIT_AND_PLAN.md
plugins/recall/CHANGELOG.md
plugins/recall/.codex-plugin/plugin.json
```

If making changes, create a `cdx/...` branch unless the user explicitly asks to work on another branch.

## Known Local Worktree Noise

At the time this file was added, the worktree had pre-existing local items that should not be disturbed unless the user asks:

```text
deleted: RECALL_Design_and_Development_Plan.md
untracked: DO NOT INCLUDE.rar
untracked: RECALL_quality_suite/
```

Do not inspect or extract `DO NOT INCLUDE.rar`.

## Common Commands

From the repo root:

```powershell
.\build_plugin.ps1
```

From the plugin root:

```powershell
cd .\plugins\recall
python -m unittest discover -s tests
python .\scripts\smoke_recall.py --json
.\build_plugin.ps1
```

Validate the plugin manifest with the local `plugin-creator` validator when available:

```powershell
python C:\Users\juliu\.codex\skills\.system\plugin-creator\scripts\validate_plugin.py .\plugins\recall
```

Run built-zip marketplace smoke:

```powershell
cd .\plugins\recall
python .\scripts\smoke_zip_marketplace.py --json
```

## Performance Checks

Performance matters because hooks may run frequently and memory stores can grow quickly.

A recent quick benchmark on 2026-06-09 passed with:

- `120` records
- `10` queries
- average query about `48 ms`
- p95 query about `60 ms`
- rebuild about `0.24 s`
- seed/write about `5.8 s`

The seed/write path is the weak spot. Prefer cheap ingestion gates that reject low-value hook events before storage, index append, or duplicate scans.

When touching hook ingestion, write policy, storage, retrieval, or index behavior, run at least:

```powershell
python RECALL_quality_suite\perf\benchmark_recall_memory.py --plugin-root plugins\recall --records 120 --queries 10
```

For release or larger policy changes, also run the full quality suite if `RECALL_quality_suite/` is present:

```powershell
python RECALL_quality_suite\scripts\run_recall_quality_suite.py --repo-root .
```

## Memory Quality Rules

The current priority is reducing automatic hook noise without losing valuable project memory.

Important current finding:

- Live memory inventory showed hundreds of `post_tool_use` command records and only a small number of meaningful project-state records.
- This is an ingestion-policy problem first, not a retrieval problem.

When changing hooks:

- Default-deny low-value `PostToolUse` writes.
- Ignore successful read-only exploration commands such as `Get-Content`, `rg`, `git status`, directory listings, and memory review commands.
- Always preserve explicit user memory cues.
- Preserve failures, actionable debugging history, build/test/release milestones, and real file-edit summaries.
- Do not store generic summaries like `Bash result captured.` as durable active memory.
- Do not turn greetings, one-word replies, or unrelated explanations into `project_state`.
- Prefer non-destructive archival over deletion for cleanup.

## Testing Expectations

For narrow docs-only changes, inspect the diff and run targeted checks if relevant.

For plugin code changes, run:

```powershell
cd .\plugins\recall
python -m unittest discover -s tests
python .\scripts\smoke_recall.py --json
```

For hook behavior changes, include tests under:

```text
plugins/recall/tests/test_hooks.py
plugins/recall/tests/test_write_policy.py
plugins/recall/tests/test_memory_hygiene.py
```

For retrieval or memory-quality changes, include tests under:

```text
plugins/recall/tests/test_retrieval_quality.py
plugins/recall/tests/test_memory_review.py
```

If `RECALL_quality_suite/` is present, add or update contract tests there when changing public behavior.

## Packaging Rules

Release artifacts must not include:

- `.codex_memory/`
- `__pycache__/`
- `.pyc`
- `.git/`
- personal paths
- secret-like strings

The build scripts and package inspector are expected to enforce this. Do not commit `dist/recall.zip`; attach it to releases instead.

## Git Discipline

Do not revert user changes or unrelated local changes.

Before committing, stage only the files owned by the current task. After staging, verify:

```powershell
git diff --cached --stat
```

Use focused commit messages, for example:

```text
docs: add agent guidance
fix: tighten recall hook ingestion policy
test: cover noisy hook suppression
```
