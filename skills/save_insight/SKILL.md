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

## Memory Card Shape

Prefer structured, scannable memory cards. Keep `content` human-readable and put durable retrieval fields in metadata:

```json
{
  "summary": "One sentence future-useful memory.",
  "details": "Short supporting context, cause, decision, or acceptance rule.",
  "tags": ["lowercase-tag", "project-area"],
  "source": "user|pre_compact|post_tool_use|manual",
  "status": "active|open|resolved|superseded|archived",
  "importance": 0.0,
  "confidence": 0.0
}
```

## Workflow

1. Choose the most specific category.
2. Rewrite the memory as a concise, future-useful card with summary, details, tags, source, status, importance, and confidence when available.
3. Do not store secrets, credentials, tokens, private keys, or passwords.
4. Run:

```powershell
python .\scripts\memory_manager.py add <category> "<memory text>" --summary "<short summary>" --details "<supporting detail>" --tag <tag> --source manual --status active --importance 0.8 --confidence 0.9
```

Use `--metadata` with a JSON object when file paths, command names, or issue IDs matter.

## Examples

```powershell
python .\scripts\memory_manager.py add decisions "Use SQLite as RECALL's default backend." --summary "SQLite is the default backend." --details "It is local, embedded, and requires no service." --tag sqlite --tag local-first --source manual --status active --importance 0.8 --confidence 0.9
python .\scripts\memory_manager.py add commands "Verified test command: python -m unittest discover -s tests" --summary "Use unittest discovery for validation." --tag tests --tag command --source manual --status active --importance 0.7 --confidence 1.0
```
