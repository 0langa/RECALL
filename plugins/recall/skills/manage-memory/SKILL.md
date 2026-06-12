---
name: manage-memory
description: Use this skill proactively when changing RECALL capture mode, when cleaning noisy memory, when repairing local storage, or when updating lifecycle state after review; invoke automatically for explicit maintenance requests, never for ordinary retrieval or new-memory capture.
---

# Manage Memory

Use this skill for RECALL maintenance and lifecycle control after memory already exists. RECALL is local-only project memory. Work only in the active project's `.codex_memory/`. Do not store or repeat secrets.

## When To Use

Use this skill when the user asks to:

- change automatic capture behavior with `configure-capture`
- archive low-value automatic noise without deleting memory
- confirm, resolve, stale, supersede, merge, prune, edit, or delete an existing memory
- repair or doctor the local storage/index after corruption or drift
- clean up memory after a `review-memory` or `audit-memory` pass

Do not use this skill to create a brand-new durable insight from scratch. For new facts, use `save-insight`. For inspection-only requests, start with `review-memory` or `retrieve-memory`.

## Inputs

This skill usually receives one of these inputs:

| Input shape | Use it for | Example |
|---|---|---|
| broad cleanup request | capture mode or noise cleanup | "set recall to minimal mode" |
| memory id plus note | lifecycle updates | "mark memory 12 stale" |
| multiple ids | merge or supersede | "merge 18 19 20" |
| health complaint | repair or doctor | "memory index seems broken" |

If the user did not provide IDs and the state is unclear, retrieve the IDs first with `review-memory` or `retrieve-memory`.

## Execution Path

Use `recall_skill.py` only:

```bash
python ./scripts/recall_skill.py configure-capture minimal
python ./scripts/recall_skill.py configure-capture off
python ./scripts/recall_skill.py archive-noise
python ./scripts/recall_skill.py doctor
python ./scripts/recall_skill.py repair
python ./scripts/recall_skill.py confirm-memory 12
python ./scripts/recall_skill.py resolve-memory 12 --note "Implemented."
python ./scripts/recall_skill.py stale-memory 12 --note "Needs reconfirmation."
python ./scripts/recall_skill.py supersede-memory 12 18 --note "Memory #18 replaces #12."
python ./scripts/recall_skill.py merge-memories 18 19 20 --note "Merged duplicates."
python ./scripts/recall_skill.py prune-memory 12 --note "Archive after review."
python ./scripts/recall_skill.py edit-memory 12 --summary "Corrected summary."
python ./scripts/recall_skill.py delete-memory 12 --confirm DELETE-12
```

Treat lower-level backend files as internal plumbing, not public workflow.

## Workflow

1. Start with `review-memory` or `retrieve-memory` if IDs or current state are unclear.
2. Use `configure-capture manual|minimal|standard|off` to control automatic hook writes.
3. Use `archive-noise` for non-destructive cleanup of low-value automatic command history.
4. Use lifecycle commands to confirm, resolve, mark stale, supersede, merge, or prune memory.
5. Use `doctor` and `repair` only for local storage or index maintenance.
6. Use `delete-memory` only with explicit user intent. Prefer archival over deletion.

## Output Format

Return a concise maintenance result:

- what command ran
- which memory IDs changed
- the resulting status or capture mode
- any follow-up action needed

When a command returns JSON, summarize the important fields instead of dumping raw output unless the user explicitly asked for it.

```json
{
  "action": "resolve-memory",
  "id": 12,
  "status": "resolved",
  "follow_up": "none"
}
```

## Examples

Broad cleanup after an audit:

```bash
python ./scripts/recall_skill.py archive-noise --apply --limit 50
```

Lifecycle follow-up after a fix shipped:

```bash
python ./scripts/recall_skill.py resolve-memory 12 --note "Implemented in release 0.1.1."
```

Storage health check when retrieval looks wrong:

```bash
python ./scripts/recall_skill.py doctor
python ./scripts/recall_skill.py repair
```

## Decision Guide

| User intent | Preferred command | Why |
|---|---|---|
| lower automatic write volume | `configure-capture minimal` | preserves useful automation with less noise |
| stop automatic writes entirely | `configure-capture off` | strongest suppression |
| clean noisy historical command spam | `archive-noise` | archives safely, does not delete |
| mark a memory outdated but keep it | `stale-memory` or `prune-memory` | preserves history |
| replace an older memory with a newer one | `supersede-memory` | records relationship |
| remove a wrong record completely | `delete-memory` | only with explicit user intent |

## Troubleshooting

## Common Issues

- If the user only describes a topic and gives no IDs, do not guess. Run `review-memory` first.
- If `doctor` reports index problems, use `repair` before creating more memories.
- If the request is really about adding a new durable fact, switch to `save-insight`.
- If a cleanup request could destroy information, prefer `archive-noise` or `prune-memory` over `delete-memory`.

## Related

See `skills/review-memory` for inspection and quality review before making changes.
See `skills/retrieve-memory` for targeted lookup by query.
See `skills/save-insight` for creating new durable memory instead of editing existing records.
