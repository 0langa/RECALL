---
name: review-memory
description: Use when the user wants to inspect current RECALL memory quality, status, categories, sources, or lifecycle relationships.
---

# Review Memory

Use this skill when the user asks what RECALL currently remembers, asks for a memory audit, or needs IDs before changing memory state.

RECALL is local-only project memory. Read from the active project's `.codex_memory/` directory and never require hosted services or external APIs. Do not repeat secrets verbatim if a stored memory appears to contain sensitive data.

## Execution Path

Use the public RECALL adapter:

```bash
python ./scripts/recall_skill.py review-memory --limit 20
python ./scripts/recall_skill.py audit-memory --limit 20
```

Use `recall_skill.py` only. Treat lower-level backend scripts as internal support code.

## Filters

```bash
python ./scripts/recall_skill.py review-memory --status active --category requirements
python ./scripts/recall_skill.py review-memory --source finalizer --limit 50
python ./scripts/recall_skill.py review-memory --status stale --status superseded
```

## Workflow

1. Start with `review-memory --limit 20` when the request is broad.
2. Use `audit-memory --limit 20` when the user wants signal-vs-noise diagnosis, archive candidates, or noisy command patterns.
3. Add `--status`, `--category`, or `--source` filters when the user asks about a specific slice.
4. Use returned IDs with `manage-memory` commands such as `confirm-memory`, `resolve-memory`, `stale-memory`, `supersede-memory`, `merge-memories`, or `prune-memory`.
5. Treat the review as evidence to inspect, not as guaranteed truth over the current repository state.

## Result Handling

Report counts and the most relevant IDs. Prefer concise summaries over dumping every record. If many low-value automatic memories are present, recommend `archive-noise` for non-destructive cleanup and reserve `prune-memory` for targeted archival by ID.
