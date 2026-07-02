# Handoff Scenarios

Worked examples of `using-recall` routing user requests to the correct sibling RECALL skill.

Each scenario shows the user request, the contract fields `using-recall` applies, and the exact sibling handoff that follows. All examples stay local-only; no secrets are stored or repeated.

## Scenario 1 — Session start on a fresh project

- Trigger: `sessionStart` on Kimi Code, or first RECALL invocation on Codex/Claude Code.
- Contract fields: `store_root = .recall`, `origin_provider = <active provider>`, `applies_to_provider = all`.
- Handoff: none. Wait for a real request.

## Scenario 2 — "Remember that we chose PostgreSQL"

- Contract fields: durable decision; not a secret.
- Handoff: `save-insight decisions "Chose PostgreSQL for durable storage." --summary "PostgreSQL is the durable backend." --tag decision --source skill --status active --importance 0.8 --confidence 0.9`.
- Follow-up: none.

## Scenario 3 — "What do we know about the release process?"

- Contract fields: retrieval, not mutation.
- Handoff: `retrieve-memory "release process" --summary`.
- Follow-up: summarize returned records; if none, say so and offer to save.

## Scenario 4 — "Some memories look stale after we deleted the old docs"

- Contract fields: cleanup, not deletion.
- Handoff: `memory-hygiene hygiene-scan --limit 100` then `hygiene-plan --scope project` then `hygiene-apply --safe`.
- Follow-up: escalate destructive items to `manage-memory`.

## Scenario 5 — "Delete memory 42"

- Contract fields: explicit destructive mutation with a known ID.
- Handoff: `manage-memory delete-memory 42 --confirm DELETE-42`.
- Follow-up: confirm outcome; do not remove associated history metadata.

## Scenario 6 — "Add a new category for eval runs"

- Contract fields: taxonomy.
- Handoff: `define-category eval_runs --weight 1.0 --description "Structured eval run outputs."`.
- Follow-up: recommend routing eval outputs through the new category via `save-insight`.

## Scenario 7 — "Show me current memory noise"

- Contract fields: inspection, no mutation.
- Handoff: `review-memory --limit 20` or `audit-memory --limit 20`.
- Follow-up: propose cleanup through `memory-hygiene`, not from `review-memory`.

## Scenario 8 — Retrieved memory contains a secret-shaped token

- Contract fields: safety.
- Handoff: no adapter call; return a redacted summary and recommend `manage-memory edit-memory` to scrub the record.
- Follow-up: log the incident under `lessons_learned` without repeating the secret.

## Scenario 9 — Memory conflicts with the current file

- Contract fields: authority.
- Handoff: prefer the current file, then `save-insight` with a `--claim-key` matching the conflicting record.
- Follow-up: `manage-memory` or `memory-hygiene reconcile-current-truth` resolves the mutually exclusive claim.

## Scenario 10 — User says "don't remember this"

- Contract fields: safety and user intent.
- Handoff: none. Reject the write. Do not persist even if the fact looks durable.
