# WORK_STATUS — Lifecycle Quality Implementation Pass (2026-07-05)

## Batch 3 plan — RECALL benchmark/eval system (user-aligned 2026-07-05)

Goal: measure token cost, quality, latency, and agent compliance of RECALL,
provider-local, deterministic core with optional (never auto-run) LLM judging.

User decisions: full build in one pass; live LLM judging NEVER executed by the
building agent (deliver judge system + manual run instructions); CI light-mode
job non-blocking first; v1.3.0 pushed+tagged first (done, marketplace bumped).

Architecture (repo-root `bench/`, NOT shipped in plugin zip):
- Layer 1 (engine, deterministic): scenario turn scripts drive real hooks via
  stdin JSON + MCP server via stdio JSON-RPC + adapter CLI; recorder journals
  every agent-visible emission tagged by channel taxonomy (from
  token_usage_surfaces.md); metrics engine computes token/quality/latency/
  consistency; JSON+markdown reports; baselines + delta thresholds.
- Layer 2 (agent compliance, opt-in): sandboxed fixture project + task set;
  calling agent is the test subject; graded by artifacts (store diff, debug
  traces, emission journal) against per-task rubrics; tasks never reveal
  expected RECALL behavior.
- Judge (opt-in, two-phase): harness emits judge_tasks.jsonl from a recorded
  run; any agent scores them; harness validates + aggregates. No API calls.
- Modes = presets over one config system: light (<~30s), normal, complete.
- Token estimator: local heuristic consistent with summarizer; absolute
  accuracy secondary, version-over-version deltas primary.
- Store tiers: fresh / working (~50) / mature (~500); legacy tier = optional
  user-supplied old store path.

Key metrics per mode: see conversation lists (fixed-vs-marginal token split,
injection confusion matrix, retrieval P/R@k + flag correctness, dedup rates,
hygiene detection/FP, secret leak sweep, latency p50/p95, determinism hash,
long-run growth curves).

Batch 3 status (2026-07-05): BUILT. `bench/` with recall_bench package
(channels/tokens/recorder/drivers/store_fabricator/scenarios/engine/probes/
metrics/baseline/report/judge/compliance), 5 scenario scripts, 3 presets,
10 compliance tasks, 14 harness unit tests, CI bench-light non-blocking job,
baseline bench/baselines/v1.3.0.json. Determinism verified (same seed ==
same emission hash). Judge emission verified file-only; LLM judging never
executed here per user instruction — manual instructions in bench/README.md.

FINDING FIXED DURING BUILD: read-path secret leak. Write path redacts, but
retrieval and review emitted raw secret-shaped content from legacy stores
verbatim. First normal-mode bench run caught it (3 leaks). Fixed in
retrieval.query (redact content + metadata on emit) and memory_review
compact_text; pinned by test_retrieval_flags::test_raw_secrets_in_legacy_
store_are_redacted_on_read. Leak sweep now CLEAN.

Bench fabrication artifacts fixed: now-relative deterministic timestamps
(FIXED_EPOCH aged every fabricated snapshot past the 45d window → hygiene
false positives), injection-gate labels restricted to session 1 of normal
scenarios (from session 2 on the store has legitimately learned repeated
prompts; long-run replays excluded entirely), flag probes use limit 20
(retired-status score penalties bury superseded cards below top-10 by
design), golden preference card carries explicit_declaration evidence.

SECOND ENGINE FINDING FIXED: hygiene demanded decision_id for every
preference while the write contract (preference_service) accepts
explicit_declaration without one — legitimately saved explicit preferences
were flagged needs_confirmation forever. Aligned _preference_proposal with
the write contract; pinned by test_explicit_declaration_preference_needs_
no_decision_id.

v1.3.0 baseline numbers (bench/baselines/v1.3.0.json, seed 1337):
fixed overhead 5752 est tokens/session; marginal 236.1 est tokens/turn;
20-turn session ≈ 10474 est tokens ≈ $0.031 at $3/M input. Retrieval golden
hit rate 1.0 (MRR 1.0); flag correctness 1.0; conflict marking correct;
dedup + secret rejection + safe-apply redaction all pass; leak sweep CLEAN;
hygiene detection 6/7 (the exact-duplicate PAIR yields one merge proposal —
the kept primary is correctly not proposed; known probe accounting).

FINDING CLOSED (2026-07-05): injection gate accuracy 0.684 → 0.895.
Root cause was NOT same-session re-injection (initial hypothesis) but
relevance-gate laxity: unfiltered stopword overlap ("the/into/five") plus
hash-embedding noise plus ≥1.3× category weights let generic cards cross the
threshold on unrelated prompts, and diluted genuinely matching ones. Fixes:
1. Stopword-filtered + naively-singularized lexical overlap in the GATE only
   (retrieval.gate_tokens / normalized_lexical_overlap); ranking untouched.
2. Session-recency suppression in automatic injection (session_context.
   drop_session_records; prompt_inspector passes exclude_session_id unless
   explicit @recall) — correct belt even though it wasn't the driver.
   Tests: tests/test_session_recency.py (4).
3. Two scenario labels corrected (virgin-store statement prompt; release-build
   prompt where injecting release requirements is genuinely useful).
Tried and REVERTED: best-of-top-3 gate candidate selection — fixed nothing,
reintroduced weak rank-2/3 matches (0.895 → 0.789). Keep gate on rank-1.
Remaining honest mismatches (2/19): one weak-match false inject ("run the
integration suite" pulls a test-fixture card), one false suppress
(feature_work footer prompt; golden card outranked by filler at rank 1 —
structural rank-vs-relevance gap, only fixable with better embeddings).


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

1. DONE (e773c24): `_doc_duplicate_proposals` in memory_hygiene — paragraph-level
   token containment vs README.md + docs/**/*.md, review_doc_duplicate (unsafe),
   corpus size-capped, detection fully local (no LLM). Tests with fixture docs.
2. DONE (011a07d): `staleness` config block (snapshot_stale_days=45,
   retrieval_aging_days=30); retrieval compact-by-default on agent surfaces
   (`verbose` opt-in; library callers keep full metadata); hygiene-scan caps
   listed proposals at 20 with omitted count; session-start injection capped
   at ~2000 chars.
3. DONE (902c9e2): pyproject.toml with ruff (E4/E7/E9/F/B) + lenient mypy over
   engine scripts, both blocking; all pre-existing findings fixed; CI lint job.
4. DONE: capture_mode enforced in hooks — standard full; minimal no per-tool
   buffering (PostToolUse standard-only via TOOL_CAPTURE_MODES), pre_compact
   session summaries now standard+minimal; manual explicit-cues-only (prompt
   auto-signals gated); off blocks all hook capture incl. explicit cues with a
   re-enable hint (skill/MCP saves unaffected; recall_mode governs retrieval).
   tests/test_capture_modes.py (8 tests). Version 1.3.0 in all 5 places.

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
