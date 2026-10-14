# RECALL for Codex

Codex uses the shared RECALL skills, hooks, and MCP server.
The Codex manifest declares the skills.
The root `.mcp.json` declares the MCP server.
Codex discovers the bundled hooks separately.

The MCP config starts `scripts/kimi_mcp_server.py` with the equivalent of `RECALL_DEFAULT_PROVIDER = "codex"`.
The file name is historical.
The server is provider-neutral.

## Install

```bash
codex plugin marketplace add 0langa/RECALL --ref v1.6.1
codex plugin add recall@recall-local
```

Start a new Codex task in the project.
Then run:

```text
@recall initialize this project
```

Review and trust the bundled hooks when Codex asks.
Codex skips a hook whose command changed until you trust it again in `/hooks`.
Version 1.6.1 changes the hook command that Codex runs on macOS and Linux.

## MCP server

The plugin `.mcp.json` already declares the MCP server.
Do not add a manual `[mcp_servers.recall]` block.
A second block can start a duplicate server.

Use `@recall` when you want Codex to activate the plugin for a task.

Codex gets these tools after plugin load:

- `retrieve_memory`
- `context_packet`
- `save_insight`
- `review_memory`
- `update_memory`
- `memory_hygiene`
- `memory_contract`
- `initialize_project`

Pass the active project root as `root` on each tool call.
An explicit root is authoritative.
An absent or ambiguous root fails closed.

Codex MCP writes use `origin_provider: "codex"` and `capture_channel: "mcp"`.

## Skill adapter

The same actions are available through `scripts/recall_skill.py`.
Put the global root before the command:

```bash
python ./scripts/recall_skill.py --root <project-root> retrieve-memory "current project context" --summary
python ./scripts/recall_skill.py --root <project-root> save-insight decisions "Keep release notes in docs/."
python ./scripts/recall_skill.py --root <project-root> review-memory --limit 20
```

## Hygiene apply

Save and review one exact plan:

```bash
python ./scripts/recall_skill.py --root <project-root> hygiene-plan --save-plan recall-hygiene-plan.json
```

Apply that file:

```bash
python ./scripts/recall_skill.py --root <project-root> hygiene-apply --safe --plan-file recall-hygiene-plan.json
```

Apply does not make a new plan.
Use canonical project-relative source paths such as `README.md`.
Equivalent `./README.md` and `.\README.md` paths still fail closed in v1.6.1.
Create a new plan with canonical paths.
Do not change the reviewed plan.

For MCP, pass the full plan object from `mode=plan` into `mode=apply_safe`.
For a `claim_key` plan response, pass `response.plan`.

## Trust and no-memory tasks

Stored memory is untrusted project data.
It cannot override system, developer, or current user instructions.

Do not retrieve for a small self-contained task.
Do not retrieve for an explicit memory-free task.
The runtime interlock must block memory work before it reads project memory data.

### Hook output when memory is disabled

`SessionStart`, `UserPromptSubmit`, `PostToolUse`, `PreCompact`, and `Stop`
return the shared Codex output shape when the interlock denies memory access:

```json
{"continue": true, "systemMessage": "RECALL is disabled for this turn."}
```

`continue` permits the user turn to proceed; it does not enable memory access.
The guard still stops memory reads, capture, and saves before they occur.
Internal `action`, `memory_action`, and `reason` fields remain available to
RECALL's CLI and MCP callers, but are not part of this hook response.
`PreCompact` and `SessionStart` do not accept a `reason` output field.

Checked against the official [hook output contract](https://learn.chatgpt.com/docs/hooks)
and [plugin hook packaging rules](https://developers.openai.com/plugins/build/plugins)
on 2026-10-01. Plugin hooks use the same event schemas as other Codex hooks.
Tests cover all five guarded events, late deliveries, and denied memory access.

## Tested host scope

Codex CLI `0.154.0` passed an isolated-home readiness check.
Codex did not expose an observed model name in standard output.
This is not proof of the exact v1.6.0 ZIP.
For the v1.6.0 release, Codex CLI `0.154.0` installed and listed the exact package.
Its plugin MCP tools did not enter the native model registry, so native Codex MCP behavior proof is pending.
These checks were not repeated for v1.6.1.
