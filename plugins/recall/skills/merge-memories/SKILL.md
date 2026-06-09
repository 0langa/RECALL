---
name: merge-memories
description: Use when duplicate or overlapping RECALL memories should be consolidated under one primary memory.
---

# Merge Memories

Use this skill when several memories say the same thing and one record should remain primary.

RECALL is local-only project memory. Update metadata under the active project's `.codex_memory/` directory and never require hosted services or external APIs. Do not put secrets, credentials, tokens, private keys, passwords, or sensitive personal data in notes.

## Execution Path

Use the public RECALL adapter:

```bash
python ./scripts/recall_skill.py merge-memories <primary-id> <secondary-id> [secondary-id ...] --note "<short reason>"
```

Use `recall_skill.py` only. Treat lower-level backend scripts as internal support code.

## Workflow

1. Use `review-memory` to list candidate duplicates and their IDs.
2. Choose the clearest, most current memory as the primary.
3. Merge secondary memories only when they are redundant or less useful than the primary.
4. Run:

```bash
python ./scripts/recall_skill.py merge-memories 31 12 18 --note "Consolidated duplicate hook-finalizer memories."
```

## Result

The primary memory gets `merged_from`, `related_to`, and `last_confirmed`. Secondary memories are marked `superseded` with `superseded_by` pointing to the primary.
