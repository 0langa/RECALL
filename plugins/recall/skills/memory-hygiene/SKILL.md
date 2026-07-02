---
name: memory-hygiene
description: Use this skill when deciding whether candidate context belongs in Recall memory, repo docs, skill/plugin instructions, provider config, or current chat only; when planning memory cleanup; when detecting stale, duplicate, conflicting, low-value, source-backed, command, or weak-preference memories; or when applying safe non-destructive hygiene. Use proactively for memory quality policy before using manage-memory for direct ID-based mutation.
---

# Memory Hygiene

Use this skill as RECALL's policy brain for memory quality. It routes candidate facts to the right durable surface, plans cleanup, and applies only safe non-destructive lifecycle changes.

RECALL remains local-only. Work in the active project's `.recall/` store, or the legacy `.codex_memory/` store when present. Do not store or repeat secrets.

## Boundary

RECALL now exposes seven public skills:

- `save-insight`: create new durable memory.
- `retrieve-memory`: targeted lookup.
- `review-memory`: inspect/audit only.
- `manage-memory`: direct lifecycle mutation when IDs/actions are already known.
- `define-category`: category taxonomy.
- `using-recall`: session usage guidance.
- `memory-hygiene`: routing, cleanup planning, safe automatic maintenance, and staleness/conflict policy.

Use `memory-hygiene` before mutation when the correct action is not already obvious. Hand exact ID-based lifecycle changes to `manage-memory` when the user already gave the action and IDs.

## Execution Path

Run these examples from the installed/source plugin root so `./scripts/recall_skill.py` resolves. If the shell is in the active project repository, use the adapter's absolute path and pass `--root <project-root>`.

```bash
python ./scripts/recall_skill.py route-memory "<candidate fact>"
python ./scripts/recall_skill.py hygiene-scan --limit 80
python ./scripts/recall_skill.py hygiene-plan --scope project
python ./scripts/recall_skill.py hygiene-apply --safe
python ./scripts/recall_skill.py reconcile-current-truth --claim-key recall.kimi.standard_average
python ./scripts/recall_skill.py refresh-source-backed
```

Use the contract asset as the quick boundary check:

```json
{"asset":"assets/contract.json","kind":"hygiene-boundary"}
```

Read `references/hygiene-policy.md` when a routing or cleanup decision is ambiguous.

## Workflow

1. For a candidate fact, run `route-memory` before saving it.
2. For store quality work, run `hygiene-scan` or `hygiene-plan`.
3. Review proposals. Each proposal includes target IDs, action, confidence, reason, `safe_to_apply`, and follow-up.
4. Use `hygiene-apply --safe` only for high-confidence non-destructive changes.
5. Leave risky conflicts, near-duplicates, deletions, and ambiguous scope decisions for user confirmation.
6. Use `manage-memory` for explicit ID-based edits, deletion, or user-approved lifecycle work.

## Output Shape

Plans return JSON-like summaries:

```json
{
  "action": "hygiene-plan",
  "inspected": 80,
  "proposals": [
    {
      "id": 42,
      "proposed_action": "stale",
      "confidence": 0.91,
      "reason": "source_path no longer exists",
      "safe_to_apply": true
    }
  ],
  "requires_confirmation": [17]
}
```

## Safe Actions

Safe automatic changes are non-destructive:

- `stale`: current repo evidence invalidates a memory.
- `supersede`: validated current-truth claim clearly wins.
- `merge`: exact duplicate joins an older primary record.
- `prune`: low-value noise is archived.
- `refresh_source`: source-backed memory still matches its file.
- `needs_confirmation`: weak preference or ambiguous memory is kept but demoted.

Never hard-delete from this skill. If deletion is explicit, use `manage-memory` and `delete-memory --confirm DELETE-<id>`.

## Decision Guide

| Situation | Action |
|---|---|
| Candidate belongs in durable project context | route to `recall_memory`, then use `save-insight` |
| Candidate changes README/docs/runbook/release notes | route to `repo_docs` |
| Candidate changes `SKILL.md`, plugin manifests, hooks, or agent instructions | route to `skill_or_plugin_instructions` |
| Candidate changes provider config such as `AGENTS.md`, `CLAUDE.md`, Kimi/Codex settings | route to `provider_config` |
| Candidate is temporary, draft, or one-off | route to `current_chat_only` |
| Source file missing/changed | propose `stale` |
| Exact duplicate | propose safe `merge` |
| Near duplicate | report, require confirmation |
| Conflicting claim key | pick validated/high-trust winner only when clear |
| Weak preference without evidence | mark `needs_confirmation` |

## Safety

- Treat current repository evidence as stronger than old memory.
- Preserve history through lifecycle metadata.
- Prefer stale/supersede/merge/archive over delete.
- Do not silently edit memory content to match new truth.
- If unsure, report `needs_confirmation`.

## Related

- [Hygiene policy](references/hygiene-policy.md)
- [Manage Memory](../manage-memory/SKILL.md) for exact mutation by ID.
- [Review Memory](../review-memory/SKILL.md) for inspection-only reporting.
- [Save Insight](../save-insight/SKILL.md) for new durable facts.
