# RECALL Usage Contract

Deep reference for the session-start rules loaded by `using-recall`.

## Store Discovery

RECALL resolves the active store in this order:

1. `.recall/` inside the git or manifest root of the active project.
2. Existing `.codex_memory/` in the same root (legacy shared layout).
3. Ancestor directories only when the project explicitly extends a parent store.

Do not fabricate stores in unrelated directories. If both `.recall/` and `.codex_memory/` exist, treat `.recall/` as the current writer and `.codex_memory/` as read-only legacy history unless the user requests migration.

## Provider Provenance Fields

Every durable write carries:

- `origin_provider`: which client wrote the memory (`codex`, `kimi`, `claude-code`).
- `origin_agent`: the agent identifier when known.
- `session_id`, `turn_id`: capture identity for replay.
- `workspace`, `branch`, `commit`: repository state at capture.
- `capture_channel`: `hook`, `mcp`, `skill_adapter`, or `manual`.
- `applies_to_provider`: `all` unless the fact is provider-specific.

## Retrieval Authority

- Current files > user instructions > retrieved memory.
- Validated lifecycle beats hypothesis lifecycle for the same claim key.
- Recent trust promotions beat older automatic writes when they conflict.

## Save vs Skip

Save when a fact is:

- durable across sessions,
- not better represented in a repo doc or SKILL.md,
- verifiable from source, evidence, or a user decision.

Skip when a fact is:

- transient (draft, one-off command, active scratch),
- already documented in the repository,
- a secret or credential.

## Lifecycle Preference

Prefer these actions before deletion:

- `stale` when source evidence changed.
- `supersede` when a validated claim clearly wins.
- `merge` when duplicates share provenance.
- `prune` (archive) for low-value automatic noise.

Use `manage-memory delete-memory --confirm DELETE-<id>` only when the user explicitly asked to remove memory.

## Related Skills

- `save-insight` — write durable facts.
- `retrieve-memory` — targeted lookup.
- `review-memory` — inspection.
- `manage-memory` — lifecycle mutation.
- `define-category` — taxonomy.
- `memory-hygiene` — routing and safe cleanup.
