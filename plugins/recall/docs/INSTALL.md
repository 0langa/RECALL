# Install RECALL

The installable plugin is `plugins/recall/`.
It contains the shared engine, seven skills, hooks, and provider manifests.
Python 3.11 or later must be available to the host.

## Codex from GitHub

```bash
codex plugin marketplace add 0langa/RECALL --ref v1.6.0
codex plugin add recall@recall-local
```

You can also use the Git URL:

```bash
codex plugin marketplace add https://github.com/0langa/RECALL --ref v1.6.0
codex plugin add recall@recall-local
```

Start a new task in the target project.
Then run:

```text
@recall initialize this project
```

Review the bundled hooks when Codex asks.

The Codex plugin `.mcp.json` declares the RECALL MCP server.
Do not add a second manual `mcp_servers.recall` entry.

## Codex from a local checkout

Run these commands from the repository root:

```bash
codex plugin marketplace add .
codex plugin add recall@recall-local
```

## Claude Code

Add the plugin folder as a local marketplace:

```text
claude plugin marketplace add <path-to-RECALL>/plugins/recall
claude plugin install recall@recall-local
```

Start a new Claude Code session in the target project.
See [CLAUDE_CODE.md](CLAUDE_CODE.md).

## Kimi Code

Run these commands in Kimi Code:

```text
/plugins install <path-to-RECALL>/plugins/recall
/plugins enable recall
/plugins mcp enable recall recall
/reload
```

See [KIMI_CODE.md](KIMI_CODE.md) for optional hook setup.

## Verify the public adapter

Run from the installed or source plugin root.
Put `--root` before the subcommand.

```bash
python ./scripts/recall_skill.py --root <project-root> activation-status
python ./scripts/recall_skill.py --root <project-root> retrieve-memory "current project context" --summary
python ./scripts/recall_skill.py --root <project-root> doctor
```

## Runtime data

New project memory is in `.recall/` under the project root.
An existing `.codex_memory/` store remains the active legacy store until explicit migration.
Keep both directories out of source control.

Plugin removal does not delete project memory.
Do not delete either store unless you intend to delete its data.

## Upgrade from a manual Codex MCP entry

The Codex plugin has declared the MCP server since v1.5.5.
Version 1.6.0 moves the declaration from the manifest to the root `.mcp.json` file that current Codex loads.
Remove a manual `[mcp_servers.recall]` entry before you use the plugin declaration.
This avoids two server registrations.

## Tested host scope

Readiness checks used Codex CLI `0.154.0`, Claude Code `2.1.268`, and Kimi Code `0.42.0` in isolated homes.
Those checks do not prove the exact v1.6.0 ZIP.
Exact installed-package proof is pending at candidate freeze.

The public asset will be at the [v1.6.0 GitHub release](https://github.com/0langa/RECALL/releases/tag/v1.6.0) after publication.
