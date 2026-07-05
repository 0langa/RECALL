# WORK_STATUS — Lifecycle Quality Implementation Pass (2026-07-05)

Goal: make RECALL a dependable memory layer that guides, enforces, and verifies
memory behavior for Codex, Claude Code, and Kimi Code without per-session user steering.

## BAR 1 — Current-State Audit (DONE)

### How agents can interact with RECALL today

| Surface | Entry points |
|---|---|
| MCP tools (Claude Code + Kimi) | `retrieve_memory`, `context_packet`, `save_insight`, `review_memory`, `initialize_project` (`scripts/kimi_mcp_server.py`) |
| Skill adapter CLI (all providers) | `recall_skill.py`: save-insight, save-turn-card, retrieve-memory, review-memory, audit-memory, initialize-project, define-category, manage-memory (confirm/resolve/stale/supersede/merge/prune/edit/delete/doctor/repair), memory-hygiene (route/scan/plan/apply/reconcile/refresh) |
| Hooks (all providers, shared hooks.json) | SessionStart, UserPromptSubmit (prompt_inspector), PostToolUse, PreCompact, Stop |
| Skills (7, frozen surface) | using-recall, retrieve-memory, save-insight, review-memory, manage-memory, define-category, memory-hygiene |
| Direct CLI | `memory_manager.py` init/add/query/define-category/rebuild-index/doctor/repair |

### Failure model — where behavior depends on "agent just remembers"

1. **Retrieval-before-work not enforced or nudged**: only Kimi auto-loads
   `using-recall` (sessionStart). Codex/Claude Code SessionStart hook outputs
   `{"continue": true}` silently — no contract, no retrieval nudge.
2. **No lifecycle tools on MCP**: update/deprecate/supersede/merge/hygiene not
   callable via MCP. Agents on Claude Code/Kimi can only append (`save_insight`)
   — append-only bias built into the tool surface.
3. **Retrieval output hides health**: stale/superseded/deprecated status only in
   `metadata["status"]`; no flags, no conflict marking, no "verify before trust".
4. **Category selection pure goodwill**: 12 categories defined only as
   name+description+weight; no examples/non-examples/update rules exposed;
   real stores show dumping (85% `commands` in `.codex_memory_old`,
   76–79% `project_state` in sibling repos).
5. **Save responses don't teach**: near-duplicate found → silently linked;
   no "update existing #N instead" instruction back to the agent.
6. **capture_mode / recall_mode config values not enforced in code.**
7. **Hygiene gaps**: no secret scan of *existing* store, no raw-log/vague
   detection, no stale project_state-snapshot ageing, no repo-doc duplication check.
8. **Provider drift risks**: 3 hand-maintained manifests; version pinned in 5
   files with no parity test; `.claude-plugin` **missing from build_plugin.py
   INCLUDE** (packaged zip would ship without Claude Code manifest);
   `inspect_package.py` doesn't require `.claude-plugin/plugin.json`.
9. **Contract only in markdown**: `skills/using-recall/references/contract.md`
   defines authority order + save/skip, but nothing programmatic exposes it;
   MCP `instructions` don't carry it; no test keeps docs and code aligned.

### Real-store quality evidence

- `.codex_memory_old` (796 records): 85% `commands`; 51× duplicate
  `git status --short --branch`; 46-char "git push completed" cards.
- Current `.codex_memory` (73): healthier but 27% commands; hook-injected
  curated memory still contains raw chat fragments with mojibake (cards #52, #57).
- Sibling repos: near-everything dumped into `project_state`.
- No secrets found in any store (patterns work at write time).

### Current lifecycle (as implemented)

init (`activate_project`) → hooks capture (post_tool_use/pre_compact/stop with
write_policy gates: fingerprint dedup, low-signal filter, near-dup ≥0.72 link)
→ retrieve (vector+lexical+importance×category/status/source weights) →
lifecycle ops (confirm auto-promotes hypothesis→active→validated; supersede;
merge; stale; prune) → hygiene proposals (merge/supersede/stale/prune/
needs_confirmation/refresh_source; `--safe` apply) → doctor/repair.

## Plan (BARS 2–10)

1. **Canonical contract module** `scripts/contract.py`: authority order,
   lifecycle steps, save/skip rules, retrieval triggers, category slots.
   Single source consumed by MCP server instructions, session_start hook
   context injection, `recall_skill.py contract` command, and tests that
   pin skills/docs to it. (BAR 2, 7)
2. **Category enrichment** in `config.py`: examples, non_examples, update_rule
   per category; add `tooling_quirks` + `integrations` categories; expose via
   `define-category --list` and contract. Hygiene check for category dumping /
   mismatch. (BAR 3)
3. **Retrieval health flags**: per-result `flag` (current/stale/deprecated/
   superseded/needs_verification/conflicting) + response header counts +
   `next_action` hints. (BAR 4)
4. **Save teaches update**: near-duplicate → response instructs update/confirm
   of existing id; new MCP tool `update_memory` (op-based lifecycle) and
   `memory_hygiene` (scan/plan/apply-safe/route). (BAR 5, 8)
5. **Hygiene extensions**: stored-secret scan, raw-log detection, vague-memory
   detection, stale project_state snapshot ageing, missing-metadata check;
   concrete repair actions in output. (BAR 6)
6. **Provider sync**: fix `build_plugin.py` INCLUDE (+`.claude-plugin`),
   `inspect_package.py` required paths, parity test pinning version across
   3 manifests + server + metadata test; session_start injects contract
   nudge for Codex/Claude Code parity with Kimi sessionStart. (BAR 7)
7. **Init upgrades**: `activate_project` ensures `.gitignore` entries, enriched
   categories, returns first-workflow guidance; legacy-store validation. (BAR 9)
8. **Tests + fixtures** for all above; run unit suite + smoke + quality gates. (BAR 10)

## Progress log

- 2026-07-05: audits complete (3 parallel agents), plan recorded.
- 2026-07-05: implementation complete — v1.2.0.
  - `scripts/contract.py` canonical contract; consumed by MCP `instructions`,
    `memory_contract` tool, SessionStart hook, `recall_skill.py contract`,
    pinned to skills/docs by `tests/test_contract_sync.py`.
  - Categories enriched (examples/non-examples/update rules) + `tooling_quirks`
    + `integrations`; guidance fields survive `validate_config` and are
    settable via `define-category --example/--non-example/--update-rule`.
  - Retrieval health flags + `health.next_action`; conflict marking.
  - MCP: `update_memory`, `memory_hygiene`, `memory_contract` tools added;
    `save_insight` rejects secrets, dedups, and teaches recovery; preference
    evidence fields exposed. Adapter `save-insight` same dedup+teach.
  - Hygiene: `redact_secret` (safe, top priority), raw-log prune, vague review,
    45-day snapshot ageing, missing-provenance review; scan `next_action`.
  - Init: `.gitignore` coverage + contract + first-workflow on both surfaces.
  - Provider sync: `.claude-plugin` added to build INCLUDE + package inspection;
    manifest version/name/skills parity test; all versions bumped to 1.2.0.
  - SessionStart hook injects compact contract + store overview for activated
    projects (quiet otherwise); smoke harness covers both paths.

## Verification (2026-07-05)

- Unit suite: 200/200 pass (`python -m pytest tests/ -q`, plugins/recall).
- Quality suite contract tests: 35/35 pass.
- Smoke harness: pass (includes new SessionStart checks).
- Package build + inspection: pass; zip contains `.claude-plugin/plugin.json`
  and `scripts/contract.py`.
- PluginEval static: 90.92 composite, Platinum, no anti-pattern penalty.
- Not run: PluginEval per-skill judge (codex-backed, slow; frozen skill surface
  unchanged in triggering shape), CI matrix (runs on push).

## Batch 2 plan (2026-07-05, user-aligned) — clear all deferred items → v1.3.0

User decisions: docs corpus = README + docs/ only; doc-dup = review-only proposal;
token diet = compact outputs by default (full metadata behind verbose); capture_mode
mapping = standard current / minimal no per-tool buffering but Stop summary /
manual explicit cues only / off no hook capture (skill+MCP saves stay explicit);
ruff blocking + lenient mypy blocking; 4 separate commits; hold push.

1. Commit 1: `_doc_duplicate_proposals` in memory_hygiene — paragraph-level token
   containment vs README.md + docs/**/*.md, review_doc_duplicate (unsafe), corpus
   cached + size-capped, detection fully local (no LLM). Tests with fixture docs.
2. Commit 2: `staleness` config block (snapshot_stale_days, retrieval_aging_days);
   retrieval compact-by-default + `verbose` flag through retrieval/manager/MCP/
   adapter; hygiene proposal list cap + omitted count; session-start injection cap.
3. Commit 3: ruff config + lenient mypy config at repo root, fix findings, CI lint
   job, gate commands documented.
4. Commit 4: capture_mode enforcement in post_tool_use/pre_compact/stop/
   prompt_inspector; per-mode tests; version bump 1.3.0 (5 places), CHANGELOG,
   docs; full gates + PluginEval.

## Deferred (with reasons)

1. Semantic repo-doc duplication detection — severity: medium; component:
   memory_hygiene; risk: memory duplicating README/docs undetected unless
   routed through route-memory; deferral: needs a docs-corpus similarity pass,
   design decision on false positives; next step: token-overlap comparison of
   memory content vs docs/*.md with a review-only proposal.
2. Configurable ageing thresholds (45d hygiene / 30d retrieval flag constants)
   — severity: low; component: memory_hygiene/retrieval; next step: read from
   memory_config.json `staleness` block.
3. Lint/type CI gate (no ruff/mypy config in repo) — severity: low; next step:
   add ruff config + CI job.
4. capture_mode enforcement inside hook scripts remains partial (pre-existing)
   — severity: low-medium; component: hooks; next step: gate post_tool_use
   capture on capture_mode value.
