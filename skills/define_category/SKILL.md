---
name: define_category
description: Create or update a custom RECALL memory category with a description and retrieval weight.
---

# Define Category

Use this skill when the user wants a new memory category or wants to tune how strongly an existing category is retrieved.

## Workflow

1. Normalize the category to lower snake case.
2. Write a short description that explains what belongs in the category.
3. Choose a positive weight. Use `1.0` for normal priority, higher values such as `1.3` to surface the category more aggressively, and lower values such as `0.8` for background context.
4. Run:

```powershell
python .\scripts\memory_manager.py define-category <category> --description "<description>" --weight <weight>
```

## Example

```powershell
python .\scripts\memory_manager.py define-category api_contracts --description "Stable API shapes and compatibility promises." --weight 1.4
```
