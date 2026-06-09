---
name: repair-memory
description: Use when RECALL doctor reports repairable local memory or index problems.
---

# Repair Memory

Use this skill when `doctor-memory` reports a repairable local RECALL problem, such as an incomplete rebuildable index.

RECALL is local-only project memory. Repair files under the active project's `.codex_memory/` directory and never require hosted services or external APIs. Do not store or print secrets, credentials, tokens, private keys, passwords, or sensitive personal data.

## Execution Path

Use the public RECALL adapter:

```bash
python ./scripts/recall_skill.py repair
```

Use `recall_skill.py` only. Treat lower-level backend scripts as internal support code.

## Workflow

1. Run `doctor-memory` first unless the user explicitly asks for immediate repair.
2. Confirm the report describes a repairable condition.
3. Run:

```bash
python ./scripts/recall_skill.py repair
```

4. Run `doctor-memory` again if the user needs proof of health.

## Result

The adapter performs safe local repairs, such as rebuilding the index from durable storage. Storage remains the source of truth.
