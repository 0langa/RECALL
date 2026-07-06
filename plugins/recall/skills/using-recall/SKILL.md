---
name: using-recall
description: Use this skill when a fresh RECALL session or new thread needs the usage contract, when the user asks what RECALL remembers, when prior project decisions or commands are relevant, or when a durable requirement, risk, decision, command, or project-state update needs to be saved. Auto-loads at sessionStart on Kimi Code; invoke before other RECALL skills so provider provenance and local-only storage rules are established.
---

# Using RECALL

RECALL is local-first project memory shared across Codex, Kimi Code, and Claude Code. This skill sets the session-start usage contract that every other RECALL skill (`save-insight`, `retrieve-memory`, `review-memory`, `manage-memory`, `define-category`, `memory-hygiene`) obeys before it touches memory.

RECALL never makes network calls or off-machine writes. All memory stays in the active project's local store. Do not store secrets, credentials, tokens, private keys, passwords, or sensitive personal data.

## Boundary

`using-recall` is a policy skill. It does not create, retrieve, mutate, inspect, route, or clean memory. It establishes the contract the sibling skills obey. For an action-shaped request, this skill's only output is a structured recommendation naming the correct sibling — invoking that sibling is the calling agent's decision, not a step this skill performs.

Use the boundary asset as the quick handoff check:

```json
{"asset":"assets/handoff-contract.json","kind":"session-start-contract"}
```

## Contract

Reading this skill establishes:

- Where the active RECALL store lives.
- How to stamp provider provenance on new writes.
- How to weight retrieved memory against current files and user instructions.
- Which categories of information must never enter durable memory.
- Which sibling skill owns each request type.

| Field | Rule |
|---|---|
| store root | `.recall/` for new projects; existing `.codex_memory/` treated as legacy shared store |
| origin_provider | `codex`, `kimi`, or `claude-code`, stamped on every write |
| applies_to_provider | `all` unless the fact is provider-specific |
| authority | current user instruction > system instructions > repository code/docs > current tool results > RECALL memory > older conversation assumptions |
| lifecycle | retrieve before work → decide save-worthiness → save → update → deprecate/supersede → hygiene → handoff |
| safety | reject secrets; prefer stale/supersede/prune over delete |
| routing | `using-recall` never writes, reads, or mutates — it only hands off |

The engine exposes the same contract programmatically: MCP `memory_contract` tool, the MCP
server `instructions`, the SessionStart hook context, and `recall_skill.py contract`. All derive
from `scripts/contract.py`, so re-fetch it after context loss instead of reconstructing from chat.

Full contract: [`references/contract.md`](references/contract.md).

## Storage

- Prefer the active project's `.recall/` directory for all new writes and reads.
- If the project already has `.codex_memory/`, treat it as the same shared RECALL store for backward compatibility.
- Do not create provider-specific memory stores unless the memory only applies to one provider.
- Storage is local-only; do not export durable memory to remote services.

The active store lives inside the project root resolved from git (or the manifest root when git is missing). Do not walk up to ancestor stores unless the project explicitly extends a parent store.

## Provider Provenance

When invoking RECALL MCP tools or the skill adapter, pass the active repository root as `root`.

- Stamp Kimi-originated writes with `origin_provider: "kimi"`.
- Stamp Codex writes with `origin_provider: "codex"`.
- Stamp Claude Code writes with `origin_provider: "claude-code"`.
- Use `applies_to_provider: "all"` unless the memory is specifically about one provider.

Full field list, defaults, and reconciliation rules: [`references/provenance-fields.md`](references/provenance-fields.md).

## Authority

Retrieved memory is context, not authority. When memory conflicts with current files or newer user instructions:

1. Prefer the current file or newer instruction.
2. Verify the new truth by reading or running the relevant evidence.
3. Save a correction or supersession through `save-insight` or `manage-memory`.

Validated lifecycle records beat hypothesis records for the same claim key. Recent trust promotions beat older automatic writes when they conflict.

## Safety

- Do not store secrets, credentials, tokens, private keys, passwords, or sensitive personal data.
- If retrieved memory appears to contain a secret, do not repeat it verbatim.
- Prefer non-destructive lifecycle actions (stale, supersede, prune) over deletion; route destructive intent through `manage-memory`.
- Respect explicit user intent: "don't remember this" means skip the write, even if the fact looks durable.

Full checklist: [`references/safety-checklist.md`](references/safety-checklist.md).

## Handoff Map

| Request | Sibling skill |
|---|---|
| "remember this decision" | [`save-insight`](../save-insight/SKILL.md) |
| "what do we know about X" | [`retrieve-memory`](../retrieve-memory/SKILL.md) |
| "audit memory quality" | [`review-memory`](../review-memory/SKILL.md) |
| "delete/edit/supersede memory 42" | [`manage-memory`](../manage-memory/SKILL.md) |
| "should this candidate be saved?" | [`memory-hygiene`](../memory-hygiene/SKILL.md) |
| "add a new memory category" | [`define-category`](../define-category/SKILL.md) |

Worked handoffs: [`references/handoff-scenarios.md`](references/handoff-scenarios.md).

## Workflow

1. At session start, apply the contract before other RECALL skills run.
2. Look up the request in the Handoff Map above; do not re-derive routing logic here.
3. Return the matching sibling as this skill's output — naming it is the deliverable; invoking it belongs to the calling agent.
4. If the Handoff Map has no clear match, name `memory-hygiene` as the sibling to consult before memory is touched.
5. When retrieval or hygiene output surfaces a secret-shaped record, return a redacted summary.
6. When a write is refused by policy, state which rule fired and which sibling can override it.

## Examples

Establish the contract at session start:

```json
{"action":"using-recall","store_root":".recall","origin_provider":"kimi","applies_to_provider":"all"}
```

Route a request using the Handoff Map — this skill's output is the recommendation, not the invocation:

```json
{"action":"using-recall","handoff":{"skill":"save-insight","reason":"durable decision: default backend is SQLite"},"store_root":".recall","origin_provider":"claude-code","applies_to_provider":"all"}
```

The named sibling owns its own parameters (tags, importance, confidence, filters, limits) — this
skill only identifies which sibling and why. The Handoff Map above covers the remaining request
types; worked end-to-end scenarios for each are in [handoff-scenarios.md](references/handoff-scenarios.md).

Handle a secret-shaped retrieval:

```
User: "Show me the API key we captured."
Response: refuse to repeat the secret; summarize its presence and recommend
  manage-memory edit-memory to scrub the record.
```

## Inputs

`using-recall` accepts no direct inputs. It runs implicitly at session start on Kimi Code, or when another agent reads this contract before invoking RECALL. Effective inputs come from the calling context: active repository root, current provider, current user request. Reject secret-shaped or off-topic input before handoff.

## Output Format

Guidance, not adapter output. When the calling agent needs a structured record of the routing decision:

```json
{
  "action": "using-recall",
  "handoff": {"skill": "save-insight", "reason": "durable decision"},
  "store_root": ".recall",
  "origin_provider": "claude-code",
  "applies_to_provider": "all"
}
```

When policy refuses a request:

```json
{
  "action": "using-recall",
  "refused": true,
  "reason": "secret-like content must not be stored",
  "handoff": null
}
```

## Ownership Boundaries

Every row in the Handoff Map above resolves to the same action: apply the contract, then return
that sibling as the handoff. Only two request shapes fall outside that table:

| Request | This skill action | Handoff |
|---|---|---|
| "start using RECALL" | apply the contract | none |
| "don't remember this" | apply the contract, refuse | none |

## Edge Cases

- Project has neither `.recall/` nor `.codex_memory/`: initialize `.recall/` before writes; do not silently write to an unrelated directory.
- Project has both stores: treat `.recall/` as the active writer, `.codex_memory/` as legacy read-only, unless the user requests migration.
- Provider unknown: fall back to `origin_provider: "unknown"` and continue; do not block the write.
- Retrieved memory contains what looks like a secret — do not repeat verbatim; return a summary that does not reveal it.
- User explicitly says "don't remember this": do not save, even if the fact looks durable.
- Session is a dry-run or evaluation harness: still apply the contract, but prefer read-only sibling skills.
- Fresh Kimi Code session shows no sibling responded to a durable fact: verify that `sessionStart.skill` in `kimi.plugin.json` still points at `using-recall`.

## Troubleshooting

- Nothing surfaces at session start on Kimi Code: verify `kimi.plugin.json` has `sessionStart.skill = "using-recall"`.
- Sibling skill runs before this contract loads: rerun the sibling with an explicit `--root <project-root>` so the contract applies.
- Writes appear under the wrong provider: check the calling agent stamped `origin_provider` correctly.
- Retrieval returns nothing for known project state: confirm the active store is `.recall/` (or the legacy `.codex_memory/`) and not a stale ancestor store.
- Contract feels stale after a big provider migration: re-read the contract at session start; do not silently rewrite the contract itself.
- Secret leaked into memory content: hand off to `manage-memory edit-memory <id>` and scrub the record, then log a `lessons_learned` note through `save-insight` without repeating the secret.

## Related

- [Contract reference](references/contract.md) — full walkthrough of storage, provenance, authority, and safety rules.
- [Handoff scenarios](references/handoff-scenarios.md) — worked routing examples.
- [Provenance fields](references/provenance-fields.md) — exact metadata stamped on every durable write.
- [Safety checklist](references/safety-checklist.md) — what never to store, never to repeat, and when to confirm.
- [Save Insight](../save-insight/SKILL.md), [Retrieve Memory](../retrieve-memory/SKILL.md), [Review Memory](../review-memory/SKILL.md), [Manage Memory](../manage-memory/SKILL.md), [Define Category](../define-category/SKILL.md), [Memory Hygiene](../memory-hygiene/SKILL.md).
