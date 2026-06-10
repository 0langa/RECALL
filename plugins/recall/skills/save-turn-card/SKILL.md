---
name: save-turn-card
description: Use when a RECALL Stop-hook finalizer pass must save schema-validated turn memory cards.
---

# Save Turn Card

Use this skill only when a RECALL finalizer request asks for a memory-finalization pass. It is the structured write path for end-of-turn memory created from buffered evidence.

RECALL is local-only project memory. Store data under the active project's `.codex_memory/` directory and never require hosted services or external APIs. Do not store secrets, credentials, tokens, private keys, passwords, or sensitive personal data.

## Execution Path

Use the public RECALL adapter:

```bash
python ./scripts/recall_skill.py save-turn-card --file <turn-card.json>
python ./scripts/recall_skill.py save-turn-card --stdin
```

Use `recall_skill.py` only. Treat lower-level backend scripts as internal support code.

## Workflow

1. Read the inline `PACKET=` JSON from the `RECALL_FINALIZER_REQUEST`; use its `packet_path` only as fallback evidence.
2. Review the packet's `candidate_summary`, `policy`, and adapter path.
3. Retrieve or review existing memory before writing a new card when duplicates are plausible.
4. Create at most the packet's `max_new_cards`.
5. Use lifecycle commands instead of creating duplicates when an existing memory should be confirmed, resolved, marked stale, superseded, merged, or archived.
6. Store nothing if the turn has no durable future value.

## Card JSON

Required fields:

```json
{
  "category": "decisions",
  "content": "Use Stop finalizer continuation for RECALL turn memory.",
  "summary": "Stop finalizer continuation is the memory write boundary."
}
```

Recommended fields:

```json
{
  "details": "PostToolUse buffers evidence; Stop requests one finalizer continuation.",
  "tags": ["finalizer", "hooks"],
  "source": "finalizer",
  "status": "active",
  "importance": 0.8,
  "confidence": 0.9,
  "capture_reason": "durable_turn_outcome",
  "session_id": "session-id",
  "turn_id": "turn-id",
  "evidence_ids": ["event-1"]
}
```

## Example

```bash
python ./scripts/recall_skill.py save-turn-card --stdin
```

Then provide a JSON object on stdin. The adapter validates required fields, rejects secret-like text, and stores metadata with schema `recall.turn_card.v1`.
