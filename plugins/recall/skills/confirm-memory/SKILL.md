---
name: confirm-memory
description: Use when a RECALL memory is verified and should be marked confirmed/current.
---

# Confirm Memory

Use this skill when the user or current project evidence verifies that an existing RECALL memory is still true and useful.

RECALL is local-only project memory. Update metadata under the active project's `.codex_memory/` directory and never require hosted services or external APIs. Do not add secrets, credentials, tokens, private keys, passwords, or sensitive personal data to lifecycle notes.

## Execution Path

Use the public RECALL adapter:

```bash
python ./scripts/recall_skill.py confirm-memory <id>
```

Use `recall_skill.py` only. Treat lower-level backend scripts as internal support code.

## Workflow

1. Use `review-memory` or `retrieve-memory` to find the memory ID.
2. Verify the memory against current project evidence when possible.
3. Confirm only the specific memory that remains true.
4. Run:

```bash
python ./scripts/recall_skill.py confirm-memory 12 --source-session "<session-id>"
```

## Result

The adapter increments `confirmed_count`, updates `last_confirmed`, and keeps stale memories usable again by returning them to `active` when appropriate.
