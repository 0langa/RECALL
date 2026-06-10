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

## Minimal Working Path

From the repository root:

```bash
codex plugin marketplace add .
codex plugin add recall@recall-local
```

Then start a Codex thread in a project and review RECALL's hooks in Codex Settings > Coding > Hooks. Plugin installation is one command once the marketplace is configured; hook execution still requires Codex's normal trust review for non-managed hooks.

For direct skill-adapter checks from this plugin folder:

Initialize memory for the current project:

```bash
python ./scripts/recall_skill.py retrieve-memory "current project context" --summary
```

Save a memory:

```bash
python ./scripts/recall_skill.py save-insight decisions "Use SQLite as the default backend because it is local and requires no service." --summary "SQLite is the default backend." --source skill
```

Retrieve memories:

```bash
python ./scripts/recall_skill.py retrieve-memory "local backend choice" --summary
```

Developer/support maintenance commands are available through the internal backend script, but they are not the public plugin workflow.

Review what RECALL thinks matters:

```bash
python ./scripts/recall_skill.py review-memory --limit 20
```

Preview and archive old automatic hook noise:

```bash
python ./scripts/recall_skill.py archive-noise
python ./scripts/recall_skill.py archive-noise --apply --limit 50
```

`archive-noise` is non-destructive and dry-runs by default. With `--apply`, it marks low-value automatic `post_tool_use` command records as `archived`; it does not delete memory.

Confirm, resolve, supersede, merge, or prune memories through the public adapter:

```bash
python ./scripts/recall_skill.py confirm-memory 12 --source-session session-2026-06-08
python ./scripts/recall_skill.py resolve-memory 12 --note "Implemented in the current release."
python ./scripts/recall_skill.py stale-memory 12 --note "Needs reconfirmation after API changes."
python ./scripts/recall_skill.py supersede-memory 12 18 --note "Memory #18 corrects #12."
python ./scripts/recall_skill.py merge-memories 18 19 20 --note "Folded duplicate memories into #18."
python ./scripts/recall_skill.py prune-memory 12 --note "Reviewed as obsolete."
```

`prune-memory` is non-destructive: it marks a memory as `archived` and records review metadata.

Define a custom category:

```bash
python ./scripts/recall_skill.py define-category api_contracts --description "Stable API shapes and compatibility promises." --weight 1.4
```

Run tests:

```bash
python -m unittest discover -s tests
```

Run the end-to-end smoke harness:

```bash
python ./scripts/smoke_recall.py --json
```

## Local Install

```bash
codex plugin marketplace add .
codex plugin add recall@recall-local
```

Then open Plugins or `/plugins`, choose `RECALL Local`, and install `RECALL` if you prefer the UI flow. See [docs/INSTALL.md](docs/INSTALL.md) for hook trust and runtime data notes.

Validate the plugin:

```bash
python <path-to-plugin-creator>/scripts/validate_plugin.py <path-to-RECALL>
```

Build a zip package:

macOS/Linux:

```bash
./build_plugin.sh
```

Windows PowerShell:

```powershell
.\build_plugin.ps1
```

## Troubleshooting

If `codex plugin add recall@recall-local` cannot find RECALL, confirm the marketplace file is at the repository root and points to `./plugins/recall`.

If retrieval looks stale, run:

```bash
python ./scripts/recall_skill.py retrieve-memory "current project context" --summary
python ./scripts/recall_skill.py doctor
```

If `doctor` reports repairable index issues, run the safe public repair action:

```bash
python ./scripts/recall_skill.py repair
```

If category names or weights were edited manually in `memory_config.json`, normalize and rewrite the project-local runtime config with:

```bash
python ./scripts/update_categories.py --root <project-root>
```

This is a developer/support maintenance command, not a Codex hook event. Normal category creation and refinement should use the `define-category` skill.

To inspect available categories through the public adapter:

```bash
python ./scripts/recall_skill.py list-categories
```

If hooks do not run, open Codex Settings > Coding > Hooks and review the RECALL hook definitions. Codex skips untrusted plugin hooks until the user trusts them.

If commands work in the source checkout but not after install, run the smoke harness against the installed plugin root:

```bash
python ./scripts/smoke_recall.py --installed-plugin-root <installed-plugin-root> --json
```

## Hooks

Codex auto-discovers plugin hooks from `hooks/hooks.json`. RECALL currently wires:

- `SessionStart` as a quiet compatibility hook; it does not inject memory by default.
- `UserPromptSubmit` to activate RECALL only when the prompt explicitly includes `@recall`, `plugin://recall`, or `$recall:`.
- `UserPromptSubmit` to catch explicit "remember this" and "define category" cues after RECALL is activated.
- `PostToolUse` to buffer useful command and debugging context only for activated RECALL turns.
- `PreCompact` to save compaction checkpoints only for activated RECALL turns.
- `Stop` to request one compact inline finalizer pass for activated RECALL turns with buffered durable evidence.

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

Unknown categories are accepted, normalized to snake case, and added to the config with a default weight. You can refine them later with the `define-category` skill or the CLI command.

Lifecycle metadata is stored inside each memory card. RECALL understands `related_to`, `supersedes`, `superseded_by`, `source_session`, and `last_confirmed`, and automatic hooks can update or link existing memories instead of creating repetitive notes.

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

## Known Limitations

- Codex hook trust is intentionally interactive; RECALL cannot bypass that review.
- Retrieval is schema-first and deterministic, not transformer-grade semantic search.
- RECALL depends on a local Python runtime being available to run its scripts and hooks.
- Live Codex App picker visibility, fresh-thread skill discovery, hook trust, installed-cache smoke, and built-zip marketplace smoke were verified for `v0.1.0`; future Codex payload drift remains a normal compatibility risk.

## Roadmap

The V1 path now prioritizes structured memory cards, live Codex install verification, hook payload hardening, release-grade packaging, and repeatable e2e smoke tests. Bundled local model embeddings remain optional after V1, only if they can be packaged and smoke-tested without network calls.
