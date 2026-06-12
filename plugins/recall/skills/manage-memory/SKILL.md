---
name: manage-memory
description: Use when user needs capture-mode changes, cleanup, repair, or lifecycle changes for existing RECALL memories.
---

# Manage Memory

Use this skill for RECALL maintenance and lifecycle control. RECALL is local-only project memory. Work only in active project's `.codex_memory/`. Do not store or repeat secrets.

Use `recall_skill.py` only:

```bash
python ./scripts/recall_skill.py configure-capture minimal
python ./scripts/recall_skill.py archive-noise
python ./scripts/recall_skill.py doctor
python ./scripts/recall_skill.py repair
python ./scripts/recall_skill.py confirm-memory 12
python ./scripts/recall_skill.py resolve-memory 12 --note "Implemented."
python ./scripts/recall_skill.py stale-memory 12 --note "Needs reconfirmation."
python ./scripts/recall_skill.py supersede-memory 12 18 --note "Memory #18 replaces #12."
python ./scripts/recall_skill.py merge-memories 18 19 20 --note "Merged duplicates."
python ./scripts/recall_skill.py prune-memory 12 --note "Archive after review."
python ./scripts/recall_skill.py edit-memory 12 --summary "Corrected summary."
python ./scripts/recall_skill.py delete-memory 12 --confirm DELETE-12
```

Workflow:

1. Start with `review-memory` or `retrieve-memory` if IDs or current state are unclear.
2. Use `configure-capture manual|minimal|standard|off` to control automatic hook writes.
3. Use `archive-noise` for non-destructive cleanup of low-value automatic command history.
4. Use lifecycle commands to confirm, resolve, mark stale, supersede, merge, or prune memory.
5. Use `doctor` and `repair` only for local storage or index maintenance.
6. Use `delete-memory` only with explicit user intent. Prefer archival over deletion.
