# Memory Hygiene Policy

Use this reference when `memory-hygiene` needs to decide where information belongs or whether cleanup is safe.

## Routing

Route to Recall only when a fact should help future agents across sessions and is not already better represented in source files.

- Recall memory: decisions, requirements, risks, commands, debug history, project state, architecture, lessons, constraints.
- Repo docs: README, install guides, release notes, runbooks, architecture docs, checklists.
- Skill/plugin instructions: `SKILL.md`, plugin manifests, hooks, MCP/server instructions, examples that change agent behavior.
- Provider config: `AGENTS.md`, `CLAUDE.md`, Kimi/Codex settings, provider-specific env/config snippets.
- Current chat only: draft plans, temporary choices, one-off commands, active scratch work, user says not to remember.

## Planning

Every plan item should include:

- memory ID
- proposed action
- confidence
- reason
- `safe_to_apply`
- related IDs when relevant
- follow-up when human confirmation is needed

Plans also carry `plan_version`, `store_identity`, `snapshot_identity`, and `plan_id`.
Each proposal carries `operation_id`, exact record `preconditions`, and source-file
preconditions when relevant. `operations` is the selected safe subset of the visible
`proposals`. Save the entire plan, review it, then pass that plan to apply.

`scan_limit`, `output_limit`, and `action_limit` are separate. Hidden proposals never
become saved operations. Apply can further reduce the operation count, but cannot
reorder operations, fill a skip, or make a new plan. Record-state checks and mutations
share the store transaction or JSONL exclusion. JSONL does not promise multi-file rollback.

Secret repair has first priority inside the scanned records. Unscanned secret status is
unknown. A card can participate in only one selected lifecycle operation, including a
merge primary. Omitted collisions and limit exclusions remain visible in the report.

## Safe Automatic Changes

Safe apply may:

- mark missing/changed source-backed records `stale`
- archive low-value automatic command noise
- redact legacy secret-shaped content, invalidate prior verification, and clear obsolete claims
- merge exact duplicates into the oldest/current primary
- mark weak preference records `needs_confirmation`
- refresh source-backed metadata when the file still matches

Safe apply must not:

- delete memory
- edit record content to rewrite history
- merge near-duplicates
- choose between conflicting current truths without independent current evidence
- promote a preference without evidence
- archive questions, uncertainty, one-time task requests, or raw failure history based on a semantic guess

`review_noise` and `review_failure_history` surface bounded lexical candidates for
review. Failure logs stay active. These rules do not establish broad semantic truth.

## Evidence Strength

Prefer current repository files and explicit current user instructions over old memory. Preserve old memory by changing lifecycle status, not by erasing history.

Status, confidence, age, and record ID do not independently verify a claim. Report every
conflicting claim slot as `review_claim_conflict` with `resolution=review_required`. After an
agent or user checks current evidence, use explicit supersession with the reason recorded.

Source-backed memory is current when the source path exists and the stored hash matches. Missing or changed source files are stale candidates.

Preference memory should stay active only when it has durable evidence, normally a `preference_key`, `preference_evidence_type`, and `decision_id`.
