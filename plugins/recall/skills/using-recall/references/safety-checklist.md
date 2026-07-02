# Safety Checklist

Apply this checklist before any RECALL write. It supplements the contract loaded by `using-recall` at session start.

## Never store

- Secrets, credentials, tokens, private keys, passwords.
- Session cookies, bearer tokens, API keys, service-account JSON.
- Personal identifiers of third parties (email, phone, address) without explicit user approval.
- Full request bodies containing user data that should stay local to the current turn.

## Never repeat

- Redact any secret-shaped content before echoing back into chat.
- Do not paste a memory's content back into commit messages, PR descriptions, or public logs.
- When retrieval returns a record whose content looks like a secret, return a summary that omits the secret.

## Always confirm

- User says "don't remember this" → skip the write, even if the fact looks durable.
- User says "forget X" → hand off to `manage-memory delete-memory <id> --confirm DELETE-<id>` after verifying the ID.
- Destructive lifecycle actions (delete, purge) require an explicit confirmation token.

## Prefer non-destructive lifecycle

Before deleting, consider:

- `stale` — source evidence changed.
- `supersede` — a validated claim clearly wins.
- `merge` — exact duplicate joins an older primary.
- `prune` — archive low-value noise.
- `needs_confirmation` — demote weak preferences.

Only escalate to `delete-memory` when the user asked to remove memory content permanently, and the ID is known.

## Provider crossover

- Kimi Code writes should be readable by Codex and Claude Code unless `applies_to_provider` says otherwise.
- Provider-specific facts (e.g. Codex-only CLI flags) must set `applies_to_provider` to that provider.
- Do not fork durable memory into provider-specific stores.
