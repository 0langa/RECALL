# Audit Signals

Use this reference to interpret review output quickly.

## Healthy Signals

- active memories outnumber archived junk in the current slice
- summaries are specific instead of generic
- categories match real project concerns like requirements, risks, or architecture
- lifecycle links show superseded or related records instead of duplicated facts

## Warning Signals

- many active `post_tool_use` command memories with generic summaries
- repeated duplicates on the same requirement or decision
- stale memories with no recent confirmation
- archived memory dominating retrieval because filters were too broad

## Next Actions

- Recommend `archive-noise` for low-value automatic command clutter.
- Recommend `confirm-memory` for still-valid durable facts.
- Recommend `supersede-memory` when one newer memory clearly replaces an older one.
- Recommend `prune-memory` only after a targeted review by ID.
