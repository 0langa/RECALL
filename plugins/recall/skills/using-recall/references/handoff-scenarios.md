# Handoff Scenarios

Worked examples of `using-recall` routing user requests to the correct sibling RECALL skill.

Each scenario shows the user request, the contract fields `using-recall` applies, and the handoff
recommendation it returns — matching the `"handoff": {"skill": ..., "reason": ...}` shape in the
Output Format section of SKILL.md. The named sibling determines its own operational parameters
(tags, importance, confidence, limits, flags); `using-recall` never invents those values. All
examples stay local-only; no secrets are stored or repeated.

## Scenario 1 — Session start on a fresh project

- Trigger: `sessionStart` on Kimi Code, or first RECALL invocation on Codex/Claude Code.
- Contract fields: `store_root = .recall`, `origin_provider = <active provider>`, `applies_to_provider = all`.
- Handoff: none. Wait for a real request.

## Scenario 2 — "Remember that we chose PostgreSQL"

- Contract fields: durable decision; not a secret.
- Handoff: `{"skill": "save-insight", "reason": "durable decision: chose PostgreSQL for durable storage"}`.
- Follow-up: none.

## Scenario 3 — "What do we know about the release process?"

- Contract fields: retrieval, not mutation.
- Handoff: `{"skill": "retrieve-memory", "reason": "query: release process"}`.
- Follow-up: summarize returned records; if none, say so and offer to save.

## Scenario 4 — "Some memories look stale after we deleted the old docs"

- Contract fields: cleanup, not deletion.
- Handoff: `{"skill": "memory-hygiene", "reason": "stale-candidate scan requested"}`.
- Follow-up: escalate destructive items to `manage-memory`.

## Scenario 5 — "Delete memory 42"

- Contract fields: explicit destructive mutation with a known ID.
- Handoff: `{"skill": "manage-memory", "reason": "explicit delete request: memory 42"}`.
- Follow-up: confirm outcome; do not remove associated history metadata.

## Scenario 6 — "Add a new category for eval runs"

- Contract fields: taxonomy.
- Handoff: `{"skill": "define-category", "reason": "new retrieval lane for eval run outputs"}`.
- Follow-up: recommend routing eval outputs through the new category via `save-insight`.

## Scenario 7 — "Show me current memory noise"

- Contract fields: inspection, no mutation.
- Handoff: `{"skill": "review-memory", "reason": "quality/noise inspection requested"}`.
- Follow-up: propose cleanup through `memory-hygiene`, not from `review-memory`.

## Scenario 8 — Retrieved memory contains a secret-shaped token

- Contract fields: safety.
- Handoff: none. Return a redacted summary and recommend `manage-memory` to scrub the record.
- Follow-up: log the incident under `lessons_learned` without repeating the secret.

## Scenario 9 — Memory conflicts with the current file

- Contract fields: authority.
- Handoff: `{"skill": "save-insight", "reason": "supersede conflicting record with verified current truth"}`.
- Follow-up: `manage-memory` or `memory-hygiene` resolves the mutually exclusive claim.

## Scenario 10 — User says "don't remember this"

- Contract fields: safety and user intent.
- Handoff: none. Reject the write. Do not persist even if the fact looks durable.
