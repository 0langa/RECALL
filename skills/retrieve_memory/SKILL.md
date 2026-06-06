---
name: retrieve_memory
description: Retrieve relevant local project memories from RECALL, optionally filtered by category.
---

# Retrieve Memory

Use this skill before starting work when prior project context may matter, after context resets, or whenever the user asks what RECALL remembers.

## Workflow

1. Form a focused query from the current task.
2. Add category filters when the request is specific.
3. Ask for a summary when the result will be injected into the conversation.
4. Run:

```powershell
python .\scripts\memory_manager.py query "<query>" --summary
```

Category-filtered retrieval:

```powershell
python .\scripts\memory_manager.py query "build and test commands" --category commands --summary
python .\scripts\memory_manager.py query "known fragile areas" --category risks --category debug_history --summary
```

If the local index appears stale or incomplete, run:

```powershell
python .\scripts\memory_manager.py rebuild-index
python .\scripts\memory_manager.py doctor
```

## Result Handling

Use the returned memories as context, not as unquestioned truth. If a recalled item conflicts with the current repository state or newer user instructions, prefer the newer source and save the correction.
