---
name: save_insight
description: Save a project-specific memory into RECALL using a structured category and optional metadata.
---

# Save Insight

Use this skill when the user asks Codex to remember a decision, constraint, command, requirement, risk, preference, bug fix, task status, or other durable project context.

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

Custom categories are allowed. If a category does not exist, RECALL auto-creates it with a default weight and records a warning in metadata.

## Workflow

1. Choose the most specific category.
2. Rewrite the memory as a concise, future-useful note.
3. Do not store secrets, credentials, tokens, private keys, or passwords.
4. Run:

```powershell
python .\scripts\memory_manager.py add <category> "<memory text>"
```

Use `--metadata` with a JSON object when file paths, command names, or issue IDs matter.

## Examples

```powershell
python .\scripts\memory_manager.py add decisions "Use SQLite as RECALL's default backend because it is local, embedded, and requires no service."
python .\scripts\memory_manager.py add commands "Verified test command: python -m unittest discover -s tests"
```
