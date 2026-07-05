# RECALL 1.2.0 — deterministic memory lifecycle contract

> Handoff ID: `20260705-071753-088`  
> Created: 2026-07-05T07:17:53.089318+00:00  
> Updated: 2026-07-05T07:35:09.450810+00:00  
> Created by: `claude-code`  
> Last updated by: `codex`

## Objective

Make RECALL a dependable, self-enforcing project memory layer for Codex, Claude Code, and Kimi Code: agents retrieve before work, save durable insights only, update/deprecate wrong memory, and keep .recall stores trustworthy without per-session user steering.

## Status

`in_progress`

## Progress

### Done
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
- Read active handoff 20260705-071753-088 and repo state docs.
- Confirmed main had local commit 6e838c8 ahead of origin/main with only untracked .handoff/.
- Ran targeted verification for 1.2.0 contract/MCP/retrieval/hygiene tests: 32 passed.
- Pushed main to GitHub: d972258..6e838c8 main -> main.

### Current
- Work complete and committed locally on main (6e838c8); not pushed to GitHub
- Working tree clean except untracked runtime artifacts; dist/recall.zip rebuilt and verified
- Repo baseline is pushed to origin/main at 6e838c8.
- Working tree still has untracked .handoff/ runtime state only.

### Next
- Push main to GitHub if user wants remote baseline (prior sessions authorized push of baselines, see RECALL memory card #55)
- Optionally tag v1.2.0 and bump downstream marketplace submodule (0langas-plugin-marketplace: plugins.json + .claude-plugin/marketplace.json only — kimi-marketplace.json and .agents/plugins/marketplace.json have no version field)
- Deferred item 1: semantic repo-doc duplication detection in hygiene (medium; today only heuristic route-memory) — next step: token-overlap comparison of memory content vs docs/*.md as review-only proposal
- Deferred item 2: make ageing thresholds configurable (constants: 45d hygiene SNAPSHOT_STALE_DAYS, 30d retrieval SNAPSHOT_AGING_DAYS) via memory_config.json
- Deferred item 3: add ruff/mypy config + CI lint gate (repo has none)
- Deferred item 4: full capture_mode enforcement in hook scripts (pre-existing partial)
- Optionally run PluginEval per-skill judge (--depth standard against each skills/<skill> dir; plugin-level standard silently downgrades to quick)
- Choose next work item: tag v1.2.0 and bump marketplace submodule, or implement deferred semantic repo-doc duplication detection, configurable ageing thresholds, lint/type CI, or fuller capture_mode enforcement.

### Blockers
- _(none)_

## Context

### Important Files
- `plugins/recall/scripts/contract.py`
- `plugins/recall/scripts/kimi_mcp_server.py`
- `plugins/recall/scripts/memory_hygiene.py`
- `plugins/recall/scripts/retrieval.py`
- `plugins/recall/scripts/config.py`
- `plugins/recall/scripts/recall_skill.py`
- `plugins/recall/hooks/scripts/session_start.py`
- `plugins/recall/tests/test_contract_sync.py`
- `plugins/recall/tests/test_mcp_lifecycle_tools.py`
- `plugins/recall/tests/test_retrieval_flags.py`
- `plugins/recall/tests/test_hygiene_quality_checks.py`
- `WORK_STATUS.md`
- `PROJECT_STATE.md`
- `plugins/recall/CHANGELOG.md`

### Constraints
- Local-first: no cloud storage, telemetry, sync, accounts — unchanged and non-negotiable
- Never store secrets; reject at write, redact at storage layer, hygiene-repair legacy stores
- Repo files and user instructions outrank memory (authority order in contract.py)
- Provider-neutral: no Codex-only enforcement; one hooks.json, one MCP server (kimi_mcp_server.py) shared by Claude Code and Kimi via RECALL_DEFAULT_PROVIDER env
- recall_skill.py requires --root BEFORE the subcommand
- Do not declare hooks in .claude-plugin/plugin.json (breaks plugin load with Duplicate hooks file detected)
- Version moves together in 5 places: 3 manifests, kimi_mcp_server.py serverInfo, test_package_metadata.py — parity test enforces manifests
- Local-first: no cloud storage, telemetry, sync, accounts.
- Never store secrets; reject at write and hygiene-repair legacy stores.
- Repo files and current user instructions outrank memory.
- Provider-neutral behavior across Codex, Claude Code, Kimi Code.
- Do not declare hooks in .claude-plugin/plugin.json.

### Decisions
- Seven public skills stay frozen; MCP tool surface is NOT frozen (grew to 8 tools)
- contract.py is single source of truth; skills/docs pinned to it by test_contract_sync.py — edit contract.py first, never patch derived surfaces
- Duplicate-shaped saves confirm the existing card instead of appending (updated_existing result); pre-existing duplicates still surface as hygiene merge proposals
- Preferences require evidence (preference_key + preference_evidence_type explicit_declaration, or durable decision type + decision_id); bare preference saves are ignored with teaching response
- Skill saves declaring hook sources (post_tool_use etc.) are gated by auto-capture policy; test fixtures seed noise via memory_manager.py add instead
- redact_secret is a SAFE hygiene action (privacy outranks review caution); risky deletions stay review-only
- SessionStart injects contract only for activated projects — opt-in quietness preserved
- Committed straight to main matching repo convention

### Open Questions
- Push 6e838c8 to GitHub and tag v1.2.0 now, or hold for more work?
- Bump downstream marketplace submodule now or with the tag?
- Should v1.2.0 be tagged now?
- Should downstream marketplace metadata be bumped now?
- Which deferred item should be tackled next?

## Workspace

### Git Status

```text
## main...origin/main
?? .handoff/
```

### Changed Files
- `.handoff/`

### Commands Run
- `cd plugins/recall && C:/Python312/python.exe -m pytest tests/ -q` — success: Full unit suite (200/200 in ~55s)- `C:/Python312/python.exe -m unittest discover -s RECALL_quality_suite/tests -p test_*.py` — success: Quality suite contract tests (35/35)- `C:/Python312/python.exe scripts/smoke_recall.py --json` — success: End-to-end smoke incl. new SessionStart contract checks- `C:/Python312/python.exe scripts/build_plugin.py --skip-validator --skip-tests --skip-smoke` — success: Package build + inspection; zip verified to contain .claude-plugin/plugin.json and scripts/contract.py- `uv run plugin-eval score .../plugins/recall --depth quick --output json (from 0langas-plugin-marketplace/plugins/plugin-evaluation-kimi)` — success: Static quality gate (90.92 composite, Platinum, zero anti-pattern penalty)- `recall_skill.py --root <repo> save-insight project_state ... --claim-key recall.release.current_version --claim-value 1.2.0` — success: Dogfood: release card #76 saved through RECALL- `git status --short --branch` — unknown: Confirm tracked/untracked state- `git log --oneline --decorate -5` — unknown: Confirm latest baseline commit- `C:\Python312\python.exe -m pytest plugins\recall\tests\test_contract_sync.py plugins\recall\tests\test_mcp_lifecycle_tools.py plugins\recall\tests\test_retrieval_flags.py plugins\recall\tests\test_hygiene_quality_checks.py -q` — unknown: Light verification before push- `git push origin main` — unknown: Push approved baseline to GitHub
### Tests Run
- `python -m pytest tests/ -q (plugins/recall)` — passed: 200/200 — includes 4 new files: contract sync/parity, retrieval flags, hygiene quality checks, MCP lifecycle tools- `python -m unittest discover -s RECALL_quality_suite/tests` — passed: 35/35 — two tests updated to new dedup/secret-reject contract, one new legacy-redaction test- `C:\Python312\python.exe -m pytest plugins\recall\tests\test_contract_sync.py plugins\recall\tests\test_mcp_lifecycle_tools.py plugins\recall\tests\test_retrieval_flags.py plugins\recall\tests\test_hygiene_quality_checks.py -q` — unknown: Targeted contract/MCP/retrieval/hygiene suite
## Capabilities

### Used
- _(none recorded)_

### Required Next
- _(none recorded)_

### Missing at Capture
- _(none)_

## Safety

- Secrets touched: `False`
### Needs User Approval
- git push to GitHub (outward-facing)
- v1.2.0 tag + downstream marketplace submodule bump

## Resume

Resumed active handoff, read active.md content, WORK_STATUS.md, PROJECT_STATE.md, contract.py, key MCP lifecycle tests, contract sync tests, latest commit stats, git status/log, and remote. Confirmed RECALL 1.2.0 implementation commit 6e838c8 was on main and pushed it to origin/main. No code edits made in this session.

**Recommended next provider:** `codex`

### Next Prompt

Continue in C:\Users\Julius\source\repos\RECALL. RECALL 1.2.0 (deterministic memory lifecycle contract) is implemented, verified, and committed locally as 6e838c8 on main — read WORK_STATUS.md (audit, implementation log, verification, deferred items) and PROJECT_STATE.md (architecture map, behavior contract, gates) first. plugins/recall/scripts/contract.py is the single source of truth for agent-facing memory behavior; tests/test_contract_sync.py pins all derived surfaces to it. All gates green: 200/200 unit, 35/35 quality contract, smoke, package build+inspection, PluginEval 90.92 Platinum. Candidate next steps: push to GitHub + tag v1.2.0 + bump marketplace submodule (needs user approval), or pick up a deferred item from WORK_STATUS.md (semantic repo-doc duplication detection in hygiene is the highest-value one). Before release-shaped work, run the gates listed in PROJECT_STATE.md.
