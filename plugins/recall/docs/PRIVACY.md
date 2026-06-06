# RECALL Privacy

RECALL is local-first project memory for Codex.

## Data Storage

RECALL stores runtime memory data in the active project's `.codex_memory/` directory. The default backend is SQLite, with JSONL available through local config.

RECALL does not require hosted services, remote APIs, external databases, model downloads, or cloud storage for its V1 behavior.

## Data Sent By RECALL

RECALL does not intentionally send stored memories, prompts, command summaries, or project data to any RECALL-operated service. The plugin has no RECALL backend service.

Codex itself may process conversation and tool context according to the user's Codex/OpenAI settings and workspace policies. RECALL's local files should be treated as project data.

## Hooks

RECALL bundles Codex lifecycle hooks. These hooks run locally after the user reviews and trusts them in Codex. Hook outputs are compact summaries intended to help future Codex sessions recover relevant project context.

## Sensitive Data

Do not store credentials, tokens, private keys, passwords, or sensitive personal data in RECALL. The backend redacts common secret-like patterns before storage, but redaction is a safety net rather than a guarantee.

## Deletion

Delete a project's `.codex_memory/` directory to remove that project's RECALL runtime data.
