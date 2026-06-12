---
name: save-insight
description: Use this skill proactively when debugging a durable failure, when testing a verified command, when implementing an accepted decision, or when recording a standing requirement for future threads. Trigger when durable evidence should persist; invoke automatically only for explicit evidence, never drafts.
---

# Save Insight

Use this skill when the user asks Codex to remember a decision, constraint, command, requirement, risk, preference, bug fix, task status, or other durable project context.

RECALL is local-only project memory. Store data under the active project's `.codex_memory/` directory and never require hosted services or external APIs. Do not store secrets, credentials, tokens, private keys, passwords, or sensitive personal data.

## Execution Path

Use this skill as the public RECALL interface. When shell execution is needed, run the bundled skill adapter from the installed plugin root or source plugin root. Treat lower-level backend scripts as internal support code, not as the user-facing RECALL workflow.

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

## Examples

```bash
python ./scripts/recall_skill.py save-insight decisions "Use SQLite as RECALL's default backend." --summary "SQLite is the default backend." --details "It is local, embedded, and requires no service." --tag sqlite --tag local-first --source skill --status active --importance 0.8 --confidence 0.9
python ./scripts/recall_skill.py save-insight commands "Verified test command: python -m unittest discover -s tests" --summary "Use unittest discovery for validation." --tag tests --tag command --source skill --status active --importance 0.7 --confidence 1.0
python ./scripts/recall_skill.py supersede-memory 12 18 --note "Memory #18 corrects the older decision."
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

## Edge Cases

- Drafts and one-task constraints are not standing preferences.
- Corrections should supersede old truth instead of creating two current claims.
- File-backed facts should carry `--source-path` so reconciliation can stale them.
- Exact duplicates should confirm/update existing memory, not multiply records.

## Troubleshooting

- Secret-like text: do not weaken redaction; remove secret and save only durable fact.
- Wrong category: use `edit-memory` after retrieving exact ID.
- Conflicting current claims: run `list-conflicts`, then `resolve-conflict`.
- Reusable custom category: refine it through `define-category`.

## Related

- [Retrieve Memory](../retrieve-memory/SKILL.md) for task-focused recall.
- [Review Memory](../review-memory/SKILL.md) for inspection and conflict review.
- [Manage Memory](../manage-memory/SKILL.md) for lifecycle changes.
- [Evidence guide](references/evidence-policy.md) for durable write decisions.
