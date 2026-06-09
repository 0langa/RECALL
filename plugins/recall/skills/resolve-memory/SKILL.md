---
name: resolve-memory
description: Use when an open RECALL task, risk, issue, or temporary memory has been completed or no longer needs active attention.
---

# Resolve Memory

Use this skill when an existing RECALL memory describes an open item that has been handled.

RECALL is local-only project memory. Update metadata under the active project's `.codex_memory/` directory and never require hosted services or external APIs. Do not put secrets, credentials, tokens, private keys, passwords, or sensitive personal data in notes.

## Execution Path

Use the public RECALL adapter:

```bash
python ./scripts/recall_skill.py resolve-memory <id> --note "<short reason>"
```

Use `recall_skill.py` only. Treat lower-level backend scripts as internal support code.

## Workflow

1. Find the relevant memory with `review-memory` or `retrieve-memory`.
2. Verify that the item is actually resolved.
3. Write a short note that explains the evidence or outcome.
4. Run:

```bash
python ./scripts/recall_skill.py resolve-memory 18 --note "Implemented in commit 19c8129 and verified by unit tests."
```

## Result

The adapter sets status `resolved`, records `resolved_at`, and stores the lifecycle note.
