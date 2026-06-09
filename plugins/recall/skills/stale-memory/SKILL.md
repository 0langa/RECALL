---
name: stale-memory
description: Use when a RECALL memory may be outdated but should remain available below active memories.
---

# Stale Memory

Use this skill when a memory is probably outdated, uncertain, or lower priority, but should not be archived or superseded yet.

RECALL is local-only project memory. Update metadata under the active project's `.codex_memory/` directory and never require hosted services or external APIs. Do not put secrets, credentials, tokens, private keys, passwords, or sensitive personal data in notes.

## Execution Path

Use the public RECALL adapter:

```bash
python ./scripts/recall_skill.py stale-memory <id> --note "<short reason>"
```

Use `recall_skill.py` only. Treat lower-level backend scripts as internal support code.

## Workflow

1. Use `review-memory` or `retrieve-memory` to find the memory ID.
2. Prefer `supersede-memory` when a newer replacement memory exists.
3. Prefer `resolve-memory` when the memory represents completed work.
4. Use stale when the memory should remain visible but rank lower than active/open memory.

## Example

```bash
python ./scripts/recall_skill.py stale-memory 22 --note "Hook strategy changed after Stop finalizer implementation."
```

The adapter sets status `stale`, records `stale_at`, and stores the lifecycle note.
