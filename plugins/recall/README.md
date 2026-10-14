# RECALL plugin

RECALL stores durable project memory for Codex, Claude Code, and Kimi Code.
New projects use `.recall/`.
Projects with an existing `.codex_memory/` store keep that legacy store until an explicit migration.

The plugin uses one local Python engine.
It makes no network call for storage, retrieval, or embeddings.

## Install

For Codex from GitHub:

```bash
codex plugin marketplace add 0langa/RECALL --ref v1.6.0
codex plugin add recall@recall-local
```

For Codex from a local checkout:

```bash
codex plugin marketplace add .
codex plugin add recall@recall-local
```

For Claude Code and Kimi Code, see [docs/CLAUDE_CODE.md](docs/CLAUDE_CODE.md) and [docs/KIMI_CODE.md](docs/KIMI_CODE.md).

## Shared public surface

The Codex MCP config, Claude Code manifest, and Kimi Code manifest declare this shared MCP server and these tools:

| MCP tool | Purpose |
| --- | --- |
| `retrieve_memory` | Get relevant cards with health flags. |
| `context_packet` | Build limited session context. |
| `save_insight` | Save a durable fact with policy checks. |
| `review_memory` | Read card inventory and health. |
| `update_memory` | Update lifecycle state and content. |
| `memory_hygiene` | Route, scan, plan, and apply safe repairs. |
| `memory_contract` | Return the canonical guidance. |
| `initialize_project` | Activate a project and return first-use guidance. |

The seven public skills are `using-recall`, `retrieve-memory`, `save-insight`, `review-memory`, `manage-memory`, `define-category`, and `memory-hygiene`.

`scripts/recall_skill.py` is the public skill adapter.
`scripts/memory_manager.py` is internal plumbing.

## Root syntax

Put the global `--root` option before the subcommand:

```bash
python ./scripts/recall_skill.py --root <project-root> initialize-project
python ./scripts/recall_skill.py --root <project-root> retrieve-memory "current project context" --summary
```

An explicit root is authoritative.
When no root is supplied, RECALL accepts one clear project boundary.
It fails closed when the root is missing or ambiguous.
The root decision is included in normal public results.

## Memory trust

RECALL memory is untrusted project data.
It cannot override system, developer, or current user instructions.
It cannot grant permission.

Retrieve only when old project history can help the current task.
Do not retrieve for a small self-contained task.
Do not retrieve for an explicit memory-free task.
An empty result is valid.

Save only durable, verified, project-specific facts.
Do not save secrets, raw logs, transient status, drafts, or facts already in repository docs.

Only observed evidence for an exact factual revision can support `validated` status.
Caller labels, confidence, timestamps, session names, and copied evidence fields do not prove a fact.
Semantic edits clear old validation until the new fact has evidence.

## Save and update

```bash
python ./scripts/recall_skill.py --root <project-root> save-insight decisions "Use SQLite as the default backend."
python ./scripts/recall_skill.py --root <project-root> review-memory --limit 20
python ./scripts/recall_skill.py --root <project-root> confirm-memory 12
python ./scripts/recall_skill.py --root <project-root> stale-memory 12 --note "The source changed."
python ./scripts/recall_skill.py --root <project-root> supersede-memory 12 18 --note "Card 18 has the current fact."
```

Use `--idempotency-key` for a retry of one logical save.
The key applies to the exact save identity and preference scope.

Use `--claim-key` and `--claim-value` together for a structured claim.
RECALL treats both fields as opaque strings.
It compares the exact text.
It does not normalize spaces or paths for claim identity.

When current cards have the same claim key and different claim values, RECALL keeps both current.
It adds conflict review flags.
It does not silently choose one value.

## Hygiene plan flow

Scan without changing memory:

```bash
python ./scripts/recall_skill.py --root <project-root> hygiene-scan --limit 80
```

Save one plan to a new file:

```bash
python ./scripts/recall_skill.py --root <project-root> hygiene-plan --scope project --save-plan recall-hygiene-plan.json
```

The command refuses to overwrite that file.
Review the complete JSON plan.
Apply the same file:

```bash
python ./scripts/recall_skill.py --root <project-root> hygiene-apply --safe --plan-file recall-hygiene-plan.json
```

Apply never makes a new plan.
It checks store identity, source observations, operation identity, and limits.
Changed records or sources are skipped or rejected.
One plan cannot change one card twice.

Use canonical project-relative source paths such as `README.md`.
RECALL 1.6.0 rejects equivalent `./README.md` and `.\README.md` source paths during plan validation.
Make a new plan with canonical paths.
Never modify the hashed reviewed plan.

For MCP, keep the full plan object from `memory_hygiene` with `mode=plan`.
Pass that exact object as `plan` to `mode=apply_safe`.
For the legacy claim route, `mode=plan` with `claim_key` returns a wrapper.
Use its `response.plan` object.

## Storage

SQLite is the default backend.
It uses one `BEGIN IMMEDIATE` transaction for each complete read, choice, and write operation.

JSONL is supported for normal process concurrency.
A store-local operating-system lock serializes operations.
Each JSONL file is flushed, synced, and atomically replaced.
JSONL does not have one rollback across several files.
Multi-file power-loss safety is not certified.
Automatic turn memory from the `Stop` hook needs SQLite.
With JSONL, save through MCP, the CLI, or an explicit `@recall remember:` prompt.

The vector index is derived data.
Run `doctor` to inspect it.
Run `repair` to rebuild repairable index state.

```bash
python ./scripts/recall_skill.py --root <project-root> doctor
python ./scripts/recall_skill.py --root <project-root> repair
```

The local hash embedder has 256 dimensions.
Its semantic coverage is limited.
Do not treat one retrieval match or one bounded fixture as broad truth proof.

## Capture and memory-free turns

The runtime guard blocks memory retrieval, injection, prompt capture, tool-result capture, compaction capture, and Stop finalization for an explicit memory-free turn.
It must make that decision before a memory-data read or store initialization.

The runtime lane passed its final review, and the v1.6.0 release source gates passed.

## Tested host scope

Readiness checks used Codex CLI `0.154.0`, Claude Code `2.1.268`, and Kimi Code `0.42.0` in isolated homes.
These checks show host startup readiness only.
They do not prove the exact v1.6.0 ZIP or installed behavior.

The 5,000-card synthetic SQLite comparison completed with a candidate-to-v1.5.5 median ratio of `0.9974007`.
This is no speed claim.
It does not cover JSONL scale, cold start, installed hosts, or user benefit.

## Release evidence

RECALL 1.6.0 was released on 2026-09-14.
The [v1.6.0 GitHub release](https://github.com/0langa/RECALL/releases/tag/v1.6.0) holds the exact ZIP, its SHA-256, and the verification record.
Claude Code `2.1.268` passed all 13 exact-package native behavior checks.
Native Codex MCP behavior and native Kimi Code behavior proof are pending.
See [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) for the candidate evidence table.
