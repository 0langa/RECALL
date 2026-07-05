# Continuation Prompt — Claude Code

You are resuming work previously captured by another agent. Use Claude Code tools (`git`, `read`, `edit`, `bash`, etc.) as needed. Prefer shell and git inspection for workspace state.

## Task

**RECALL 1.2.0 — deterministic memory lifecycle contract**

Status: `in_progress`

### Objective

Make RECALL a dependable, self-enforcing project memory layer for Codex, Claude Code, and Kimi Code: agents retrieve before work, save durable insights only, update/deprecate wrong memory, and keep .recall stores trustworthy without per-session user steering.

## What Was Done

- Audited engine, provider surfaces, tests, and real .codex_memory stores (failure model in WORK_STATUS.md: legacy store 85% commands bloat, category dumping in sibling repos, append-only MCP bias)
- Created plugins/recall/scripts/contract.py — canonical contract: source authority order, lifecycle steps, save/skip rules, status meanings
- Exposed contract via MCP initialize instructions, memory_contract tool, SessionStart hook additionalContext, recall_skill.py contract command
- Added MCP tools update_memory (update/confirm/stale/deprecate/supersede/merge/resolve/prune) and memory_hygiene (route/scan/plan/apply_safe)
- MCP save_insight: secret rejection (was silent redaction), dedup via add_record_if_useful (was raw append), teaching responses, preference evidence fields on schema
- Adapter save-insight: same dedup-and-teach behavior
- Retrieval health flags per result + health summary with next_action + conflict marking across claim keys
- Hygiene: redact_secret (safe, top priority), raw-log prune, review_vague, 45d snapshot ageing to stale, review_metadata for missing provenance, scan next_action
- Categories: examples/non-examples/update rules on all 12 built-ins, preserved through validate_config; added tooling_quirks + integrations; define-category --example/--non-example/--update-rule
- initialize-project ensures .gitignore covers .recall/ and .codex_memory/, returns categories+contract+first-workflow (both MCP and adapter)
- SessionStart hook injects compact contract + store overview for activated projects, quiet otherwise; smoke covers both
- Fixed .claude-plugin missing from build_plugin.py INCLUDE; inspect_package.py requires .claude-plugin/plugin.json + scripts/contract.py
- Manifest parity tests (version/name/skills-path across 3 manifests + MCP serverInfo)
- Versions bumped to 1.2.0 in all 5 pinned places
- Updated SKILL.md files (retrieve-memory, save-insight, memory-hygiene, using-recall, define-category), contract.md reference, CHANGELOG, both READMEs, CLAUDE_CODE.md, KIMI_CODE.md
- 4 new test files: test_contract_sync.py, test_retrieval_flags.py, test_hygiene_quality_checks.py, test_mcp_lifecycle_tools.py
- Committed 6e838c8; saved release card #76 through RECALL itself (claim-keyed recall.release.current_version=1.2.0)

## What Is In Progress

- Work complete and committed locally on main (6e838c8); not pushed to GitHub
- Working tree clean except untracked runtime artifacts; dist/recall.zip rebuilt and verified

## Next Steps

- Push main to GitHub if user wants remote baseline (prior sessions authorized push of baselines, see RECALL memory card #55)
- Optionally tag v1.2.0 and bump downstream marketplace submodule (0langas-plugin-marketplace: plugins.json + .claude-plugin/marketplace.json only — kimi-marketplace.json and .agents/plugins/marketplace.json have no version field)
- Deferred item 1: semantic repo-doc duplication detection in hygiene (medium; today only heuristic route-memory) — next step: token-overlap comparison of memory content vs docs/*.md as review-only proposal
- Deferred item 2: make ageing thresholds configurable (constants: 45d hygiene SNAPSHOT_STALE_DAYS, 30d retrieval SNAPSHOT_AGING_DAYS) via memory_config.json
- Deferred item 3: add ruff/mypy config + CI lint gate (repo has none)
- Deferred item 4: full capture_mode enforcement in hook scripts (pre-existing partial)
- Optionally run PluginEval per-skill judge (--depth standard against each skills/<skill> dir; plugin-level standard silently downgrades to quick)

## Blockers

- _(none)_

## Workspace State

Git status:

```text
## main...origin/main [ahead 1]
?? .handoff/
```

Changed files:
- `.handoff/`

Tests run:
- `python -m pytest tests/ -q (plugins/recall)` — passed: 200/200 — includes 4 new files: contract sync/parity, retrieval flags, hygiene quality checks, MCP lifecycle tools- `python -m unittest discover -s RECALL_quality_suite/tests` — passed: 35/35 — two tests updated to new dedup/secret-reject contract, one new legacy-redaction test
## Important Context

- File: `plugins/recall/scripts/contract.py`
- File: `plugins/recall/scripts/kimi_mcp_server.py`
- File: `plugins/recall/scripts/memory_hygiene.py`
- File: `plugins/recall/scripts/retrieval.py`
- File: `plugins/recall/scripts/config.py`
- File: `plugins/recall/scripts/recall_skill.py`
- File: `plugins/recall/hooks/scripts/session_start.py`
- File: `plugins/recall/tests/test_contract_sync.py`
- File: `plugins/recall/tests/test_mcp_lifecycle_tools.py`
- File: `plugins/recall/tests/test_retrieval_flags.py`
- File: `plugins/recall/tests/test_hygiene_quality_checks.py`
- File: `WORK_STATUS.md`
- File: `PROJECT_STATE.md`
- File: `plugins/recall/CHANGELOG.md`

- Decision: Seven public skills stay frozen; MCP tool surface is NOT frozen (grew to 8 tools)
- Decision: contract.py is single source of truth; skills/docs pinned to it by test_contract_sync.py — edit contract.py first, never patch derived surfaces
- Decision: Duplicate-shaped saves confirm the existing card instead of appending (updated_existing result); pre-existing duplicates still surface as hygiene merge proposals
- Decision: Preferences require evidence (preference_key + preference_evidence_type explicit_declaration, or durable decision type + decision_id); bare preference saves are ignored with teaching response
- Decision: Skill saves declaring hook sources (post_tool_use etc.) are gated by auto-capture policy; test fixtures seed noise via memory_manager.py add instead
- Decision: redact_secret is a SAFE hygiene action (privacy outranks review caution); risky deletions stay review-only
- Decision: SessionStart injects contract only for activated projects — opt-in quietness preserved
- Decision: Committed straight to main matching repo convention

- Constraint: Local-first: no cloud storage, telemetry, sync, accounts — unchanged and non-negotiable
- Constraint: Never store secrets; reject at write, redact at storage layer, hygiene-repair legacy stores
- Constraint: Repo files and user instructions outrank memory (authority order in contract.py)
- Constraint: Provider-neutral: no Codex-only enforcement; one hooks.json, one MCP server (kimi_mcp_server.py) shared by Claude Code and Kimi via RECALL_DEFAULT_PROVIDER env
- Constraint: recall_skill.py requires --root BEFORE the subcommand
- Constraint: Do not declare hooks in .claude-plugin/plugin.json (breaks plugin load with Duplicate hooks file detected)
- Constraint: Version moves together in 5 places: 3 manifests, kimi_mcp_server.py serverInfo, test_package_metadata.py — parity test enforces manifests

- Open question: Push 6e838c8 to GitHub and tag v1.2.0 now, or hold for more work?
- Open question: Bump downstream marketplace submodule now or with the tag?

## Capability Warnings


## Safety Notes

- Requires user approval: git push to GitHub (outward-facing)
- Requires user approval: v1.2.0 tag + downstream marketplace submodule bump

## Resume Summary

Full implementation pass shipped as v1.2.0, commit 6e838c8 on main (local, not pushed). Added canonical behavior contract module (plugins/recall/scripts/contract.py) exposed via MCP server instructions, new memory_contract MCP tool, SessionStart hook injection, and adapter `contract` command; pinned to skills/docs by tests. MCP surface grew from 5 to 8 tools (added update_memory lifecycle ops and memory_hygiene route/scan/plan/apply_safe). Saves now reject secrets on every surface, dedup at write time (exact duplicate confirms existing card instead of appending), and return teaching next_action responses. Retrieval results carry health flags (current/stale/superseded/deprecated/needs_verification/conflicting) plus health.next_action. Hygiene detects stored secrets (safe in-place redaction), raw log dumps, vague cards, 45-day aged snapshots, missing provenance. Categories enriched with examples/non-examples/update rules; added tooling_quirks and integrations. Fixed .claude-plugin missing from build packaging. Added manifest parity tests. All gates green.

Continue in C:\Users\Julius\source\repos\RECALL. RECALL 1.2.0 (deterministic memory lifecycle contract) is implemented, verified, and committed locally as 6e838c8 on main — read WORK_STATUS.md (audit, implementation log, verification, deferred items) and PROJECT_STATE.md (architecture map, behavior contract, gates) first. plugins/recall/scripts/contract.py is the single source of truth for agent-facing memory behavior; tests/test_contract_sync.py pins all derived surfaces to it. All gates green: 200/200 unit, 35/35 quality contract, smoke, package build+inspection, PluginEval 90.92 Platinum. Candidate next steps: push to GitHub + tag v1.2.0 + bump marketplace submodule (needs user approval), or pick up a deferred item from WORK_STATUS.md (semantic repo-doc duplication detection in hygiene is the highest-value one). Before release-shaped work, run the gates listed in PROJECT_STATE.md.
