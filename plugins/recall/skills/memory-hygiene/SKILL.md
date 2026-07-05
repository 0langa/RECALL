---
name: memory-hygiene
description: Use this skill when deciding whether candidate context belongs in Recall memory, repo docs, skill/plugin instructions, provider config, or current chat only; when planning memory cleanup; when detecting stale, duplicate, conflicting, low-value, source-backed, command, or weak-preference memories; or when applying safe non-destructive hygiene. Use proactively for memory quality policy before using manage-memory for direct ID-based mutation.
---

# Memory Hygiene

Use this skill as RECALL's policy brain for memory quality. It routes candidate facts to the right durable surface, plans cleanup, and applies only safe non-destructive lifecycle changes.

RECALL is local-only project memory. Work in the active project's `.recall/` store, or the legacy `.codex_memory/` store when present. Do not store or repeat secrets, credentials, tokens, private keys, passwords, or sensitive personal data.

## Boundary

RECALL exposes seven public skills:

- `save-insight`: create new durable memory.
- `retrieve-memory`: targeted lookup.
- `review-memory`: inspect/audit only.
- `manage-memory`: direct lifecycle mutation when IDs/actions are already known.
- `define-category`: category taxonomy.
- `using-recall`: session usage guidance.
- `memory-hygiene`: routing, cleanup planning, safe automatic maintenance, and staleness/conflict policy.

Use `memory-hygiene` before mutation when the correct action is not already obvious. Hand exact ID-based lifecycle changes to `manage-memory` when the user already gave the action and IDs. Do not create new memories from this skill; hand new writes to `save-insight`.

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

Read `references/hygiene-policy.md` when a routing or cleanup decision is ambiguous. Read `references/routing-decision-tree.md` for step-by-step routing calls. Read `references/examples.md` for worked scan/plan/apply outputs.

## Contract

| Field | Required | Meaning |
|---|---:|---|
| `candidate_fact` | for `route-memory` | free text of a candidate durable fact |
| `claim_key` | for `reconcile-current-truth` | mutually exclusive claim slot to resolve |
| `scope` | for `hygiene-plan` | `project` (only value currently supported) |
| `--safe` | for `hygiene-apply` | required flag; refuses destructive changes |
| `--limit` | optional | cap the number of records inspected per pass |
| `result` | yes | JSON summary of proposals, inspected count, safe/apply status |

## Workflow

1. For a candidate fact, run `route-memory` before saving it.
2. For store quality work, run `hygiene-scan` or `hygiene-plan`.
3. Review proposals. Each proposal includes target IDs, action, confidence, reason, `safe_to_apply`, and follow-up.
4. Use `hygiene-apply --safe` only for high-confidence non-destructive changes.
5. Leave risky conflicts, near-duplicates, deletions, and ambiguous scope decisions for user confirmation.
6. Use `manage-memory` for explicit ID-based edits, deletion, or user-approved lifecycle work.

## Safe Actions

Safe automatic changes are non-destructive:

- `redact_secret`: secret-shaped content in an existing card is redacted in place (highest priority; policy says secrets must never be stored).
- `stale`: current repo evidence invalidates a memory, or a point-in-time snapshot (`project_state`, `session_summaries`, `integrations`, `tooling_quirks`) aged past the staleness window.
- `supersede`: validated current-truth claim clearly wins.
- `merge`: exact duplicate joins an older primary record.
- `prune`: low-value noise or a raw log/output dump is archived.
- `refresh_source`: source-backed memory still matches its file.
- `needs_confirmation`: weak preference or ambiguous memory is kept but demoted.

Review-only findings (never auto-applied): `review_near_duplicate`, `review_vague`
(memory too vague to act on), `review_metadata` (missing source/status provenance), and
`review_doc_duplicate` (memory restates README/docs content — repo docs win; prune the
memory or rewrite it to add non-doc insight). Doc-duplication detection is fully local
deterministic token comparison against `README.md` and `docs/**/*.md`; it makes no
model or network calls. Scan output includes a `next_action` telling you the correct follow-up.

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
| Secret-shaped stored content | propose safe `redact_secret`, apply immediately |
| Raw log or output dump stored as memory | propose safe `prune` |
| Vague unactionable memory | report `review_vague`, require rewrite or confirmation |
| Aged point-in-time snapshot | propose safe `stale` for verification |
| Missing source/status provenance | report `review_metadata` |
| Memory restates README/docs content | report `review_doc_duplicate`, require confirmation |

## Examples

Route a candidate fact:

```bash
python ./scripts/recall_skill.py route-memory "Release notes must stay in docs/manual-release-notes.md."
```

```json
{"action":"route-memory","target":"repo_docs","reason":"candidate belongs in project docs, not memory"}
```

Scan then plan then safe-apply:

```bash
python ./scripts/recall_skill.py hygiene-scan --limit 80
python ./scripts/recall_skill.py hygiene-plan --scope project --limit 80
python ./scripts/recall_skill.py hygiene-apply --safe --limit 20
```

Reconcile a conflicting current-truth claim:

```bash
python ./scripts/recall_skill.py reconcile-current-truth --claim-key recall.kimi.standard_average
```

## Inputs

Required: candidate fact for `route-memory`; claim key for `reconcile-current-truth`; `--safe` flag for `hygiene-apply`. Optional: `--limit`, `--scope`. Reject requests to run destructive actions from this skill; reject secret-shaped candidate facts before routing.

## Output Format

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

`hygiene-apply --safe` returns per-record outcomes:

```json
{"action":"hygiene-apply","applied":[{"id":42,"outcome":"stale"}],"skipped":[{"id":17,"reason":"needs_confirmation"}]}
```

`route-memory` returns a single target:

```json
{"action":"route-memory","target":"recall_memory","reason":"durable cross-session decision"}
```

## Ownership Boundaries

| Request | This skill action | Handoff |
|---|---|---|
| "should this go into memory?" | route candidate | none |
| "clean up noisy memory" | plan + safe apply | `manage-memory` for destructive follow-ups |
| "delete memory 42" | refuse from this skill | `manage-memory` `delete-memory --confirm` |
| "save this decision" | refuse; not a writer | `save-insight` |
| "show me all conflicts" | do not audit inventory | `review-memory` |
| "make a new category" | do not design taxonomy | `define-category` |

## Edge Cases

- Ambiguous scope: propose `needs_confirmation`, never guess between recall memory and repo docs.
- Near-duplicates with different provenance: report both, require confirmation before merge.
- Source-backed record whose file moved but still exists at the new path: refresh source, do not stale.
- Weak preference with no evidence: mark `needs_confirmation`, keep the record.
- Validated claim conflicting with a hypothesis claim: supersede hypothesis only when evidence lineage is clean.
- Secret-shaped candidate text: reject at `route-memory`, do not persist.

## Safety

- Treat current repository evidence as stronger than old memory.
- Preserve history through lifecycle metadata.
- Prefer stale/supersede/merge/archive over delete.
- Do not silently edit memory content to match new truth.
- If unsure, report `needs_confirmation`.

## Troubleshooting

- `hygiene-apply` refuses without `--safe`: this is intentional; do not remove the guard.
- Adapter path errors: run from installed/source plugin root, or use absolute path plus `--root`.
- Missing proposals for an obvious stale record: rerun `hygiene-scan --limit <higher>` to widen the window.
- Persistent conflicts on the same claim key: hand to `manage-memory resolve-conflict`.
- Route target keeps returning `current_chat_only` for a fact you want saved: strengthen the candidate wording with evidence, then rerun `route-memory`.

## Related

- [Hygiene policy](references/hygiene-policy.md) for full routing and cleanup rules.
- [Routing decision tree](references/routing-decision-tree.md) for step-by-step routing calls.
- [Worked examples](references/examples.md) for scan/plan/apply outputs.
- [Manage Memory](../manage-memory/SKILL.md) for exact mutation by ID.
- [Review Memory](../review-memory/SKILL.md) for inspection-only reporting.
- [Save Insight](../save-insight/SKILL.md) for new durable facts.
