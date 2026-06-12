---
name: retrieve-memory
description: Use this skill proactively when debugging a known failure, when implementing work shaped by prior decisions, when testing with verified commands, or when starting a new thread that needs project state. Trigger when local memory prevents repeated investigation; invoke automatically only when project context is relevant.
---

# Retrieve Memory

Use this skill before starting work when prior project context may matter, after context resets, or whenever the user asks what RECALL remembers.

RECALL is local-only project memory. Read from the active project's `.codex_memory/` directory and never require hosted services or external APIs. Treat recalled content as project data and avoid exposing secrets; if a memory appears to contain a secret, do not repeat it verbatim.

## Execution Path

Use this skill as the public RECALL retrieval interface. When shell execution is needed, run the bundled skill adapter from the installed plugin root or source plugin root. Treat lower-level backend scripts as internal support code, not as the user-facing RECALL workflow.

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

If retrieval appears stale or incomplete, run the safe public diagnostic path before suggesting backend maintenance:

```bash
python ./scripts/recall_skill.py doctor
```

If `doctor` reports an incomplete index or available repairs, ask before running:

```bash
python ./scripts/recall_skill.py repair
```

When the task is to inspect what RECALL currently believes, use the review surface instead of broad retrieval:

```bash
python ./scripts/recall_skill.py review-memory --limit 20
python ./scripts/recall_skill.py review-memory --status active --category requirements
```

## Result Handling

Use the returned memories as context, not as unquestioned truth. Prefer active structured memory cards with matching categories, tags, and status. If a recalled item conflicts with the current repository state or newer user instructions, prefer the newer source and save the correction.

For compact injection under a hard budget, use:

```bash
python ./scripts/recall_skill.py context-packet "current task" --token-budget 1200
```

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

## Edge Cases

- No results: say memory lacks answer; do not invent source detail.
- Stale result requested explicitly: label it historical, not current truth.
- Repository contradicts memory: prefer repository, then save correction/supersession.
- Broad noisy query: narrow categories or use `review-memory` first.

## Troubleshooting

- Missing records: run `doctor`; run `repair` only when report offers repair.
- Source-linked claim seems wrong: run `reconcile-sources`.
- Multiple current answers: run `list-conflicts` or `audit-memory`.
- Packet too large: lower token budget; title-only fallback is automatic.

## Related

- [Review Memory](../review-memory/SKILL.md) for inventory and quality inspection.
- [Save Insight](../save-insight/SKILL.md) for verified corrections.
- [Manage Memory](../manage-memory/SKILL.md) for lifecycle changes.
- [Retrieval guide](references/retrieval-guide.md) for query strategy.
