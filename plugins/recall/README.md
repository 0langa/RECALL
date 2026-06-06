# RECALL

RECALL is a local-first Codex plugin for project memory. It stores durable context in `.codex_memory/` inside the active project so an agent can retrieve decisions, constraints, commands, debugging history, requirements, risks, and custom categories across sessions.

## What Works In This Foundation

- Validation-ready Codex plugin manifest at `.codex-plugin/plugin.json`.
- Skills for saving memories, retrieving context, and defining custom categories.
- Project-local configuration in `.codex_memory/memory_config.json`.
- SQLite storage by default, with JSONL support available through config.
- Deterministic local embeddings, a project-local `vector_index.bin`, and weighted retrieval with no network calls.
- Rebuildable vector index and backend diagnostics through `rebuild-index`, `doctor`, and `repair`.
- Heuristic summarization for compact context injection.
- Plugin-bundled lifecycle hooks in `hooks/hooks.json`, matching Codex's default plugin hook discovery path.
- Unit tests for config and memory storage.

## Quick Start

Initialize memory for the current project:

```powershell
python .\scripts\memory_manager.py init
```

Save a memory:

```powershell
python .\scripts\memory_manager.py add decisions "Use SQLite as the default backend because it is local and requires no service."
```

Retrieve memories:

```powershell
python .\scripts\memory_manager.py query "local backend choice" --summary
```

Repair or inspect the backend:

```powershell
python .\scripts\memory_manager.py rebuild-index
python .\scripts\memory_manager.py doctor
python .\scripts\memory_manager.py repair
```

Define a custom category:

```powershell
python .\scripts\memory_manager.py define-category api_contracts --description "Stable API shapes and compatibility promises." --weight 1.4
```

Run tests:

```powershell
python -m unittest discover -s tests
```

Run the end-to-end smoke harness:

```powershell
python .\scripts\smoke_recall.py --json
```

Install locally from the repository root:

```powershell
codex plugin marketplace add .
codex plugin add recall@recall-local
```

Then open Plugins or `/plugins`, choose `RECALL Local`, and install `RECALL` if you prefer the UI flow. See [docs/INSTALL.md](docs/INSTALL.md) for hook trust and runtime data notes.

Validate the plugin:

```powershell
python <path-to-plugin-creator>\scripts\validate_plugin.py <path-to-RECALL>
```

Build a zip package:

```powershell
.\build_plugin.ps1
```

## Hooks

Codex auto-discovers plugin hooks from `hooks/hooks.json`. RECALL currently wires:

- `SessionStart` to load high-signal project memory.
- `UserPromptSubmit` to catch explicit "remember this" and "define category" cues.
- `PostToolUse` to capture useful command and debugging context.
- `PreCompact` and `Stop` to save lightweight checkpoints.

Plugin-bundled hooks are reviewed through Codex's normal hook trust flow before they run.

## Categories

Built-in categories are:

- `decisions`
- `constraints`
- `debug_history`
- `preferences`
- `tasks`
- `session_summaries`
- `project_state`
- `architecture`
- `commands`
- `lessons_learned`
- `requirements`
- `risks`

Unknown categories are accepted, normalized to snake case, and added to the config with a default weight. You can refine them later with the `define_category` skill or the CLI command.

## Storage

RECALL writes all runtime data under `.codex_memory/`, which is ignored by git. The default backend is SQLite:

```text
.codex_memory/
  memory_config.json
  memory.sqlite
```

To use JSONL files, change `backend` in `.codex_memory/memory_config.json` to `jsonl`.

If a project-level `memory_config.json` exists before initialization, RECALL copies it into `.codex_memory/memory_config.json` and uses the project-local runtime copy from there.

## Security

RECALL is designed to stay local. The foundation implementation makes no network calls and redacts common secret-like patterns before storing memory. Still, treat memory as project data: do not ask it to store credentials, private keys, tokens, passwords, or sensitive personal data.

## Roadmap

The V1 path now prioritizes structured memory cards, live Codex install verification, hook payload hardening, release-grade packaging, and repeatable e2e smoke tests. Bundled local model embeddings remain optional after V1, only if they can be packaged and smoke-tested without network calls.
