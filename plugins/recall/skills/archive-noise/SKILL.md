---
name: archive-noise
description: Use when RECALL memory contains low-value automatic hook records that should be reviewed or archived without deletion.
---

# Archive Noise

Use this skill to review or archive low-value automatic RECALL memories, especially old successful `post_tool_use` command records from read-only exploration. RECALL is local-only project memory: it stores data under the active project's `.codex_memory/` directory and does not need hosted services or external APIs.

Do not archive memories that contain durable decisions, requirements, risks, debugging root causes, release milestones, or user preferences. Do not store or expose secrets, credentials, tokens, private keys, passwords, or sensitive personal data.

## Execution Path

Use the public RECALL adapter:

```bash
python ./scripts/recall_skill.py archive-noise
python ./scripts/recall_skill.py archive-noise --limit 50
python ./scripts/recall_skill.py archive-noise --apply --limit 50
```

Use `recall_skill.py` only. Treat lower-level backend scripts as internal support code.

## Workflow

1. Run without `--apply` first and review the matched memories.
2. Confirm the matches are generic automatic command noise, not durable project state.
3. Re-run with `--apply` and a bounded `--limit` to mark matching memories `archived`.
4. Run `review-memory --status archived` or retrieval checks when you need proof of the cleanup.

Archiving is non-destructive: records remain in local-only storage with lifecycle metadata and can still be inspected later.
