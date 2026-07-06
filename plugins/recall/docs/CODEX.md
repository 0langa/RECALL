# RECALL on Codex

Codex integrates with RECALL through three channels:

1. **Skills** — the shared `./skills/` surface, discovered from the plugin manifest.
2. **Hooks** — the shared `hooks/hooks.json`, auto-discovered by Codex's plugin
   hook convention (SessionStart injects the lifecycle contract; capture and
   finalization run exactly as on other providers).
3. **Skill adapter CLI** — `scripts/recall_skill.py`, which exposes a superset
   of the MCP tool surface as subcommands. Pass `--root <project-root>`
   BEFORE the subcommand.

The engine, store, contract, and hook behavior are identical across
providers. What differs by default is **delivery**: Claude Code and Kimi Code
declare RECALL's MCP server in their plugin manifests, so their agents see
eight typed tools with descriptions in context. Codex's plugin manifest does
not declare MCP servers, so a stock Codex agent works through the skills and
the adapter CLI instead.

## Recommended: enable the MCP server for Codex

Codex supports the same stdio MCP servers via `config.toml`
(`[mcp_servers.<name>]`, configurable with `codex mcp` or by editing the
file). RECALL's server is provider-neutral — one entry gives Codex the exact
same eight tools Claude Code and Kimi Code get, with correct provenance
stamping:

```toml
# ~/.codex/config.toml
[mcp_servers.recall]
command = "python"
args = ["<path-to-installed-recall-plugin>/scripts/kimi_mcp_server.py"]
env = { RECALL_DEFAULT_PROVIDER = "codex" }
```

Replace `<path-to-installed-recall-plugin>` with the installed plugin root
(the directory containing `scripts/`). Verify with `/mcp` in the Codex TUI —
you should see `recall` with tools `retrieve_memory`, `context_packet`,
`save_insight`, `review_memory`, `update_memory`, `memory_hygiene`,
`memory_contract`, and `initialize_project`. Writes made through this server
are stamped `origin_provider: "codex"`, `capture_channel: "mcp"`.

Notes:

- Prefer the user-level `~/.codex/config.toml`; project-scoped
  `.codex/config.toml` MCP entries have known loading inconsistencies in some
  Codex builds.
- Pass the active repository root as `root` on every tool call, exactly as on
  Kimi and Claude Code.
- This is optional: without it, every capability remains reachable through
  the adapter CLI (see the tool-to-command map below), and hooks/contract
  behavior is unchanged. With it, Codex agents get the same in-context tool
  discoverability as the other providers — recommended when cross-provider
  consistency matters.

## MCP tool ↔ adapter command map

| MCP tool | Adapter equivalent (`recall_skill.py --root <root> …`) |
|---|---|
| `retrieve_memory` | `retrieve-memory "<query>"` |
| `context_packet` | `context-packet "<query>"` |
| `save_insight` | `save-insight <category> "<content>"` |
| `review_memory` | `review-memory` (plus `audit-memory`) |
| `update_memory` | `confirm-memory` / `stale-memory` / `supersede-memory` / `merge-memories` / `resolve-memory` / `prune-memory` / `edit-memory` / `deprecate-memory` |
| `memory_hygiene` | `route-memory` / `hygiene-scan` / `hygiene-plan` / `hygiene-apply --safe` |
| `memory_contract` | `contract` |
| `initialize_project` | `initialize-project` |

The adapter additionally exposes maintenance commands with no MCP
counterpart (`migrate-store`, `export-memory`/`import-memory`,
`backup-memory`/`restore-memory`, `list-conflicts`/`resolve-conflict`,
`doctor`/`repair`); those are deliberate — recovery and migration stay
explicit CLI operations on every provider.
