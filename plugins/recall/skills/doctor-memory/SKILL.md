---
name: doctor-memory
description: Use when RECALL memory storage, index health, or retrieval behavior seems broken or inconsistent.
---

# Doctor Memory

Use this skill when retrieval looks wrong, memory appears missing, the index may be stale, or the user asks for a RECALL health check.

RECALL is local-only project memory. Inspect the active project's `.codex_memory/` directory and never require hosted services or external APIs. Do not print secrets verbatim if diagnostics expose sensitive-looking content.

## Execution Path

Use the public RECALL adapter:

```bash
python ./scripts/recall_skill.py doctor
```

Use `recall_skill.py` only. Treat lower-level backend scripts as internal support code.

## Workflow

1. Run `doctor` before repair.
2. Read the JSON report and identify whether storage, config, JSONL rows, or index integrity is affected.
3. If repair is recommended and the user has asked for a fix, use `repair-memory`.
4. If doctor is clean but retrieval still seems wrong, review memory quality with `review-memory`.

## Example

```bash
python ./scripts/recall_skill.py doctor
```

Report only the relevant health fields and any recommended next action.
