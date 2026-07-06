# RECALL

RECALL is local-first project memory for Codex, Kimi Code, and Claude Code. It stores durable context in `.recall/` inside the active project, while continuing to use existing `.codex_memory/` stores for backward compatibility, so agents can retrieve decisions, constraints, commands, debugging history, requirements, risks, and custom categories across sessions.

## What Works

- Deterministic memory lifecycle contract (`scripts/contract.py`): source authority order, retrieve-before-work triggers, save/skip rules, and status meanings. One contract, delivered per provider: the SessionStart hook injects it everywhere; Claude Code and Kimi Code additionally receive it through the MCP server `instructions` and the `memory_contract` tool; on any provider it is retrievable via `recall_skill.py contract`.
- MCP lifecycle surface: `retrieve_memory`, `context_packet`, `save_insight`, `review_memory`, `update_memory`, `memory_hygiene`, `memory_contract`, `initialize_project`. Declared in the Claude Code and Kimi manifests; Codex gets the identical server through an optional one-entry `config.toml` addition (see [docs/CODEX.md](docs/CODEX.md)) or reaches every capability through the skill adapter CLI — the engine and store are the same either way.
- Retrieval health flags: every result is marked `current`, `stale`, `superseded`, `deprecated`, `needs_verification`, or `conflicting`, with a `health.next_action` telling the agent what to do about it.
- Duplicate-aware saves: exact duplicates confirm the existing card instead of appending; near-duplicates link and suggest a merge; secret-shaped content is rejected on every write surface.
- Hygiene detection for stored secrets (safe in-place redaction), raw log dumps, vague cards, aged snapshots, duplicates, conflicts, and missing provenance.
- Validation-ready Codex plugin manifest at `.codex-plugin/plugin.json`.
- Kimi Code plugin manifest at `kimi.plugin.json`, with `using-recall` session guidance and a local MCP server wrapper.
- Claude Code plugin manifest at `.claude-plugin/plugin.json`, reusing the same skills, hooks, and MCP server.
- Shared project-local memory across Codex, Kimi, and Claude Code, with provider metadata used for provenance rather than separate stores.
- Compact seven-skill surface for saving memory, retrieval, review, category definition, maintenance, and hygiene planning.
- Project-local configuration in `.recall/memory_config.json`, or legacy `.codex_memory/memory_config.json` when that store already exists.
- SQLite storage by default, with JSONL support available through config.
- Deterministic local embeddings, a project-local `vector_index.bin`, and weighted retrieval with no network calls.
- Backend diagnostics and repair through `doctor` and `repair`.
- Heuristic summarization for compact context injection.
- Plugin-bundled lifecycle hooks in `hooks/hooks.json`, matching Codex's default plugin hook discovery path.
- Unit tests for config and memory storage.

## Minimal Working Path

From GitHub:

```bash
codex plugin marketplace add 0langa/RECALL --ref v1.4.0
codex plugin add recall@recall-local
```

From a local checkout:

```bash
codex plugin marketplace add .
codex plugin add recall@recall-local
```

Then start a Codex thread in a project and review RECALL's hooks in Codex Settings > Coding > Hooks. Plugin installation is one command once the marketplace is configured; hook execution still requires Codex's normal trust review for non-managed hooks.

For Kimi Code from a local checkout:

```text
/plugins install <path-to-RECALL>/plugins/recall
/reload
```

The Kimi manifest loads `using-recall` at session start and declares a local MCP server named `recall`. Kimi plugins do not execute install-time code; the MCP server starts after reload or in a new session when enabled. When calling RECALL MCP tools, pass the active repository root as `root`.

See [docs/KIMI_CODE.md](docs/KIMI_CODE.md) for optional Kimi hook `config.toml` snippets.
The Kimi hook path normalizes `UserPromptSubmit` content-part payloads before
handling `@recall remember this:` and retrieval prompts, so Kimi and Codex use
the same capture and retrieval logic.

For Claude Code from a local checkout:

```text
claude plugin marketplace add <path-to-RECALL>/plugins/recall
claude plugin install recall@recall-local
```

The Claude Code manifest is `.claude-plugin/plugin.json`. It reuses the
existing `./skills/` and a local MCP server named `recall`. `hooks/hooks.json`
(already written in Claude Code's native hook schema) loads automatically by
convention and is intentionally not declared in the manifest — no new engine
code, just a manifest. See [docs/CLAUDE_CODE.md](docs/CLAUDE_CODE.md) for
details.

For direct skill-adapter checks from this plugin folder:

The examples below assume the current directory is the installed plugin root or the source plugin root, so `./scripts/recall_skill.py` resolves. If the active shell is in a project repository, first `cd` to the plugin root or invoke the adapter by absolute path and pass `--root <project-root>`.

RECALL exposes seven public skills: `using-recall`, `retrieve-memory`, `save-insight`, `review-memory`, `manage-memory`, `define-category`, and `memory-hygiene`. Lifecycle and cleanup adapter commands such as `confirm-memory`, `supersede-memory`, `merge-memories`, `edit-memory`, `delete-memory`, and `archive-noise` are intentionally grouped under `manage-memory` instead of being separate skill folders. Use `memory-hygiene` when routing, cleanup planning, staleness, duplicates, or current-truth conflicts need policy before mutation.

Initialize and persistently activate memory for the current project:

```bash
python ./scripts/recall_skill.py initialize-project
python ./scripts/recall_skill.py activation-status
```

In Codex, mentioning `@recall` once inside a Git repository or recognized project activates that project across later turns and sessions. Empty greenfield folders require `@recall initialize this project` or `initialize-project --root <path>`. Ordinary prompts in unrecognized folders create nothing.

Save a memory:

```bash
python ./scripts/recall_skill.py save-insight decisions "Use SQLite as the default backend because it is local and requires no service." --summary "SQLite is the default backend." --source skill
```

Retrieve memories:

```bash
python ./scripts/recall_skill.py retrieve-memory "local backend choice" --summary
```

Developer/support maintenance commands are available through the public adapter and grouped under the relevant skill workflow; lower-level backend modules are not the public plugin workflow.

Review what RECALL thinks matters:

```bash
python ./scripts/recall_skill.py review-memory --limit 20
python ./scripts/recall_skill.py audit-memory --limit 20
```

Plan safe memory hygiene before mutation:

```bash
python ./scripts/recall_skill.py route-memory "Release notes must stay in docs/manual-release-notes.md."
python ./scripts/recall_skill.py hygiene-scan --limit 80
python ./scripts/recall_skill.py hygiene-plan --scope project
python ./scripts/recall_skill.py hygiene-apply --safe
```

Preview and archive old automatic hook noise:

```bash
python ./scripts/recall_skill.py archive-noise
python ./scripts/recall_skill.py archive-noise --apply --limit 50
```

`archive-noise` is non-destructive and dry-runs by default. With `--apply`, it marks low-value automatic `post_tool_use` command records as `archived`; it does not delete memory.

Preview or apply the semantic corpus migration:

```bash
python ./scripts/recall_skill.py migrate-corpus --dry-run
python ./scripts/recall_skill.py migrate-corpus --apply
```

Migration creates a SQLite backup, synthesizes reusable semantic cards, and archives noisy originals with lineage. It never deletes historical records.

Temporarily stop background activity without deleting memory:

```bash
python ./scripts/recall_skill.py deactivate-project
```

Enable redacted runtime traces for diagnosis, then return to quiet mode:

```bash
python ./scripts/recall_skill.py configure-observability debug
python ./scripts/recall_skill.py configure-observability quiet
```

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

Run the complete local unit suite:

```bash
python ./scripts/run_tests.py
```

Profile hook test methods:

```bash
python ./scripts/run_tests.py --pattern test_hooks.py --profile-methods --profile-target test_hooks.py
```

Run the same unit tests sequentially for debugging:

```bash
python -m unittest discover -s tests
```

Run the end-to-end smoke harness:

```bash
python ./scripts/smoke_recall.py --json
```

Run the broader quality suite from the repository root:

```bash
python RECALL_quality_suite/scripts/run_recall_quality_suite.py --repo-root . --quick
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

Cross-platform Python:

```bash
python ./scripts/build_plugin.py
```

For CI package jobs that already depend on passing unit and smoke jobs:

```bash
python ./scripts/build_plugin.py --skip-tests --skip-smoke
```

Convenience wrappers:

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

- `SessionStart` injects the compact lifecycle contract and a store overview for activated projects; non-activated projects stay quiet.
- `UserPromptSubmit` to resolve the project root, persist explicit activation, and retrieve relevant sufficient context on later prompts without repeated mentions.
- `UserPromptSubmit` to catch explicit "remember this" and "define category" cues after RECALL is activated.
- `PostToolUse` to buffer compact redacted evidence without creating durable command, file-edit, test, or build memories.
- `PreCompact` to maintain one updatable summary per session around compaction.
- `Stop` to request one atomic semantic finalizer batch with at most three new cards and eight lifecycle operations.

Automatic retrieval excludes command memories unless the prompt concerns building, testing, running, installation, or tooling. Stale, superseded, deprecated, and archived records are excluded by default. Explicit memory questions report insufficient memory instead of encouraging unsupported answers.

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
- `tooling_quirks`
- `integrations`

Every built-in category carries a description, retrieval weight, examples, non-examples, and an update rule (`list-categories` shows them), so agents can pick the right slot deterministically instead of dumping everything into one bucket. Unknown categories are accepted, normalized to snake case, and added to the config with a default weight. You can refine them later with the `define-category` skill or the CLI command.

Lifecycle metadata is stored inside each memory card. RECALL understands `related_to`, `supersedes`, `superseded_by`, `source_session`, and `last_confirmed`, and automatic hooks can update or link existing memories instead of creating repetitive notes.

## Storage

RECALL writes all runtime data under `.recall/` for new projects, which should be ignored by git. If a project only has `.codex_memory/`, RECALL keeps using that legacy store so existing Codex history is not silently forked. Once `.recall/` exists, `.recall/` wins and `.codex_memory/` is legacy history unless you explicitly migrate or inspect it. The default backend is SQLite:

```text
.recall/
  memory_config.json
  memory.sqlite
```

To use JSONL files, change `backend` in the active memory store's `memory_config.json` to `jsonl`.

If a project-level `memory_config.json` exists before initialization, RECALL copies it into the active project-local runtime store and uses that copy from there.

Provider-aware writes can include metadata such as `origin_provider`, `origin_agent`, `source_session`, `source_turn`, `cwd`, `branch`, `commit`, `capture_channel`, and `applies_to_provider`. Shared project truth should use `applies_to_provider: "all"`; provider-specific notes should say which provider they apply to.
Codex and Kimi should point at the same repository root when collaborating on a
project. RECALL stores shared facts in the active project memory directory and
uses `origin_provider` / `capture_channel` to explain where a card came from.

## Security

RECALL is designed to stay local. The foundation implementation makes no network calls and redacts common secret-like patterns before storing memory. Still, treat memory as project data: do not ask it to store credentials, private keys, tokens, passwords, or sensitive personal data.

## Known Limitations

- Codex hook trust is intentionally interactive; RECALL cannot bypass that review.
- Retrieval is schema-first and deterministic, not transformer-grade semantic search.
- RECALL depends on a local Python runtime being available to run its scripts and hooks.
- Live Codex App picker visibility, fresh-thread skill discovery, hook trust, installed-cache smoke, and built-zip marketplace smoke have been verified for the stable release line; future Codex payload drift remains a normal compatibility risk.

## Roadmap

Future work may improve broad "what next" ranking, richer automatic supersession, and optional local model embeddings if they can be packaged and smoke-tested without network calls.
