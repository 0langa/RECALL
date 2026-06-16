# RECALL

Local-first project memory for Codex.

RECALL is a Codex plugin that gives agents durable project context without sending memory to a hosted service. It stores decisions, requirements, risks, commands, debugging history, and session summaries inside the active project under `.codex_memory/`, then retrieves relevant context in later Codex sessions.

The installable plugin lives in [`plugins/recall`](plugins/recall/). This repository is also a Codex plugin marketplace, so Codex can install RECALL directly from GitHub.

## What RECALL Does

- Keeps memory local to each project in `.codex_memory/`.
- Retrieves relevant project context when you invoke `@recall`.
- Captures explicit "remember this" requests and useful development outcomes.
- Stores structured memory categories such as `decisions`, `requirements`, `risks`, `commands`, and `debug_history`.
- Supports review, confirmation, supersession, merge, and archival of memory cards.
- Uses SQLite by default, with JSONL storage available through config.
- Builds and validates as a portable Codex plugin zip on Windows, macOS, and Linux.

RECALL does not use a hosted database or network embedding service. It is designed as a local project assistant, not a team memory server.

## Install From GitHub

Requires Codex CLI with plugin marketplace support and a local Python runtime.

```bash
codex plugin marketplace add 0langa/RECALL --ref v1.0.0
codex plugin add recall@recall-local
```

Then open Codex in a project and invoke:

```text
@recall initialize this project
```

Codex may ask you to review and trust the bundled RECALL hooks before automatic memory capture and retrieval run.

## Install From A Local Checkout

```bash
git clone https://github.com/0langa/RECALL.git
cd RECALL
codex plugin marketplace add .
codex plugin add recall@recall-local
```

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

More usage and support commands are documented in [`plugins/recall/README.md`](plugins/recall/README.md) and [`plugins/recall/docs/INSTALL.md`](plugins/recall/docs/INSTALL.md).

## Storage

RECALL writes runtime data to the active project:

```text
.codex_memory/
  memory_config.json
  memory.sqlite
```

`.codex_memory/` should stay out of source control. This repository ignores it by default.

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

The v1.0.0 release was validated with the plugin test suite, quality suite, package inspection, built-zip marketplace smoke test, installed-cache smoke test, and a real project field test.

## Release Status

Current stable release: `v1.0.0`

The GitHub release asset is `recall.zip`. Users who install from GitHub should pin `--ref v1.0.0` for a stable install.

## License

See [`LICENSE`](LICENSE).
