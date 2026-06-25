---
name: manage-memory
description: Use this skill when changing RECALL capture mode, when cleaning noisy memory, when repairing local storage, or when updating lifecycle state after review. Use proactively for explicit maintenance requests, never for ordinary retrieval or new-memory capture.
---

# Manage Memory

Use this skill for RECALL maintenance and lifecycle control after memory already exists. RECALL is local-only project memory. Work only in the active project's RECALL memory directory: `.recall/` for new projects, or existing `.codex_memory/` stores for legacy projects. Do not store or repeat secrets.

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

## Contract

This skill receives an existing-memory maintenance request and returns the lifecycle, capture,
or storage-health change that was made. It does not create new durable facts and it does not
perform inspection-only reports except to collect IDs needed for a maintenance action.

Contract schema:

| Field | Required | Meaning |
|---|---:|---|
| `intent` | yes | capture-mode, cleanup, lifecycle, doctor, or repair |
| `ids` | for lifecycle | exact memory IDs gathered from user input or review output |
| `note` | for state change | concise reason preserved in lifecycle metadata |
| `safety` | for deletion | explicit confirmation token for destructive delete |
| `result` | yes | command run, changed IDs, status/capture mode, follow-up |

Use the contract asset when deciding whether the request belongs here:

```json
{"asset":"assets/contract.json","kind":"maintenance-boundary"}
```

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

For multi-record work, keep the same shape and make changed IDs explicit:

```json
{"action":"archive-noise","changed_ids":[18,19,22],"status":"archived","follow_up":"none"}
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

Capture-mode change:

```bash
python ./scripts/recall_skill.py configure-capture minimal
```

Safe lifecycle correction:

```bash
python ./scripts/recall_skill.py stale-memory 42 --note "Repository state now contradicts this record."
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

## Ownership Boundaries

| Request | This skill action | Handoff |
|---|---|---|
| "save this decision" | decline direct write | skills/save-insight |
| "what does memory know?" | inspect only if IDs are needed | skills/review-memory |
| "find the old test command" | no lifecycle mutation | skills/retrieve-memory |
| "memory 12 is obsolete" | run stale/supersede/prune | none |
| "index looks broken" | run doctor, then repair if indicated | none |

## Troubleshooting

## Common Issues

- If the user only describes a topic and gives no IDs, do not guess. Run `review-memory` first.
- If `doctor` reports index problems, use `repair` before creating more memories.
- If the request is really about adding a new durable fact, switch to `save-insight`.
- If a cleanup request could destroy information, prefer `archive-noise` or `prune-memory` over `delete-memory`.
- If a retrieved memory conflicts with the repository, stale or supersede it rather than silently editing history.
- If the user asks for deletion but the record may still be historically useful, offer archival unless deletion is explicit.

## Related

See [Review Memory](../review-memory/SKILL.md) for inspection and quality review before making changes.
See [Retrieve Memory](../retrieve-memory/SKILL.md) for targeted lookup by query.
See [Save Insight](../save-insight/SKILL.md) for creating new durable memory instead of editing existing records.
See [Maintenance playbook](references/maintenance-playbook.md) for cleanup sequencing.
Sibling routes: skills/review-memory, skills/retrieve-memory, skills/save-insight.
