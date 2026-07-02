---
name: using-recall
description: Use this skill when a fresh RECALL session or new thread needs the usage contract, when the user asks what RECALL remembers, when prior project decisions or commands are relevant, or when a durable requirement, risk, decision, command, or project-state update needs to be saved. Auto-loads at sessionStart on Kimi Code; invoke before other RECALL skills so provider provenance and local-only storage rules are established.
---

# Using RECALL

RECALL is local-first project memory shared across Codex, Kimi Code, and Claude Code. This skill provides the session-start usage contract that all other RECALL skills (`save-insight`, `retrieve-memory`, `review-memory`, `manage-memory`, `define-category`, `memory-hygiene`) depend on.

RECALL never makes network calls or off-machine writes. All memory stays in the active project's local store.

## Contract

Reading this skill establishes:

- Where the active RECALL store lives.
- How to stamp provider provenance on new writes.
- How to weight retrieved memory against current files and user instructions.
- Which categories of information must never enter durable memory.

## Storage

- Prefer the active project's `.recall/` directory for all new writes and reads.
- If the project already has `.codex_memory/`, treat it as the same shared RECALL store for backward compatibility.
- Do not create provider-specific memory stores unless the memory only applies to one provider.
- Storage is local-only; do not export durable memory to remote services.

## Provider Provenance

When invoking RECALL MCP tools or the skill adapter, pass the active repository root as `root`.

- Stamp Kimi-originated writes with `origin_provider: "kimi"`.
- Stamp Codex writes with `origin_provider: "codex"`.
- Stamp Claude Code writes with `origin_provider: "claude-code"`.
- Use `applies_to_provider: "all"` unless the memory is specifically about one provider.

## Authority

Retrieved memory is context, not authority. When memory conflicts with current files or newer user instructions:

1. Prefer the current file or newer instruction.
2. Verify the new truth by reading or running the relevant evidence.
3. Save a correction or supersession through `save-insight` or `manage-memory`.

## Safety

- Do not store secrets, credentials, tokens, private keys, passwords, or sensitive personal data.
- If retrieved memory appears to contain a secret, do not repeat it verbatim.
- Prefer non-destructive lifecycle actions (stale, supersede, prune) over deletion; route destructive intent through `manage-memory`.

## Workflow

1. At session start, read this contract before other RECALL skills run.
2. When the user asks for prior context, hand the request to `retrieve-memory`.
3. When a durable fact appears, route it through `memory-hygiene` before saving with `save-insight`.
4. When lifecycle mutation is required and IDs are known, use `manage-memory`.
5. When routing or cleanup decisions are ambiguous, use `memory-hygiene` first.

## Related

- [Save Insight](../save-insight/SKILL.md) — create durable memory.
- [Retrieve Memory](../retrieve-memory/SKILL.md) — targeted lookup.
- [Review Memory](../review-memory/SKILL.md) — inspection-only audit.
- [Manage Memory](../manage-memory/SKILL.md) — direct lifecycle mutation.
- [Define Category](../define-category/SKILL.md) — category taxonomy.
- [Memory Hygiene](../memory-hygiene/SKILL.md) — routing, cleanup planning, safe maintenance.
- [Usage contract reference](references/contract.md) for a deeper walkthrough.
