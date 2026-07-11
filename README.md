# RECALL

Local-first project memory for Codex, Kimi Code, and Claude Code.

RECALL gives coding agents durable project context without sending memory to a hosted service. It stores decisions, requirements, risks, commands, debugging history, and session summaries inside the active project under `.recall/`, while continuing to read existing `.codex_memory/` stores for backward compatibility.

The installable plugin lives in [`plugins/recall`](plugins/recall/). It contains the shared RECALL core, the Codex plugin manifest/hooks, a Kimi Code plugin manifest/MCP adapter, and a Claude Code plugin manifest that reuses the same skills, hooks, and MCP server.

## What RECALL Does

- Keeps memory local to each project in `.recall/`, with legacy `.codex_memory/` compatibility.
- Retrieves relevant project context when you invoke `@recall`.
- Captures explicit "remember this" requests and useful development outcomes.
- Stores structured memory categories such as `decisions`, `requirements`, `risks`, `commands`, and `debug_history`.
- Supports review, confirmation, supersession, merge, and archival of memory cards.
- Exposes a deterministic lifecycle contract (retrieve before work, save/skip rules, source authority order). One contract everywhere, delivered per provider: session-start hooks inject it on Codex, Claude Code, and Kimi Code alike; Claude Code and Kimi Code additionally get it through MCP tool schemas and server instructions, and Codex can opt into the same MCP server with one `config.toml` entry ([docs](plugins/recall/docs/CODEX.md)).
- Flags retrieval results as current, stale, superseded, deprecated, needs-verification, or conflicting so agents know what to trust.
- Detects duplicates at save time and confirms the existing card instead of appending; hygiene finds stored secrets, raw logs, vague cards, aged snapshots, and conflicts, and applies safe repairs.
- Exposes seven public skills: `using-recall`, `retrieve-memory`, `save-insight`, `review-memory`, `manage-memory`, `define-category`, and `memory-hygiene`.
- Uses SQLite by default, with JSONL storage available through config.
- Builds and validates as a portable Codex plugin zip on Windows, macOS, and Linux.
- Exposes a Kimi Code plugin manifest and MCP server wrapper over the same memory engine.
- Exposes a Claude Code plugin manifest (`.claude-plugin/plugin.json`) over the same skills, hooks, and MCP server — no separate engine.
- Shares one project-local memory store across Codex, Kimi, and Claude Code; provider metadata records provenance without forking memory.

RECALL does not use a hosted database or network embedding service. It is designed as a local project assistant, not a team memory server.

## Install For Codex

Requires Codex CLI with plugin marketplace support and a local Python runtime.

```bash
codex plugin marketplace add 0langa/RECALL --ref v1.5.1
codex plugin add recall@recall-local
```

Then open Codex in a project and invoke:

```text
@recall initialize this project
```

Codex may ask you to review and trust the bundled RECALL hooks before automatic memory capture and retrieval run.

To give Codex the same eight MCP tools Claude Code and Kimi Code see (recommended for cross-provider consistency), add RECALL's server to `~/.codex/config.toml` — one entry, documented in [plugins/recall/docs/CODEX.md](plugins/recall/docs/CODEX.md).

## Install From A Local Checkout

```bash
git clone https://github.com/0langa/RECALL.git
cd RECALL
codex plugin marketplace add .
codex plugin add recall@recall-local
```

## Install For Kimi Code

From Kimi Code, install the same plugin directory:

```text
/plugins install <path-to-RECALL>/plugins/recall
/reload
```

RECALL's Kimi manifest loads the `using-recall` session Skill and declares a local MCP server named `recall`. Plugin installation does not execute code; the MCP server starts after reload or in a new session when enabled by Kimi Code. When using RECALL tools from Kimi, pass the active repository root as `root`.

Optional Kimi hook setup lives in [`plugins/recall/docs/KIMI_CODE.md`](plugins/recall/docs/KIMI_CODE.md).
The hook path is optional but verified: Kimi `UserPromptSubmit` content-part
payloads are normalized before RECALL handles `@recall remember this:` and
retrieval prompts.

## Install For Claude Code

From a local checkout, add a local marketplace and install:

```text
claude plugin marketplace add <path-to-RECALL>/plugins/recall
claude plugin install recall@recall-local
```

RECALL's Claude Code manifest (`.claude-plugin/plugin.json`) reuses the
existing `./skills/` and declares the same local MCP server pattern as the
Kimi integration. `hooks/hooks.json` (already written in Claude Code's
native hook schema) is loaded automatically by convention and is
intentionally not declared in the manifest — no new engine code was added. See
[`plugins/recall/docs/CLAUDE_CODE.md`](plugins/recall/docs/CLAUDE_CODE.md)
for details.

## Build The Plugin Zip

The release build is cross-platform and Python-based:

```bash
python build_plugin.py
```

This runs the plugin tests, validates the Codex plugin manifest when the local validator is available, runs the smoke harness, inspects the package, and writes:

```text
dist/recall.zip
```

Convenience wrappers call the same Python builder:

```bash
./build_plugin.sh
```

```powershell
.\build_plugin.ps1
```

## Basic Usage

Ask RECALL what it knows:

```text
@recall what project context should I preserve?
```

Save an explicit decision:

```text
@recall remember this: decisions: generated release notes must stay in docs/manual-release-notes.md
```

Review memory from the plugin folder:

```bash
cd plugins/recall
python ./scripts/recall_skill.py review-memory --limit 20
python ./scripts/recall_skill.py retrieve-memory "current project context" --summary
python ./scripts/recall_skill.py doctor
```

Archive low-value automatic command noise without deleting history:

```bash
python ./scripts/recall_skill.py archive-noise
python ./scripts/recall_skill.py archive-noise --apply --limit 50
```

Lifecycle and cleanup commands such as `confirm-memory`, `supersede-memory`, `edit-memory`, `delete-memory`, and `archive-noise` are intentionally grouped under the `manage-memory` skill instead of being separate public skills.
Use `memory-hygiene` first when the right routing or cleanup action is unclear.

More usage and support commands are documented in [`plugins/recall/README.md`](plugins/recall/README.md) and [`plugins/recall/docs/INSTALL.md`](plugins/recall/docs/INSTALL.md).

## Storage

RECALL writes runtime data to the active project:

```text
.recall/
  memory_config.json
  memory.sqlite
```

`.recall/` should stay out of source control. If a project only has a legacy `.codex_memory/` store, RECALL keeps using it so existing history stays visible. Once `.recall/` exists, `.recall/` wins and `.codex_memory/` is legacy history unless you explicitly migrate or inspect it.

## Troubleshooting

Run the built-in diagnostics from `plugins/recall` (or wherever the plugin is installed):

```bash
python ./scripts/recall_skill.py doctor
```

`doctor` reports schema version, index/JSONL drift, and (SQLite) journal mode, FTS5 availability, and integrity. If it reports `"storage_corrupted": true`, restore from the newest automatic migration backup instead of deleting the store:

```bash
python ./scripts/recall_skill.py repair --restore-backup
```

This copies the corrupted `memory.sqlite` aside as `memory.sqlite.corrupt` before restoring, so nothing is silently discarded. For non-corruption drift (a stale or incomplete index), plain `repair` (no flag) rebuilds the index instead.

If hooks don't seem to run, confirm the host provider has trusted/enabled RECALL's bundled hooks (Codex and Claude Code both ask before auto-capture/retrieval hooks run) and that a local Python runtime is on `PATH`.

## Migrating From `.codex_memory/`

Projects with only a legacy `.codex_memory/` store keep working as-is — RECALL reads it for backward compatibility. To move onto the current `.recall/` store and its full feature set (health flags, hygiene, lifecycle ops):

```bash
python ./scripts/recall_skill.py migrate-store          # dry-run plan
python ./scripts/recall_skill.py migrate-store --apply  # perform the migration
```

## Uninstalling

Remove the plugin through the provider's own command, then optionally delete the project-local store:

```bash
codex plugin remove recall@recall-local        # Codex
claude plugin uninstall recall@recall-local    # Claude Code
```

For Kimi Code, open the interactive plugin manager with `/plugins` and remove RECALL from there — Kimi Code's docs don't document a direct uninstall slash-command syntax at this time.

Uninstalling the plugin does not delete stored memory. Remove `.recall/` (and `.codex_memory/` if still present) from a project to delete its RECALL data entirely — this is destructive and not reversible without a prior `export-memory` backup.

## Security Model

RECALL is local-first:

- no hosted RECALL service
- no remote database
- no network calls for storage or retrieval
- common secret-like values are redacted before storage

Treat memory as project data. Do not intentionally store credentials, private keys, access tokens, passwords, or sensitive personal data.

## Maintainer Validation

From the repository root:

```bash
python -m pytest plugins/recall/tests -q
python RECALL_quality_suite/scripts/run_recall_quality_suite.py --repo-root . --quick
python build_plugin.py
python plugins/recall/scripts/smoke_zip_marketplace.py dist/recall.zip --json
```

The v1.3.0 release was validated with plugin tests, quality gates, package inspection, built-zip marketplace smoke, installed-cache smoke, and benchmark runs.
The 2026-06-25 split retest also verified Codex CLI `0.140.0` and Kimi Code
CLI `0.19.2` writing and reading each other's project-local `.recall/` memory
through live hook-injected context.
v1.4.0 (retrieval ranking + local embedder v2) was validated with the full
plugin test suite, blocking lint/type gates, and complete-mode benchmark runs
(package/zip/marketplace smoke not re-run this pass).
v1.5.0 (quality-gate hardening: secret-scanner fix, skill orchestration_fitness
fix, CI bench-light flipped to a blocking gate) was validated with the full
plugin test suite (237/237), blocking lint/type gates, and bench-light CI
green including the newly-blocking benchmark step.

## Release Status

Current stable release: `v1.5.1`

The GitHub release asset is `recall.zip`. Users who install from GitHub should pin `--ref v1.5.1` for a stable install.

## License

See [`LICENSE`](LICENSE).
