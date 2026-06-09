---
name: prune-memory
description: Use when a low-value RECALL memory should be archived non-destructively.
---

# Prune Memory

Use this skill when a memory is noise, obsolete, misleading, or too low-value to stay active, but should be preserved for auditability.

RECALL is local-only project memory. Update metadata under the active project's `.codex_memory/` directory and never require hosted services or external APIs. Do not put secrets, credentials, tokens, private keys, passwords, or sensitive personal data in notes.

## Execution Path

Use the public RECALL adapter:

```bash
python ./scripts/recall_skill.py prune-memory <id> --note "<short reason>"
```

Use `recall_skill.py` only. Treat lower-level backend scripts as internal support code.

## Workflow

1. Use `review-memory` to find noisy or obsolete memory IDs.
2. Prefer `merge-memories` when the memory duplicates a better primary record.
3. Prefer `supersede-memory` when a newer replacement exists.
4. Use `prune-memory` for non-destructive archival.

## Example

```bash
python ./scripts/recall_skill.py prune-memory 44 --note "Generic post-tool-use command log with no future value."
```

The adapter sets status `archived`, records `archived_at`, and stores the lifecycle note. This is not a hard delete.
