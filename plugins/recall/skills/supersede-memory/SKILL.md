---
name: supersede-memory
description: Use when a newer RECALL memory replaces an older memory and both IDs are known.
---

# Supersede Memory

Use this skill when an older memory is wrong, incomplete, or outdated and a newer memory should become the authoritative replacement.

RECALL is local-only project memory. Update metadata under the active project's `.codex_memory/` directory and never require hosted services or external APIs. Do not put secrets, credentials, tokens, private keys, passwords, or sensitive personal data in notes.

## Execution Path

Use the public RECALL adapter:

```bash
python ./scripts/recall_skill.py supersede-memory <old-id> <new-id> --note "<short reason>"
```

Use `recall_skill.py` only. Treat lower-level backend scripts as internal support code.

## Workflow

1. Use `review-memory` or `retrieve-memory` to identify both records.
2. Confirm that the new memory actually replaces the old memory.
3. If no replacement exists, save the replacement with `save-insight` or `save-turn-card` first.
4. Run:

```bash
python ./scripts/recall_skill.py supersede-memory 12 31 --note "Memory #31 reflects the documented Stop finalizer design."
```

## Result

The old memory gets status `superseded` and `superseded_by`. The new memory gets `supersedes` and `last_confirmed`.
