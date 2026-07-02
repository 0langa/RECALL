# Provenance Fields

Every durable write through the RECALL adapter carries provenance metadata so future retrieval, hygiene, and reconciliation can trace a record back to its origin.

## Required fields

| Field | Meaning |
|---|---|
| `origin_provider` | `codex`, `kimi`, or `claude-code` — which agent client wrote the memory. |
| `origin_agent` | Free-form agent identifier when known (e.g. `codex-cli`, `claude-code`, `kimi-code`). |
| `session_id` | Capture identity for replay and idempotency. |
| `turn_id` | Turn identifier inside the session. |
| `workspace` | Absolute path or slug for the active project root. |
| `branch` | Current git branch at capture time. |
| `commit` | Current git commit SHA at capture time. |
| `capture_channel` | `hook`, `mcp`, `skill_adapter`, or `manual`. |
| `applies_to_provider` | `all` unless the fact is provider-specific. |

## When any field is unknown

- Missing `origin_agent`: continue; write is still saved.
- Missing `session_id` or `turn_id`: adapter generates a placeholder; hooks fill in during the finalizer batch.
- Missing `branch` or `commit`: write is saved without the git snapshot; hygiene will refresh once reconciled.
- Missing `capture_channel`: default to `skill_adapter` when invoked through the public adapter.

## Reconciliation hooks

`memory-hygiene reconcile-current-truth` uses provenance to pick a winner between conflicting claim-key records. Prefer:

1. Records with `lifecycle: validated`.
2. Records with recent `last_confirmed` timestamps.
3. Records with explicit `source_path` matched by `refresh-source-backed`.
4. Records with `capture_channel: manual` over `capture_channel: hook`.

## Redaction

Provenance metadata is subject to the same secret redaction as memory content. Do not stuff API tokens or session cookies into `origin_agent` or `workspace`; they will be redacted before persistence.
