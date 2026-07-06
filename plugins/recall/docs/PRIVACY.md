# RECALL Privacy

RECALL is local-first project memory for Codex, Kimi Code, and Claude Code.

## Data Storage

RECALL stores runtime memory data in the active project's `.recall/` directory. Projects that only have an older `.codex_memory/` store can continue using that legacy store for backward compatibility. The default backend is SQLite, with JSONL available through local config.

RECALL does not require hosted services, remote APIs, external databases, model downloads, or cloud storage for its V1 behavior.

## Data Sent By RECALL

RECALL does not intentionally send stored memories, prompts, command summaries, or project data to any RECALL-operated service. The plugin has no RECALL backend service.

Codex itself may process conversation and tool context according to the user's Codex/OpenAI settings and workspace policies. RECALL's local files should be treated as project data.

## Hooks

RECALL bundles Codex lifecycle hooks. These hooks run locally after the user reviews and trusts them in Codex. Hook outputs are compact summaries intended to help future Codex sessions recover relevant project context.

## Sensitive Data

Do not store credentials, tokens, private keys, passwords, or sensitive personal data in RECALL. The backend redacts common secret-like patterns before storage, but redaction is a safety net rather than a guarantee.

## Deletion

Delete the active project's `.recall/` directory to remove current RECALL runtime data. If the project still uses a legacy `.codex_memory/` store, delete that legacy directory too.
