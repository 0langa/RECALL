---
name: retrieve-memory
description: Use this skill proactively when debugging a known failure, when implementing work shaped by prior decisions, when testing with verified commands, or when starting a new thread that needs project state. Trigger when local memory prevents repeated investigation; invoke automatically only when project context is relevant.
---

# Retrieve Memory

Use this skill before starting work when prior project context may matter, after context resets, or whenever the user asks what RECALL remembers.

RECALL is local-only project memory. Read from the active project's RECALL memory directory: `.recall/` for new projects, or existing `.codex_memory/` stores for legacy projects. Never require hosted services or external APIs. Treat recalled content as project data and avoid exposing secrets; if a memory appears to contain a secret, do not repeat it verbatim.

## Execution Path

Use this skill as the public RECALL retrieval interface. When shell execution is needed, run the bundled skill adapter from the installed plugin root or source plugin root. Treat lower-level backend scripts as internal support code, not as the user-facing RECALL workflow.

All `python ./scripts/recall_skill.py ...` examples assume the current directory is the plugin root. If the shell is in the active project repository, do not look for `./scripts` there; locate the installed/source plugin root or use an absolute adapter path, then pass `--root <project-root>` when needed.

## Contract

This skill receives a focused lookup need and returns relevant memory context with enough
provenance to decide whether it is useful. It does not create, edit, archive, or confirm
memory. It does not treat memory as stronger evidence than current repository files or newer
user instructions.

Use the contract asset as the quick boundary check:

```json
{"asset":"assets/contract.json","kind":"retrieval-boundary"}
```

## Workflow

1. Form a focused query from the current task.
2. Add category filters when the request is specific.
3. Ask for a summary when the result will be injected into the conversation.
4. Run:

```bash
python ./scripts/recall_skill.py retrieve-memory "<query>" --summary
```

Category-filtered retrieval:

```bash
python ./scripts/recall_skill.py retrieve-memory "build and test commands" --category commands --summary
python ./scripts/recall_skill.py retrieve-memory "known fragile areas" --category risks --category debug_history --summary
```

If retrieval appears stale, incomplete, or index-related, stop the retrieval answer at the
sufficiency boundary and hand maintenance to `manage-memory`. If the task is to inspect what
RECALL currently believes rather than answer a focused query, hand the task to `review-memory`.

## Result Handling

Use the returned memories as context, not as unquestioned truth. Prefer active structured memory cards with matching categories, tags, and status. If a recalled item conflicts with the current repository state or newer user instructions, prefer the newer source and save the correction.

Apply a sufficiency check before answering from memory:

- Enough memory: relevant active records answer the specific question and include usable IDs, status, or provenance.
- Partial memory: answer only the supported part and say what is still missing.
- Not enough memory: say RECALL does not currently contain enough evidence and continue from repository/user evidence.
- Conflicting memory: label the conflict and use `review-memory` or `manage-memory` for follow-up instead of blending incompatible claims.

For compact injection under a hard budget, use:

```bash
python ./scripts/recall_skill.py context-packet "current task" --token-budget 1200
```

## Handoff Boundaries

| Situation | Retrieval response | Handoff |
|---|---|---|
| no relevant records | say memory lacks enough evidence | none |
| stale or incomplete index suspected | do not repair from this skill | skills/manage-memory |
| user wants inventory or counts | do not broaden query | skills/review-memory |
| verified correction discovered | do not write from this skill | skills/save-insight |
| lifecycle status needs changing | do not mutate memory | skills/manage-memory |

## Inputs

Required: focused query. Optional: categories, explicit statuses, result limit,
summary, or context-packet token budget.

## Output Format

Returns JSON with relevant IDs, categories, statuses, sources, and concise current context.
Context packets also report estimated tokens, score components, and omitted count.

```json
{"query":"current storage decision","results":[{"id":12,"category":"decisions","score":1.04}]}
```

## Examples

Current decisions:

```bash
python ./scripts/recall_skill.py retrieve-memory "current storage decision" --category decisions --status validated --summary
```

Historical investigation:

```bash
python ./scripts/recall_skill.py retrieve-memory "old retrieval design" --status superseded --status archived --summary
```

Sufficiency-first lookup:

```bash
python ./scripts/recall_skill.py retrieve-memory "current quality gate threshold and latest Kimi score" --category project_state --category tasks --status active --summary
```

Compact context packet:

```bash
python ./scripts/recall_skill.py context-packet "implement retrieval sufficiency gate" --token-budget 1200
```

## Edge Cases

- No results: say memory lacks answer; do not invent source detail.
- Stale result requested explicitly: label it historical, not current truth.
- Repository contradicts memory: prefer repository, then save correction/supersession.
- Broad noisy query: narrow categories or use `review-memory` first.
- One high-score record but no provenance: use it as a lead, not final truth.
- Multiple current records disagree: stop and inspect conflicts before answering.
- User asks for all memory: use `review-memory`, not unbounded retrieval.

## Troubleshooting

- Missing records: report insufficient memory and hand storage diagnostics to `manage-memory`.
- Source-linked claim seems wrong: report the mismatch and hand reconciliation to `manage-memory`.
- Multiple current answers: label the conflict and hand conflict review to `review-memory` or `manage-memory`.
- Packet too large: lower token budget; title-only fallback is automatic.
- Retrieval returns command noise: filter by category/status or run an audit before injecting context.
- A task needs durable follow-up after retrieval: save only verified corrections through `save-insight`.

## Related

- [Review Memory](../review-memory/SKILL.md) for inventory and quality inspection.
- [Save Insight](../save-insight/SKILL.md) for verified corrections.
- [Manage Memory](../manage-memory/SKILL.md) for lifecycle changes.
- [Retrieval guide](references/retrieval-guide.md) for query strategy.
- Sibling routes: skills/review-memory, skills/save-insight, skills/manage-memory.
