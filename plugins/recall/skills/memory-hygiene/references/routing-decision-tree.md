# Routing Decision Tree

Step-by-step walkthrough for choosing the right target when `route-memory` runs on a candidate fact.

## Step 1 — Is it durable across sessions?

- No → route to `current_chat_only`. Stop.
- Yes → continue.

## Step 2 — Is it already represented in a repo file that agents read?

- README, install guide, runbook, architecture doc, changelog → route to `repo_docs`. Stop.
- `SKILL.md`, plugin manifest, hook script, MCP config → route to `skill_or_plugin_instructions`. Stop.
- `AGENTS.md`, `CLAUDE.md`, Kimi/Codex config, provider settings → route to `provider_config`. Stop.
- Otherwise → continue.

## Step 3 — Does it change durable project understanding?

- Decision, requirement, risk, constraint, verified command, architecture claim, debug lesson → route to `recall_memory`. Continue to Step 4 for lifecycle hints.
- Ephemeral status, draft plan, one-off command output → route to `current_chat_only`. Stop.

## Step 4 — Does it conflict with existing memory?

- Exact duplicate → return `merge` proposal, keep older primary.
- Near-duplicate with different provenance → return `needs_confirmation`.
- Conflicting claim key with validated winner → return `supersede` proposal.
- Conflicting claim key with only hypothesis records → return `needs_confirmation`.

## Step 5 — Does it require evidence?

- Preference claim without `--preference-key` + evidence → return `needs_confirmation`.
- Current-truth claim without `--claim-key` → require key before save.
- File-backed claim without `--source-path` → recommend source path so `refresh-source-backed` can maintain it.

## Rejection Rules

Reject candidate facts that contain:

- Secret-shaped tokens, credentials, API keys, session cookies, personal identifiers.
- Purely conversational content (greetings, small talk, apologies).
- Contradictions the agent has not verified against a source or user statement.

## Trust Signals

Prefer records with:

- Validated lifecycle over hypothesis lifecycle.
- Explicit source path over inferred origin.
- User-confirmed provenance over automatic hook capture.
- Recent trust promotion over cold historical write.
