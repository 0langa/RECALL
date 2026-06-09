---
name: edit-memory
description: Use when the user wants to correct an existing RECALL memory's content, category, or metadata.
---

# Edit Memory

Use this skill when an existing memory is useful but needs correction. Prefer `supersede-memory` when the old memory should remain as historical context and a newer memory should replace it.

RECALL is local-only project memory. Update records under the active project's `.codex_memory/` directory and never require hosted services or external APIs. Do not add secrets, credentials, tokens, private keys, passwords, or sensitive personal data.

## Execution Path

Use the public RECALL adapter:

```bash
python ./scripts/recall_skill.py edit-memory <id> --content "<corrected memory>" --summary "<summary>"
```

Use `recall_skill.py` only. Treat lower-level backend scripts as internal support code.

## Workflow

1. Use `review-memory` or `retrieve-memory` to find the memory ID.
2. Confirm this is a correction, not a supersession or merge.
3. Provide only the fields that should change.
4. Run:

```bash
python ./scripts/recall_skill.py edit-memory 31 --content "Use structured memory cards." --summary "Structured cards are preferred." --tag memory-quality --status active
```

## Notes

The adapter preserves the memory ID and timestamp, updates `edited_at`, refreshes metadata fields, and rebuilds the local index so retrieval uses the corrected content.
