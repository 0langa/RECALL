---
name: retrieve-memory
description: Use when prior local RECALL project memory may help with the current Codex task or review.
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
