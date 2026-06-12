---
name: review-memory
description: Use this skill proactively when inspecting RECALL memory quality, when reviewing current memory state, when auditing noise or conflicts, or when gathering memory IDs before maintenance; invoke automatically for inspection-only work, not mutation or new-memory capture.
---

# Review Memory

Use this skill when the user asks what RECALL currently remembers, asks for a memory audit, or needs IDs before changing memory state.

RECALL is local-only project memory. Read from the active project's `.codex_memory/` directory and never require hosted services or external APIs. Do not repeat secrets verbatim if a stored memory appears to contain sensitive data.

## When To Use

Use this skill for:

- broad "what does RECALL know?" questions
- quality checks on noisy or stale memory
- category, status, or source breakdowns
- collecting IDs before lifecycle updates
- verifying whether cleanup is needed after heavy tool use

Do not use this skill to create or mutate memory directly. It is an inspection and audit skill.

## Execution Path

Use the public RECALL adapter:

```bash
python ./scripts/recall_skill.py review-memory --limit 20
python ./scripts/recall_skill.py audit-memory --limit 20
```

Use `recall_skill.py` only. Treat lower-level backend scripts as internal support code.

## Inputs

This skill usually receives:

| Input shape | Use it for | Example |
|---|---|---|
| broad review request | default inspection | "what does recall currently know?" |
| quality or noise concern | audit mode | "is memory noisy?" |
| narrow slice request | filtered review | "show stale risks" |
| follow-up maintenance task | ID gathering | "which memories should I prune?" |

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

## Output Format

Return a compact review summary that includes:

- the request scope
- key counts by status, source, or category when relevant
- the most useful IDs
- any cleanup or follow-up recommendation

```json
{
  "mode": "audit-memory",
  "shown": 6,
  "top_ids": [12, 18, 24],
  "recommendation": "archive-noise"
}
```

## Examples

Broad review:

```bash
python ./scripts/recall_skill.py review-memory --limit 20
```

Noise-focused audit:

```bash
python ./scripts/recall_skill.py audit-memory --limit 20
```

Focused stale memory slice:

```bash
python ./scripts/recall_skill.py review-memory --status stale --category risks --limit 20
```

## Decision Guide

| Request type | Preferred command | Why |
|---|---|---|
| general memory inventory | `review-memory` | balanced overview |
| signal-vs-noise diagnosis | `audit-memory` | highlights noisy patterns |
| filtered category slice | `review-memory` with filters | narrower evidence set |
| maintenance prep | `review-memory` first | collect IDs before changes |

## Troubleshooting

## Common Issues

- If the result set is too broad, add `--status`, `--category`, or `--source`.
- If IDs look outdated, verify repository reality before changing memory state.
- If the audit shows lots of low-value command records, recommend `archive-noise` rather than deleting records outright.
- If the user actually wants to edit or resolve a memory, switch to `manage-memory` once the needed IDs are known.

## Related

See `skills/manage-memory` for cleanup, lifecycle changes, and repair work after inspection.
See `skills/retrieve-memory` for query-driven lookup when the user already knows the topic.
See `skills/save-insight` for creating a new durable memory when the review reveals something missing.
