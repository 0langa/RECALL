# PROJECT_STATE — RECALL durable architecture and behavior contracts

Updated: 2026-07-05. Complements WORK_STATUS.md (working log). This file records
durable facts an agent needs across sessions.

## What RECALL is

Local-first project memory for coding agents (Codex, Claude Code, Kimi Code).
One shared per-project store (`.recall/`, legacy `.codex_memory/`), SQLite
default (schema v2) with JSONL alternative, deterministic local 64-D hash
embeddings, no network.

## Architecture map

- `plugins/recall/scripts/` — engine. Key modules:
  - `storage.py` (schema v2: status/trust/confidence/importance/source_*/lineage, FTS5)
  - `memory_manager.py` (public API + CLI), `memory_lifecycle.py` (confirm/
    resolve/stale/prune/supersede/merge), `memory_hygiene.py` (proposals + routing),
    `retrieval.py` (scoring), `write_policy.py` (save gates), `security.py`
    (secret patterns), `config.py` (categories, modes), `contract.py`
    (canonical behavior contract — single source of truth)
  - `kimi_mcp_server.py` — one MCP server for Claude Code AND Kimi;
    provider from `RECALL_DEFAULT_PROVIDER`
  - `recall_skill.py` — skill adapter CLI used by all skills;
    `--root` must come BEFORE subcommand
  - `services/` — context/lifecycle/preference/provenance/recovery/finalizer
- `plugins/recall/hooks/hooks.json` — single hooks file shared by all three
  providers via `${CLAUDE_PLUGIN_ROOT:-$PLUGIN_ROOT}`; Claude Code and Codex
  auto-discover by convention (declaring hooks in Claude manifest BREAKS load)
- `plugins/recall/skills/` — 7 public skills (frozen surface):
  using-recall, retrieve-memory, save-insight, review-memory, manage-memory,
  define-category, memory-hygiene
- Manifests: `.codex-plugin/plugin.json`, `.claude-plugin/plugin.json`,
  `kimi.plugin.json` — versions must move together with
  `kimi_mcp_server.py` VERSION and `tests/test_package_metadata.py`

## Behavior contract (canonical, enforced by scripts/contract.py)

Source authority order (highest first):
1. current user instruction
2. system/developer instructions
3. repository code and docs
4. current tool results
5. RECALL memory
6. older conversation assumptions

Lifecycle: initialize → discover store → retrieve before work → decide
save-worthiness → save durable insight → update changed memory → deprecate/
supersede wrong or stale memory → validate health (hygiene) → handoff summary.

Belongs in memory: durable, project-specific, not derivable from repo docs,
verifiable. Does NOT belong: secrets, raw logs, transient status, drafts,
things repo docs already state, one-off commands.

Memory statuses: hypothesis, active, validated, open, resolved, stale,
superseded, deprecated, archived. Wrong memory must be superseded or
deprecated — never left silently authoritative.

## Non-negotiables

- Local-first: no cloud storage, telemetry, sync, accounts.
- Secret-shaped content rejected at write time (`security.py`) AND scanned
  for in existing stores by hygiene.
- Repo files and explicit user instructions outrank memory.
- Provider-neutral: equivalent guidance for Codex/Claude Code/Kimi;
  no Codex-only enforcement layer.

## Benchmark harness (bench/, maintainer tooling, not shipped)

Deterministic token/quality/latency benchmark: `python bench/run_bench.py run
--mode light|normal|complete` (presets over one config system; custom configs
via --config). Zero LLM calls; judge scoring and Layer-2 agent-compliance
runs are manual (bench/README.md). Baselines in bench/baselines/<version>.json;
compare with --baseline [--strict]. Same seed must reproduce the same
emission_hash. Key outputs: fixed overhead/session, marginal/turn, injection
confusion matrix, golden retrieval, hygiene detection, secret leak sweep.

## Quality gates (run before release)

- Lint: `python -m ruff check .` and `python -m mypy --config-file pyproject.toml` (repo root; blocking in CI)
- Bench: `python -m pytest bench/tests -q` and `python bench/run_bench.py run --mode light --baseline bench/baselines/<latest>.json` (CI job non-blocking for now)
- Unit: `cd plugins/recall && python -m pytest tests/ -x -q`
- Smoke: `python scripts/smoke_recall.py --json`
- Quality suite: `python RECALL_quality_suite/scripts/run_recall_quality_suite.py --repo-root . --quick --skip-existing-unit`
- CI: `.github/workflows/recall-quality.yml` (unit 6-matrix, smoke 3-OS, quality, package)

## Known deferred / future ideas

- Hook payload drift vs live Codex payloads remains a compatibility risk.
- Doc-duplication detection is lexical (token containment vs README/docs
  paragraphs); embedding-based similarity would catch paraphrases.
