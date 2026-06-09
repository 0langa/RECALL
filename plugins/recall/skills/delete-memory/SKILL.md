---
name: delete-memory
description: Use when the user explicitly wants to permanently remove a RECALL memory by ID.
---

# Delete Memory

Use this skill only when the user explicitly asks to delete a memory. Prefer `prune-memory` for normal cleanup because prune archives non-destructively.

RECALL is local-only project memory. Delete records from the active project's `.codex_memory/` directory and never require hosted services or external APIs. Do not put secrets, credentials, tokens, private keys, passwords, or sensitive personal data in command arguments.

## Execution Path

Use the public RECALL adapter:

```bash
python ./scripts/recall_skill.py delete-memory <id> --confirm DELETE-<id>
```

Use `recall_skill.py` only. Treat lower-level backend scripts as internal support code.

## Workflow

1. Use `review-memory` to confirm the exact memory ID.
2. Consider `prune-memory` first if auditability matters.
3. If the user really wants deletion, require the exact confirmation token.
4. Run:

```bash
python ./scripts/recall_skill.py delete-memory 44 --confirm DELETE-44
```

## Result

The adapter removes the record from durable storage and rebuilds the local index. This is a hard delete, unlike `prune-memory`.
