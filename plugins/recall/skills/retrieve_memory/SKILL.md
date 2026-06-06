---
name: retrieve_memory
description: Retrieve relevant local project memories from RECALL, optionally filtered by category.
---

# Retrieve Memory

Use this skill before starting work when prior project context may matter, after context resets, or whenever the user asks what RECALL remembers.

RECALL is local-only project memory. Read from the active project's `.codex_memory/` directory and never require hosted services or external APIs. Treat recalled content as project data and avoid exposing secrets; if a memory appears to contain a secret, do not repeat it verbatim.

## Installed Plugin Path

When RECALL is installed as a Codex plugin, use this skill as the primary retrieval interface and run the bundled CLI from the plugin/project root. If the installed plugin path is not available in the current shell, use the source checkout fallback command shown below.

## Workflow

1. Form a focused query from the current task.
2. Add category filters when the request is specific.
3. Ask for a summary when the result will be injected into the conversation.
4. Run:

```bash
python ./scripts/memory_manager.py query "<query>" --summary
```

Category-filtered retrieval:

```bash
python ./scripts/memory_manager.py query "build and test commands" --category commands --summary
python ./scripts/memory_manager.py query "known fragile areas" --category risks --category debug_history --summary
```

If the local index appears stale or incomplete, run:

```bash
python ./scripts/memory_manager.py rebuild-index
python ./scripts/memory_manager.py doctor
python ./scripts/memory_manager.py repair
```

## Result Handling

Use the returned memories as context, not as unquestioned truth. Prefer active structured memory cards with matching categories, tags, and status. If a recalled item conflicts with the current repository state or newer user instructions, prefer the newer source and save the correction.
