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

## Safe Automatic Changes

Safe apply may:

- mark missing/changed source-backed records `stale`
- archive low-value automatic command noise
- merge exact duplicates into the oldest/current primary
- supersede losing current-truth claims only when a validated/high-trust winner exists
- mark weak preference records `needs_confirmation`
- refresh source-backed metadata when the file still matches

Safe apply must not:

- delete memory
- edit record content to rewrite history
- merge near-duplicates
- choose between ambiguous current truths
- promote a preference without evidence

## Evidence Strength

Prefer current repository files and explicit current user instructions over old memory. Preserve old memory by changing lifecycle status, not by erasing history.

Source-backed memory is current when the source path exists and the stored hash matches. Missing or changed source files are stale candidates.

Preference memory should stay active only when it has durable evidence, normally a `preference_key`, `preference_evidence_type`, and `decision_id`.
