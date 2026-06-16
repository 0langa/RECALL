---
name: save-insight
description: Use this skill proactively when debugging a durable failure, when testing a verified command, when implementing an accepted decision, or when recording a standing requirement for future threads. Trigger when durable evidence should persist; invoke automatically only for explicit evidence, never drafts.
---

# Save Insight

Use this skill when the user asks Codex to remember a decision, constraint, command, requirement, risk, preference, bug fix, task status, or other durable project context.

RECALL is local-only project memory. Store data under the active project's `.codex_memory/` directory and never require hosted services or external APIs. Do not store secrets, credentials, tokens, private keys, passwords, or sensitive personal data.

## Execution Path

Use this skill as the public RECALL interface. When shell execution is needed, run the bundled skill adapter from the installed plugin root or source plugin root. Treat lower-level backend scripts as internal support code, not as the user-facing RECALL workflow.

## Contract

This skill receives a verified durable fact and returns a saved, updated, linked, or ignored
memory record. It owns new memory capture only. It does not perform broad retrieval, lifecycle
cleanup, category design, or inspection reports except when checking for exact duplicates or
conflicts before a write.

Contract schema:

| Field | Required | Meaning |
|---|---:|---|
| `category` | yes | built-in or intentional custom category |
| `content` | yes | durable non-secret fact to preserve |
| `summary` | yes | one-sentence future-useful retrieval label |
| `details` | preferred | supporting context, evidence, or acceptance rule |
| `metadata` | preferred | tags, source, status, importance, confidence |
| `provenance` | when known | source path, claim key/value, or preference evidence |
| `result` | yes | saved, updated, linked, ignored, or rejected action |

Use the contract asset as the quick boundary check:

```json
{"asset":"assets/contract.json","kind":"write-boundary"}
```

## Categories

Prefer one of RECALL's built-in categories:

- `decisions`
- `constraints`
- `debug_history`
- `preferences`
- `tasks`
- `session_summaries`
- `project_state`
- `architecture`
- `commands`
- `lessons_learned`
- `requirements`
- `risks`

Custom categories are allowed. If a category does not exist, RECALL auto-creates it with a default weight and records a warning in metadata. After auto-creation, recommend refining the category with `define-category` when the category will be reused.

## Memory Card Shape

Prefer structured, scannable memory cards. Keep `content` human-readable and put durable retrieval fields in metadata:

```json
{
  "summary": "One sentence future-useful memory.",
  "details": "Short supporting context, cause, decision, or acceptance rule.",
  "tags": ["lowercase-tag", "project-area"],
  "source": "user|pre_compact|post_tool_use|manual",
  "status": "active|open|resolved|superseded|stale|archived",
  "importance": 0.0,
  "confidence": 0.0
}
```

Lifecycle fields may also be present when a memory was confirmed, merged, superseded, or reviewed: `related_to`, `supersedes`, `superseded_by`, `source_session`, and `last_confirmed`. Prefer using the public review/lifecycle adapter commands to manage those fields instead of editing metadata by hand.

## Workflow

1. Choose the most specific category.
2. Rewrite the memory as a concise, future-useful card with summary, details, tags, source, status, importance, and confidence when available.
3. Do not store secrets, credentials, tokens, private keys, passwords, or sensitive personal data.
4. Run the skill adapter:

```bash
python ./scripts/recall_skill.py save-insight <category> "<memory text>" --summary "<short summary>" --details "<supporting detail>" --tag <tag> --source skill --status active --importance 0.8 --confidence 0.9
```

Use `--source-path` when a claim comes from a project file. Use `--claim-key` and
`--claim-value` for mutually exclusive current-truth claims. Preference memories
must include durable evidence through `--preference-key`,
`--preference-evidence-type`, and `--decision-id`.

5. If the write reveals an existing conflicting current-truth claim, save only the verified
new record and hand conflict resolution to `manage-memory`; do not run lifecycle commands
from this skill.
6. If the category is missing but clearly reusable, save with the auto-created category and
recommend refining it with `define-category`; do not design the taxonomy here.

## Examples

```bash
python ./scripts/recall_skill.py save-insight decisions "Use SQLite as RECALL's default backend." --summary "SQLite is the default backend." --details "It is local, embedded, and requires no service." --tag sqlite --tag local-first --source skill --status active --importance 0.8 --confidence 0.9
python ./scripts/recall_skill.py save-insight commands "Verified test command: python -m unittest discover -s tests" --summary "Use unittest discovery for validation." --tag tests --tag command --source skill --status active --importance 0.7 --confidence 1.0
```

File-backed architecture fact:

```bash
python ./scripts/recall_skill.py save-insight architecture "Retrieval uses local SQLite plus deterministic scoring." --summary "Retrieval is local SQLite-backed." --details "Use source provenance when this claim comes from project files." --tag retrieval --source skill --status active --importance 0.8 --confidence 0.9 --source-path "plugins/recall/docs/architecture.md"
```

Current-truth claim:

```bash
python ./scripts/recall_skill.py save-insight project_state "Latest Kimi standard average is 90.12." --summary "Latest Kimi score is 90.12." --tag eval --source skill --status active --importance 0.9 --confidence 0.95 --claim-key recall.kimi.standard_average --claim-value 90.12
```

Rejected secret-like input:

```json
{"action":"rejected","reason":"secret-like content must not be stored","category":null}
```

Duplicate write:

```json
{"action":"updated","id":42,"category":"commands","reason":"exact durable command already existed"}
```

## Inputs

Required: category, durable content, concise summary. Add details, tags, source,
importance, confidence, and provenance when known. Reject empty, secret-like, or
purely temporary content.

## Output Format

Returns JSON with saved record ID and category. For preference evidence or automatic writes,
report whether RECALL saved, updated, linked, or ignored the candidate.

```json
{"action":"save-insight","id":42,"category":"decisions"}
```

When no write is made, return a reason instead of falling through silently:

```json
{"action":"ignored","reason":"draft or temporary output","category":null}
```

## Ownership Boundaries

| Request | This skill action | Handoff |
|---|---|---|
| "remember this verified decision" | save durable card | none |
| "replace old memory 12 with this" | save new verified card if needed | skills/manage-memory for supersession |
| "what do we know about evals?" | do not answer from memory | skills/retrieve-memory |
| "make a new eval category" | do not design taxonomy | skills/define-category |
| "show noisy memories" | do not audit inventory | skills/review-memory |

## Edge Cases

- Drafts and one-task constraints are not standing preferences.
- Corrections should supersede old truth instead of creating two current claims.
- File-backed facts should carry `--source-path` so reconciliation can stale them.
- Exact duplicates should confirm/update existing memory, not multiply records.
- Low-confidence observations should be stored as risks or tasks only when they will change future work.
- Secrets or secret-like snippets should be rejected; save only the non-sensitive operational fact.
- User preferences require evidence fields, not a bare assertion from one ambiguous interaction.
- Temporary command output belongs in the answer, not memory, unless it becomes a verified reusable command.

## Troubleshooting

- Secret-like text: do not weaken redaction; remove secret and save only durable fact.
- Wrong category: use `edit-memory` after retrieving exact ID.
- Conflicting current claims: save the verified new fact with a claim key, then hand resolution to `manage-memory`.
- Reusable custom category: refine it through `define-category`.
- Adapter path confusion: run from the installed plugin root or source plugin root so `./scripts/recall_skill.py` resolves.
- Missing category: let RECALL auto-create only when the category is clearly reusable, then refine through `define-category`.

## Related

- [Retrieve Memory](../retrieve-memory/SKILL.md) for task-focused recall.
- [Review Memory](../review-memory/SKILL.md) for inspection and conflict review.
- [Manage Memory](../manage-memory/SKILL.md) for lifecycle changes.
- [Evidence guide](references/evidence-policy.md) for durable write decisions.
- Sibling routes: skills/retrieve-memory, skills/review-memory, skills/manage-memory, skills/define-category.
