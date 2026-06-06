---
name: define_category
description: Create or update a custom RECALL memory category with a description and retrieval weight.
---

# Define Category

Use this skill when the user wants a new memory category or wants to tune how strongly an existing category is retrieved.

RECALL is local-only project memory. Category definitions are stored in the active project's `.codex_memory/memory_config.json` file and never require hosted services or external APIs. Do not put secrets, credentials, tokens, private keys, passwords, or sensitive personal data in category names or descriptions.

## Installed Plugin Path

When RECALL is installed as a Codex plugin, use this skill as the primary category-management interface and run the bundled CLI from the plugin/project root. If the installed plugin path is not available in the current shell, use the source checkout fallback command shown below.

## Workflow

1. Normalize the category to lower snake case.
2. Write a short description that explains what belongs in the category.
3. Choose a positive weight. Use `1.0` for normal priority, higher values such as `1.3` to surface the category more aggressively, and lower values such as `0.8` for background context.
4. If RECALL auto-created this category from a saved memory, preserve the normalized name and refine only the description/weight.
5. Run:

```powershell
python .\scripts\memory_manager.py define-category <category> --description "<description>" --weight <weight>
```

## Example

```powershell
python .\scripts\memory_manager.py define-category api_contracts --description "Stable API shapes and compatibility promises." --weight 1.4
```
