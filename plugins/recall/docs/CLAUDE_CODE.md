# RECALL For Claude Code

RECALL's Claude Code integration uses the same memory engine as Codex and Kimi
Code. New projects write to `.recall/`; projects that already have
`.codex_memory/` keep using that legacy store so all three providers share one
memory instead of forking it.

## Plugin

The Claude Code manifest is `.claude-plugin/plugin.json`. It points at the
same `./skills/` directory used by Codex and Kimi and declares a local MCP
server named `recall`. It does **not** declare `hooks/hooks.json` explicitly
— Claude Code auto-loads `hooks/hooks.json` by convention, and declaring it
in the manifest as well fails plugin load with "Duplicate hooks file
detected". RECALL's hook schema was already written in Claude Code's native
format (`SessionStart` / `UserPromptSubmit` / `PostToolUse` / `PreCompact` /
`Stop`, each a `matcher` + `hooks` array of `type: "command"` entries), so it
loads automatically with no changes.

Install from a local checkout with a local marketplace (`.claude-plugin/marketplace.json`
next to `plugin.json`, already included):

```text
claude plugin marketplace add <path-to-RECALL>/plugins/recall
claude plugin install recall@recall-local
```

No values in `plugin.json`, `hooks/hooks.json`, or any `scripts/*.py` file
were changed to add this — the Codex and Kimi manifests and hook trust flow
are untouched.

## MCP Tools

The MCP server (`scripts/kimi_mcp_server.py`) is a thin, provider-agnostic
stdio JSON-RPC adapter over the RECALL core (`memory_manager.py`,
`services/*`). It is reused as-is for Claude Code — no new server was written.
It exposes:

- `retrieve_memory` — retrieval with per-result health flags and a `health` summary
- `context_packet` — token-budgeted context for session starts
- `save_insight` — durable writes with secret rejection and duplicate teaching
- `review_memory` — read-only inventory and health
- `update_memory` — lifecycle ops: update, confirm, stale, deprecate, supersede, merge, resolve, prune
- `memory_hygiene` — route candidate facts; scan/plan/apply-safe store repairs
- `memory_contract` — the canonical lifecycle contract and category guidance
- `initialize_project` — activation, gitignore coverage, contract, first workflow

Pass the active repository root as `root`. Claude Code-originated MCP writes
are stamped with `origin_provider: "claude-code"` and `capture_channel: "mcp"`.
The MCP `initialize` handshake also returns the compact contract as server
`instructions`, so agents receive the lifecycle rules without any skill read.

## Hooks

Claude Code auto-loads `hooks/hooks.json` from the plugin bundle by convention
— the same file Codex discovers via its own convention. Do not add an explicit
hooks entry to `.claude-plugin/plugin.json`; that duplicates hook discovery and
breaks plugin load. No separate hook configuration step is required beyond
Claude Code's normal hook trust review for plugin-bundled hooks.

## Required Environment Variables

None. RECALL is local-first: no API keys, tokens, or external services are
required for the Claude Code integration. All memory storage stays on disk
under `.recall/` (or the legacy `.codex_memory/` store when one already
exists).

## Shared Memory Semantics

Treat shared RECALL memory as project truth, not provider truth. Use
provider-specific metadata only when a memory applies to one agent runtime:

- Shared project facts: `applies_to_provider: "all"`
- Claude Code-only behavior: `applies_to_provider: "claude-code"`
- Codex-only behavior: `applies_to_provider: "codex"`
- Kimi-only behavior: `applies_to_provider: "kimi"`

Retrieved memory is context, not authority. Prefer current files and newer
user instructions when they conflict with memory, then save a verified
correction or supersession.

## Security Notes

All RECALL storage stays local to the project. The MCP server and hooks run
local Python scripts, so review the plugin path and hook commands before
enabling them, exactly as you would for Codex or Kimi. Do not store secrets,
credentials, tokens, private keys, passwords, or sensitive personal data in
memory.
