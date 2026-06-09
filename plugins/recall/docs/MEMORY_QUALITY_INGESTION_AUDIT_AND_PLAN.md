# RECALL Memory Quality Ingestion Audit And Plan

Date: 2026-06-09
Branch: `cdx/recall-memory-quality-audit-plan`

## Goal

Reduce RECALL's memory noise at the ingestion layer while making stored memory more useful, auditable, and durable across real Codex work. The target is not "better retrieval over junk." The target is a write policy that only admits high-value memory by default, keeps background hooks quiet, and preserves performance as memory volume grows.

## Executive Summary

The core issue is ingestion policy. RECALL's hook integration is reliable enough to expose the problem: hooks fire for every Codex turn and every matched tool use, whether the user explicitly invoked RECALL or not. Current `PostToolUse` behavior captures too many successful commands, and `Stop` stores too many generic final messages as `project_state`.

Live memory inventory from this repository on 2026-06-09 showed:

- `521` total active records.
- `477` `commands` records.
- `29` `debug_history` records.
- `15` `project_state` records.
- `506` records from `post_tool_use`.
- `15` records from `stop`.
- `425` command records with generic summary `Bash result captured.`
- `0` records with relationship or confirmation metadata.

That confirms the user's signal-to-noise concern. RECALL has useful lifecycle, retrieval, and review primitives, but automatic hook writes are overwhelming the store before those primitives can matter.

## Audit Scope

Reviewed:

- Plugin manifest and hooks: `plugins/recall/.codex-plugin/plugin.json`, `plugins/recall/hooks/hooks.json`.
- Hook scripts: `prompt_inspector.py`, `post_tool_use.py`, `pre_compact.py`, `stop.py`, `session_start.py`, `hook_io.py`.
- Backend scripts: `memory_manager.py`, `write_policy.py`, `memory_hygiene.py`, `memory_lifecycle.py`, `memory_review.py`, `retrieval.py`, `storage.py`, `index_store.py`, `config.py`, `session_context.py`, `recall_skill.py`.
- Tests: plugin unit tests and the untracked `RECALL_quality_suite`.
- Existing docs: V1 completion plan, E2E log, release checklist, memory lifecycle plan, quality-suite memory evolution plan.
- Live project memory store through `recall_skill.py review-memory`.

Validation/evaluation run:

- `python -m unittest discover -s plugins\recall\tests` passed: 73 tests.
- `python RECALL_quality_suite\scripts\run_recall_quality_suite.py --repo-root . --quick --skip-performance` passed.
- `node ...\plugin-eval\local\scripts\plugin-eval.js analyze .\plugins\recall --format markdown` scored `77/100`, grade `C`.
- `python RECALL_quality_suite\perf\benchmark_recall_memory.py --plugin-root plugins\recall --records 120 --queries 10` passed quick thresholds.

Unavailable requested tools:

- `audit-context-building` was not available in the active plugin list.
- `brooks-lint` was not available in the active plugin list.

## Architecture Map

Current write flow:

1. `hooks/hooks.json` registers `UserPromptSubmit`, `PostToolUse`, `PreCompact`, `Stop`, and `SessionStart`.
2. `prompt_inspector.py` writes explicit `remember this:` prompts to `preferences`.
3. `post_tool_use.py` compacts tool output and writes `commands` or `debug_history`.
4. `pre_compact.py` writes `session_summaries`.
5. `stop.py` writes `project_state`.
6. `memory_manager.add_record_if_useful()` redacts content, asks `write_policy.classify_write()`, then writes through storage and appends the vector index.
7. `write_policy.py` can ignore a few low-signal commands and generic checkpoints, update exact duplicates, link near duplicates, and process explicit supersession cues.
8. `SessionStart` uses `session_context.py` to retrieve curated active memory and inject `hookSpecificOutput.additionalContext`.

Good existing foundations:

- Explicit user memory cues are stricter than before.
- Storage is local-first and stdlib-only.
- Structured card metadata exists.
- Lifecycle operations exist.
- SessionStart already caps categories and filters current vs historical statuses.
- Package and hook install gates are well covered.

Main gap:

- Automatic writes happen before RECALL has enough evidence that a record is worth becoming durable project memory.

## Findings And Resolutions

### Finding 1: `PostToolUse` Is Too Permissive For Always-On Hooks

Evidence:

- `hooks/hooks.json` registers `PostToolUse` for `Bash|apply_patch|Edit|Write`, so it runs constantly during normal Codex work.
- `post_tool_use.py` stores many successful commands as `commands` when output contains success language or when a command exists.
- Tests currently assert that a successful `python -m unittest discover -s tests` command should be stored.
- Live store: `506/521` records came from `post_tool_use`.

Resolution:

- Change `PostToolUse` from "capture compact success output" to "default-deny unless high-value."
- Store by default only:
  - Failures and errors with actionable stderr/stdout.
  - Test/build/release results with stable signal: test counts, failures, artifact path, package result, release/tag/commit result.
  - File edits summarized by changed file path and purpose, not raw patch output.
  - Git milestone commands only when they change state: branch creation, commit, tag, push, release, merge.
  - Explicit user-directed memory commands.
- Ignore by default:
  - Read-only exploration: `Get-Content`, `rg`, `Select-String`, `Select-Object`, `Get-ChildItem`, `ls`, `dir`, `pwd`, `git status`, `git log`, `git show`, `cat`, `sed`, `nl`, `wc`.
  - Successful diagnostics with no state change.
  - Commands whose only selected line is `Result: completed` or `exit_code: 0`.
- Add `record_kind`, `value_score`, `capture_reason`, `event_signature`, and `auto_capture_policy` metadata to every automatic record.

### Finding 2: `Stop` Writes Generic Conversation Closures As `project_state`

Evidence:

- Live `stop` records include `ok`, `why`, a greeting reply, and an answer about an unrelated Vercel skill.
- `stop.py` writes the last assistant message to `project_state` whenever non-empty.
- `write_policy.is_generic_checkpoint()` only catches very short/generic token sets, not semantically irrelevant but well-formed assistant replies.

Resolution:

- Make `Stop` a project-state checkpoint only when the final message contains durable project signals:
  - branch, commit, PR, release, tests, validation, files changed, blockers, next steps, architecture, requirements, risks, or explicit memory language.
- Route non-state summaries to `session_summaries` only when they pass relevance and minimum-information thresholds.
- Ignore greetings, one-word answers, generic explanations, and answers unrelated to the current project.
- Add tests using current live false positives: `ok`, `why`, greeting response, unrelated skill explanation.

### Finding 3: Automatic Records Have Generic Summaries And Weak Metadata

Evidence:

- `post_tool_use.py` sets `summary` to `"{tool_name} result captured."`.
- `session_context.py` and `memory_review.py` special-case generic summaries because they are not useful display text.
- Live store had `425` records with `Bash result captured.`
- Some live records showed command text in `details` but not in metadata fields used by `memory_hygiene.content_fingerprint()`, reducing duplicate detection value.

Resolution:

- Require summaries to be semantic before saving:
  - Good: `Unit tests passed: 73 tests.`
  - Good: `Build plugin completed and package inspection passed.`
  - Bad: `Bash result captured.`
- Ensure command, normalized command, tool name, exit code, and state-change classification are stored consistently in metadata for all Codex payload shapes.
- Redact secrets in both content and metadata.
- Reject automatic records with generic summaries unless category is `debug_history` and the body contains an error.

### Finding 4: Lifecycle Machinery Exists But Automatic Memory Does Not Use It

Evidence:

- `memory_lifecycle.py` supports confirm, resolve, stale, supersede, merge, and archive.
- `memory_hygiene.py` can find exact and near duplicates.
- Live store had no `last_confirmed`, relation, supersession, merged, or archived metadata.
- All `521` records were `active`.

Resolution:

- Add an `audit-memory` action that reports:
  - category/source/status distribution.
  - generic-summary count.
  - low-value auto-capture candidates.
  - duplicate/near-duplicate clusters.
  - stale active records by age/source/value score.
- Add `archive-noise --dry-run` and `archive-noise --apply` to mark low-value automatic records as `archived`, not delete them.
- Treat automatic low-confidence command telemetry as `archived` or `ephemeral` unless it proves durable value.
- Add lifecycle acceptance tests proving low-value auto records do not remain active.

### Finding 5: Retrieval And SessionStart Hide Noise But Cannot Fix It

Evidence:

- `session_context.py` caps `commands` at `1`, which prevents some startup-context pollution.
- `retrieval.py` still iterates over every stored record for normal queries.
- Store growth still slows retrieval, duplicate checks, doctor, review, and index rebuild.

Resolution:

- Keep SessionStart category caps, but treat them as presentation safeguards only.
- Add source/value scoring to retrieval:
  - Downrank `source=post_tool_use` unless `value_score` is high.
  - Exclude `record_kind=telemetry` and `status=archived` by default.
  - Prefer user-authored, stop-summary, requirement, decision, risk, and architecture cards.
- Add retrieval tests with a noisy corpus: hundreds of ignored/archived command records plus a few high-value project facts.

### Finding 6: The Current Write Path Has Avoidable Performance Costs

Evidence:

- `add_record_if_useful()` calls `write_policy.classify_write()`.
- `classify_write()` calls `memory_hygiene.find_related_record()`.
- `find_related_record()` scans all records and computes token similarity for same-family records.
- `retrieval.query()` calls `index_store.ensure_complete()`, whose diagnostics loads storage records before query loops over records again.
- Quick benchmark passed, but `seed_seconds` dominated at `5.7771s` for 120 records.

Resolution:

- Add cheap preflight gates before any full-store scan:
  - command denylist.
  - output-information threshold.
  - project-state relevance threshold.
  - explicit cue detection.
- Add a deterministic `event_signature` and lookup exact duplicates by metadata before token similarity.
- Bound near-duplicate search to recent same-source/same-command records, not the whole store.
- Avoid index diagnostics on every query when the index was just appended by RECALL; rebuild only when missing/stale evidence exists.
- Add performance benchmarks for 500 and 2,000 record stores with noisy-hook distributions.

### Finding 7: Tests Currently Encode Too Much Noise As Desired Behavior

Evidence:

- `test_post_tool_use_stores_compact_successful_command` requires successful test commands to create records.
- Quality-suite hook contract similarly checks successful command compaction but not long-session noise rate.
- Existing tests prove no raw listing dumps, but not that most read-only tool use is ignored.

Resolution:

- Replace "successful command is stored" as the default invariant with "successful high-value command may be stored."
- Add tests:
  - `Get-Content`, `rg`, `git status`, and `recall_skill review-memory` successes are ignored.
  - Failed read commands go to `debug_history`.
  - Successful test/build commands are stored only when they contain test/build outcome structure.
  - 100 mixed read-only hooks create zero or near-zero active durable records.
  - 100 mixed real workflow hooks produce a bounded number of high-value memories.
- Add source-blind fixtures where the agent must recover project facts despite a large noisy command corpus.

### Finding 8: Hooks Behave Like A Background Service, So Opt-In Semantics Matter

Evidence:

- User observation: hooks trigger every message whether `@recall` is mentioned or not.
- Current storage initialization can create `.codex_memory` as a side effect of hook write paths.
- This makes RECALL feel active globally once hooks are trusted.

Resolution:

- Add project-level capture modes in `memory_config.json`:
  - `manual`: only explicit `remember this:` and skill commands write.
  - `minimal`: explicit cues, failures, milestones, and final project-state checkpoints.
  - `standard`: current intended automatic behavior after stricter gates.
  - `off`: read-only SessionStart/retrieval if memory exists; no automatic writes.
- Default new projects to `manual` or `minimal`.
- Make read hooks avoid initializing storage.
- Make `PostToolUse`, `Stop`, and `PreCompact` no-op unless `.codex_memory` already exists or the event has an explicit memory cue.
- Expose `recall_skill.py configure-capture --mode minimal|manual|standard|off`.

### Finding 9: Memory Review Is Useful But Not Yet A Quality Dashboard

Evidence:

- `review-memory` shows totals, categories, status counts, and compact cards.
- It does not compute noise score, source ratios, generic-summary counts, or archive candidates.

Resolution:

- Extend review output with a `quality` section:
  - signal-to-noise estimate.
  - automatic/manual ratio.
  - source distribution.
  - generic summaries.
  - active low-value records.
  - top noisy command patterns.
  - recommended dry-run cleanup command.
- Keep this cheap: use one pass over records and simple counters.

### Finding 10: Plugin-Eval Flags Budget And Complexity Work That Also Helps Memory Quality

Evidence:

- `plugin-eval` score: `77/100`, grade `C`.
- Top fail: deferred token budget high at `59835`.
- Warnings: high Python complexity and long lines.

Resolution:

- Move bulky skill/docs guidance into deferred references where possible.
- Split complex hook/classifier logic into small policy helpers:
  - `command_policy.py`
  - `checkpoint_policy.py`
  - `memory_quality.py`
- Keep public skill instructions short and route detail through scripts/docs.

## Target Behavior

The expected end state:

- Quiet by default in projects where RECALL has not been intentionally initialized.
- Explicit user memories are always respected.
- Failures and durable milestones are saved.
- Successful exploration commands are ignored.
- SessionStart injects high-value context without depending on hundreds of command records.
- Review tools make memory quality visible.
- Cleanup is non-destructive by default.
- Performance improves because low-value events are rejected before storage/index/dedupe work.

## Implementation Plan

### Phase 1: Add Measurement Before Behavior Changes

Files:

- `plugins/recall/scripts/memory_review.py`
- `plugins/recall/scripts/recall_skill.py`
- `plugins/recall/tests/test_memory_review.py`
- `RECALL_quality_suite/tests/test_hook_lifecycle_contract.py`

Work:

- Add `audit-memory` output with source, status, category, generic summary, command pattern, and relationship counts.
- Add `archive-noise --dry-run` design surface, but do not apply cleanup yet.
- Add tests against a synthetic noisy store.

Verification:

- `python -m unittest discover -s plugins\recall\tests -p test_memory_review.py`
- `python .\plugins\recall\scripts\recall_skill.py --root . audit-memory`

### Phase 2: Add Capture Mode And No-Init Hook Semantics

Files:

- `plugins/recall/scripts/config.py`
- `plugins/recall/scripts/storage.py`
- `plugins/recall/hooks/scripts/*.py`
- `plugins/recall/tests/test_config.py`
- `plugins/recall/tests/test_hooks.py`

Work:

- Add `capture_mode` config with `manual`, `minimal`, `standard`, and `off`.
- Add helpers to detect existing memory without creating `.codex_memory`.
- Make automatic hooks no-op in uninitialized projects unless explicit memory cues exist.
- Add `recall_skill.py configure-capture`.

Verification:

- Hook tests proving no `.codex_memory` appears after unrelated hook events in a new temp project.
- Explicit `remember this:` still initializes and stores.

### Phase 3: Replace Permissive `PostToolUse` With Value-Based Command Policy

Files:

- Create `plugins/recall/scripts/command_policy.py`
- Modify `plugins/recall/hooks/scripts/post_tool_use.py`
- Modify `plugins/recall/scripts/write_policy.py`
- Modify `plugins/recall/scripts/memory_hygiene.py`
- Tests in `plugins/recall/tests/test_hooks.py`, `test_write_policy.py`, `test_memory_hygiene.py`

Work:

- Classify commands as `ignore`, `failure`, `test_result`, `build_result`, `release_milestone`, `state_change`, `file_edit`, or `manual`.
- Ignore successful read-only commands.
- Require semantic outcome extraction for successful writes.
- Store command metadata consistently for all supported payload shapes.
- Redact content and metadata.
- Add `event_signature` and exact duplicate lookup before near-duplicate scanning.

Verification:

- Successful file reads create no active memory.
- Failed commands create `debug_history`.
- Meaningful test/build/release outcomes create compact records.
- 100 read-only events stay under a strict active-record threshold.

### Phase 4: Gate `Stop` And `PreCompact` By Project-Relevance

Files:

- Create `plugins/recall/scripts/checkpoint_policy.py`
- Modify `plugins/recall/hooks/scripts/stop.py`
- Modify `plugins/recall/hooks/scripts/pre_compact.py`
- Modify `plugins/recall/scripts/write_policy.py`
- Tests in `plugins/recall/tests/test_hooks.py`

Work:

- Add relevance scoring for project-state checkpoints.
- Ignore greetings, one-word replies, generic explanations, and non-project answers.
- Save only durable project facts to `project_state`.
- Save only real compaction summaries to `session_summaries`.

Verification:

- Live false-positive examples are ignored.
- Real milestone summaries still store.

### Phase 5: Add Non-Destructive Cleanup

Files:

- `plugins/recall/scripts/memory_review.py`
- `plugins/recall/scripts/recall_skill.py`
- `plugins/recall/scripts/memory_lifecycle.py`
- Tests in `plugins/recall/tests/test_memory_review.py`, `test_memory_lifecycle.py`

Work:

- Implement `archive-noise --dry-run` and `archive-noise --apply`.
- Candidate criteria:
  - `source=post_tool_use`
  - generic summary
  - read-only command
  - no failure signal
  - no relationship/confirmation
  - no explicit user source
- Mark records `archived` with `archived_at`, `archive_reason`, and `previous_status`.

Verification:

- Dry run does not mutate.
- Apply archives only eligible automatic records.
- Retrieval excludes archived records by default and can include them with explicit status filter.

### Phase 6: Tighten Retrieval And Session Context For Noisy Stores

Files:

- `plugins/recall/scripts/retrieval.py`
- `plugins/recall/scripts/session_context.py`
- `plugins/recall/tests/test_retrieval_quality.py`
- `RECALL_quality_suite/fixtures/source_blind_memory_cards.json`

Work:

- Downrank low-value automatic records.
- Exclude archived/ephemeral records by default.
- Add noisy-corpus retrieval tests.
- Add source-blind fixture cases with stale/noisy command history.

Verification:

- High-value requirements/risks/decisions beat command noise.
- Source-blind tests pass with realistic noisy memory packs.

### Phase 7: Performance Pass

Files:

- `plugins/recall/scripts/memory_hygiene.py`
- `plugins/recall/scripts/retrieval.py`
- `plugins/recall/scripts/storage.py`
- `RECALL_quality_suite/perf/benchmark_recall_memory.py`
- `RECALL_quality_suite/perf/perf_thresholds.json`

Work:

- Avoid full-store dedupe when cheap gates reject events.
- Bound near-duplicate search.
- Add exact signature lookup.
- Avoid unnecessary index diagnostics in hot query paths.
- Benchmark 500 and 2,000 record noisy stores.

Verification:

- Full quality suite passes.
- Query/write/rebuild/doctor remain within thresholds.
- No regression against installed-cache smoke.

### Phase 8: Docs And Release Gate Updates

Files:

- `plugins/recall/README.md`
- `plugins/recall/docs/INSTALL.md`
- `plugins/recall/docs/RELEASE_CHECKLIST.md`
- `plugins/recall/docs/E2E_VERIFICATION_LOG.md`
- `RECALL_quality_suite/docs/MEMORY_QUALITY_EVOLUTION_PLAN.md`
- `RECALL_quality_suite/rubrics/production_release_criteria.md`

Work:

- Document capture modes.
- Document hook quiet behavior.
- Add memory quality audit to release checklist.
- Add long-session endurance evidence as a release gate.

Verification:

- Static docs contract tests pass.
- Plugin-eval rerun improves or at least does not regress.

## Cleanup Strategy For The Current Store

Do not delete current memory data directly.

Recommended path:

1. Implement `audit-memory`.
2. Run `archive-noise --dry-run` against this repo.
3. Inspect candidates, especially command records after ID `472`.
4. Apply archive only after confirming candidate criteria.
5. Keep archived records queryable with explicit `--status archived`.
6. Re-run source-blind and session-start checks after cleanup.

Expected current cleanup candidates:

- Most `post_tool_use` records with generic `Bash result captured.`
- Successful `Get-Content`, `rg`, inventory, and review-memory commands.
- `Stop` records containing `ok`, `why`, greetings, and unrelated explanations.

Do not auto-archive:

- Records with failures.
- Records tied to release/build/test milestones.
- Records from explicit user memory cues.
- Records with confirmation, supersession, merge, or relationship metadata.

## Risk Register

- Too-strict capture could lose useful debugging history. Mitigation: keep failures and explicit cues always saved; add capture mode `standard` for users who prefer more automation.
- No-init hooks could surprise users who expect automatic memory in every repo. Mitigation: document capture modes and expose a simple configure command.
- Cleanup could hide old context. Mitigation: archive, never delete, and preserve explicit status filters.
- Performance optimization could desync index behavior. Mitigation: keep storage as source of truth and preserve repair/rebuild tests.
- More policy code could increase complexity. Mitigation: split into small classifier modules with focused tests.

## Completion Criteria

This workstream is complete when:

- A long noisy hook simulation produces a bounded number of active durable memories.
- Read-only tool exploration no longer writes active command records.
- Generic Stop messages no longer become `project_state`.
- `audit-memory` reports a clear signal-to-noise profile.
- `archive-noise` can safely reduce active noise without deletion.
- Retrieval quality tests pass against noisy stores.
- Quick and full quality suites pass.
- Plugin-eval does not regress from `77/100`.
- SessionStart still injects concise high-value project context.
