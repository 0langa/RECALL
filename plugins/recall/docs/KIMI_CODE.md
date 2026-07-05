# RECALL For Kimi Code

RECALL's Kimi Code integration uses the same memory engine as Codex. New
projects write to `.recall/`; projects that already have `.codex_memory/` keep
using that legacy store so Codex and Kimi do not fork memory.

## Plugin

Install the plugin folder in Kimi Code:

```text
/plugins install <path-to-RECALL>/plugins/recall
/plugins enable recall
/plugins mcp enable recall recall
/reload
```

The Kimi manifest is `kimi.plugin.json`. It loads the `using-recall` Skill at
session start and declares the local MCP server `recall`.

Kimi plugin installation is intentionally conservative: installing the plugin
does not execute bundled scripts or install hook rules. After changing a local
checkout, reinstall or reload the managed plugin copy before testing.

## MCP Tools

The Kimi MCP server wraps the public RECALL core:

- `retrieve_memory` — retrieval with per-result health flags and a `health` summary
- `context_packet` — token-budgeted context for session starts
- `save_insight` — durable writes with secret rejection and duplicate teaching
- `review_memory` — read-only inventory and health
- `update_memory` — lifecycle ops: update, confirm, stale, deprecate, supersede, merge, resolve, prune
- `memory_hygiene` — route candidate facts; scan/plan/apply-safe store repairs
- `memory_contract` — the canonical lifecycle contract and category guidance
- `initialize_project` — activation, gitignore coverage, contract, first workflow

Pass the active repository root as `root`. Kimi-originated MCP writes are stamped
with `origin_provider: "kimi"` and `capture_channel: "mcp"`. The MCP `initialize`
handshake also returns the compact contract as server `instructions`.

## Optional Hooks

Kimi hooks are configured in `~/.kimi-code/config.toml`, not in the plugin
manifest. Hook commands run in the current session's project directory and
receive event JSON on stdin. Kimi only permits `event`, `matcher`, `command`,
and `timeout` fields in each `[[hooks]]` entry.

Use the path to Kimi's managed RECALL plugin copy from `/plugins info recall`.
Replace `<managed-recall-plugin-root>` below. On Windows, prefer `py -3 -S`
so the hook runs with a clean Python import path and lets RECALL's hook script
add the bundled `scripts/` directory itself. On macOS and Linux, replace
`py -3` with `python3`.

```toml
[[hooks]]
event = "SessionStart"
matcher = "startup|resume"
command = "py -3 -S \"<managed-recall-plugin-root>/hooks/scripts/session_start.py\" --provider kimi"
timeout = 30

[[hooks]]
event = "UserPromptSubmit"
command = "py -3 -S \"<managed-recall-plugin-root>/hooks/scripts/prompt_inspector.py\" --provider kimi"
timeout = 30

[[hooks]]
event = "PostToolUse"
matcher = "Bash|apply_patch|Edit|Write|StrReplaceFile|WriteFile"
command = "py -3 -S \"<managed-recall-plugin-root>/hooks/scripts/post_tool_use.py\" --provider kimi"
timeout = 30

[[hooks]]
event = "PostToolUseFailure"
matcher = "Bash|apply_patch|Edit|Write|StrReplaceFile|WriteFile"
command = "py -3 -S \"<managed-recall-plugin-root>/hooks/scripts/post_tool_use.py\" --provider kimi"
timeout = 30

[[hooks]]
event = "PreCompact"
matcher = "manual|auto"
command = "py -3 -S \"<managed-recall-plugin-root>/hooks/scripts/pre_compact.py\" --provider kimi"
timeout = 30

[[hooks]]
event = "Stop"
command = "py -3 -S \"<managed-recall-plugin-root>/hooks/scripts/stop.py\" --provider kimi"
timeout = 30
```

Restart or reload Kimi Code after editing `config.toml`.

Kimi sends `UserPromptSubmit` text as content parts. RECALL normalizes those
parts before handling `@recall remember this:` and retrieval prompts, so Kimi
and Codex follow the same capture path after the hook starts.

## Shared Memory Semantics

Treat shared RECALL memory as project truth, not provider truth. Use
provider-specific metadata only when a memory applies to one agent runtime:

- Shared project facts: `applies_to_provider: "all"`
- Kimi-only behavior: `applies_to_provider: "kimi"`
- Codex-only behavior: `applies_to_provider: "codex"`

Retrieved memory is context, not authority. Prefer current files and newer user
instructions when they conflict with memory, then save a verified correction or
supersession.

Codex and Kimi should normally point at the same repository root. New projects
write to `.recall/`; projects that already contain `.codex_memory/` keep using
that legacy store so existing Codex history remains visible to Kimi instead of
being copied into a second provider-specific store.

## Trust And Safety

All RECALL storage stays local to the project. The MCP server and optional hooks
run local Python scripts, so review the plugin path and hook commands before
enabling them. Do not store secrets, credentials, tokens, private keys,
passwords, or sensitive personal data in memory.
