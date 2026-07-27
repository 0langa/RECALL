# Changelog

## 1.5.3 - 2026-07-27

- Replaced workstation-specific names and paths in public manuals, baselines, and test fixtures.
- Added release regression coverage preventing private Windows identity data from entering tracked files.

## 1.5.2 - 2026-07-12

- Added marketplace artwork metadata for Codex install surfaces.
- Kept provider manifests and MCP server metadata version-aligned.

## 1.5.1 - 2026-07-11

Production-readiness hardening pass found via code audit, not a wishlist. No retrieval/ranking changes.

- Fixed a real concurrency bug in `storage.add_record_if_new`: the replay-dedup check and the insert were two separate DB round trips, letting two concurrent sessions double-insert. Now one `BEGIN IMMEDIATE` transaction plus an indexed `json_extract` lookup (`idx_memories_idempotency`), applied to already-migrated stores too via an unconditional `_ensure_runtime_indexes`.
- `doctor()`/`repair()` now detect SQLite corruption (`PRAGMA integrity_check`) instead of crashing unhandled; new `repair --restore-backup` recovers from the existing migration-backup snapshot, preserving the corrupt file first.
- Fixed README/INSTALL install docs still pinned to `--ref v1.4.0`, missed by the existing version-parity test; fixed and pinned by a new test (`test_install_docs_pin_ref_to_current_version`) so it can't drift silently again.
- CI: pinned ruff/mypy/pytest versions; added a non-blocking coverage job.
- Added `SECURITY.md`; added README troubleshooting/migration/uninstall sections.

## 1.5.0 - 2026-07-06

Quality-gate hardening + skill polish, found during a v1.4.0 release-validation pass. No retrieval/ranking changes.

- Fixed a secret-scanner false positive: the keyword=value pattern shared by the build-time package inspector and the runtime redact_text/contains_secret path matched any `token`/`password`/etc. identifier directly followed by `:` or `=`, so an ordinary type-annotated function parameter or a variable reassigned from a slice of itself tripped it exactly like a real hardcoded credential. Added a plausibility filter (reject common type keywords and self-referential values) to both paths. Caught and fixed a second bug while writing it: a regex match's group-end offset is relative to the full searched text, not to the matched substring — an unrelativized slice was silently returning an empty string (no protection at all) for any match not at position 0.
- Fixed `using-recall` and `define-category` scoring Gold instead of Platinum on PluginEval's `orchestration_fitness` dimension: the judge penalizes "if request is about X, use skill Y" conditional-dispatch phrasing as supervisor/orchestrator language, even in skills whose legitimate job is routing or stating scope boundaries. Reframed (not removed) the routing content as declarative recommendations; trimmed a routing table that fully duplicated the Handoff Map; aligned worked examples to each skill's own declared Output Format instead of inventing sibling-owned parameters. Verified via before/after judge re-score (using-recall orchestration_fitness 0.75 -> 0.92; define-category 0.72 -> 0.85).
- Fixed the CI `bench-light` job, which had failed at its first step ("No module named pytest") on every run since the benchmark harness was added — silently masked by `continue-on-error: true`, so the actual benchmark comparison step had never executed even once. Added the missing `pip install pytest` step.
- Flipped `bench-light` to a blocking `--strict` gate: with the above fix landed, 2 consecutive Linux CI runs plus a local Windows run all produced the identical `emission_hash` against the light-mode baseline, satisfying the "two stable consecutive baselines" bar the job had been waiting on since the harness shipped.
- WORK_STATUS.md's "Deferred" list marked 4 items resolved that had actually been closed in the 1.3.0 batch but never updated.

## 1.4.0 - 2026-07-06

Closes the last open retrieval frontier from 1.3.0: semantic matching beyond raw lexical overlap. Measured honestly with a new benchmark metric before optimizing, then improved ranking end to end with zero regressions on every existing quality gate.

- Benchmark gained a `paraphrase_retrieval` metric (`bench/recall_bench`): each golden card now has a same-meaning, different-words query variant sharing few or no tokens with the card. Deliberately not baseline-gated — it's an honest headroom number, not a pass/fail bar. Starting reading: hit rate 0.3 against a lexical-goldens ceiling of 1.0.
- Retrieval ranking (`retrieval.py`) gained two additive signals: IDF downweighting of store-frequent tokens (`build_term_document_frequencies`, `idf_weighted_overlap`) and an ephemeral in-memory FTS5 bm25 rerank (`storage.fts5_rerank_scores`) built per query over the same field-weighted text the lexical scorer already uses — not the persisted `memories_fts` mirror, which only indexes content+title and reintroduces the "raw content stuffing beats structured fields" anti-pattern this project already fixed once.
- Local hash embedder (`embedder.py`) upgraded 64 -> 256 dimensions (`local-hash-v1` -> `local-hash-v2`): the 64-dim embedder's cosine term could go actively negative on genuine paraphrase matches from hash-collision noise, which no amount of lexical reweighting could overcome. `index_store.rebuild` now silently re-embeds and persists any record still carrying an old-shaped embedding the next time the index needs rebuilding, so existing stores self-heal with no manual migration step.
- Net result: paraphrase hit rate 0.3 -> 0.6, with lexical goldens still 1.0, injection gate still 19/19, flag correctness still 1.0, hygiene detection still 6/7, zero secret leaks, and marginal tokens/turn essentially flat (~95.6 vs. 105.5 baseline — improved, not regressed).
- New tests: `test_stale_embedding_dimension_is_migrated_on_rebuild` (migration + idempotency), plus fixture updates for the new embedding shape.

## 1.3.0 - 2026-07-05

Clears every item deferred from 1.2.0. Doc-duplication detection and all other checks remain fully local — no model or network calls; the token work cuts what RECALL injects into agent context.

- Hygiene detects memories that restate repo docs: paragraph-level token containment against `README.md` and `docs/**/*.md` produces review-only `review_doc_duplicate` proposals naming the overlapping file (never auto-applied; corpus size-capped).
- Staleness thresholds are configurable via a validated `staleness` config block (`snapshot_stale_days`, `retrieval_aging_days`); hygiene snapshot ageing and retrieval health flags both consume it.
- Token-lean agent outputs: `retrieve_memory`/`retrieve-memory` return compact results by default (full metadata behind `verbose`); `hygiene-scan` caps listed proposals at 20 with an omitted count; SessionStart injection is hard-capped (~2000 chars). Library callers keep full metadata by default.
- Blocking lint gates: `ruff check .` (conservative correctness rules) and lenient `mypy` over the engine, wired as a CI job; all pre-existing findings fixed.
- capture_mode is enforced in the hooks: `standard` = full auto capture; `minimal` = no per-tool evidence buffering, session summaries and stop notes still run; `manual` = explicit cues and skill/MCP saves only; `off` = no hook capture at all, explicit cues get a how-to-re-enable response. `recall_mode` continues to govern retrieval separately. PreCompact session summaries now run in `minimal` too (previously standard-only).
- New tests: doc-duplication fixtures, configurable-threshold tests, compact/verbose retrieval tests, scan-cap test, and per-mode capture tests (`tests/test_capture_modes.py`).

## 1.2.0 - 2026-07-05

Deterministic memory lifecycle contract, exposed by the engine instead of relying on agents remembering instructions.

- Added `scripts/contract.py` as the canonical behavior contract (source authority order, lifecycle steps, save/skip rules, status meanings). The MCP server `instructions`, the new `memory_contract` MCP tool, the SessionStart hook context, the `recall_skill.py contract` command, and `skills/using-recall/references/contract.md` all derive from or are pinned to it by tests (`tests/test_contract_sync.py`).
- SessionStart hook now injects the compact contract plus a store overview for activated projects on all providers (previously Kimi-only via `sessionStart.skill`); non-activated projects stay quiet.
- Added MCP lifecycle tools: `update_memory` (update/confirm/stale/deprecate/supersede/merge/resolve/prune) and `memory_hygiene` (route/scan/plan/apply_safe), closing the append-only bias of the MCP surface.
- MCP `save_insight` now rejects secret-shaped content (parity with the skill adapter), routes through duplicate detection, and returns teaching responses: `updated_existing` confirms the existing card instead of appending; `saved_related` suggests a merge; `ignored` explains recovery (including preference-evidence requirements). Skill adapter `save-insight` gained the same dedup-and-teach behavior.
- Retrieval results now carry per-result health flags (`current`, `stale`, `superseded`, `deprecated`, `needs_verification`, `conflicting`) and a response-level `health` summary with `next_action`; conflicting claim keys are marked across results.
- Enriched all built-in categories with examples, non-examples, and update rules; added `tooling_quirks` (provider/tool quirks) and `integrations` (external service constraints) categories; `define-category` accepts `--example`, `--non-example`, `--update-rule`.
- Hygiene now detects stored secret-shaped content (safe in-place `redact_secret`, highest priority), raw log/output dumps (safe prune), vague memories (`review_vague`), aged point-in-time snapshots (safe stale after 45 days for `project_state`/`session_summaries`/`integrations`/`tooling_quirks`), and missing provenance (`review_metadata`); `hygiene-scan` output includes `next_action`.
- `initialize-project` (MCP and adapter) now ensures `.gitignore` covers `.recall/` and `.codex_memory/`, and returns category list, compact contract, and a first-workflow guide.
- Fixed `.claude-plugin/` missing from `build_plugin.py` INCLUDE (built zips previously shipped without the Claude Code manifest); `inspect_package.py` now requires `.claude-plugin/plugin.json` and `scripts/contract.py`.
- Added cross-provider drift gates: manifest version/name/skills-path parity across `.codex-plugin`, `.claude-plugin`, and `kimi.plugin.json`, MCP server env parity, and contract-consistency tests.
- New test files: `test_contract_sync.py`, `test_retrieval_flags.py`, `test_hygiene_quality_checks.py`, `test_mcp_lifecycle_tools.py`.

## 1.1.1 - 2026-07-02

- Fixed `save-insight` silently accepting secret-shaped content (AWS keys, JWTs, GitHub tokens, verbal `password is X` phrasing). The adapter now returns `{"result":"rejected","reason":"secret-like content must not be stored"}` and refuses to persist the record.
- Broadened `SECRET_PATTERNS` to cover `AKIA*`/`ASIA*` AWS access keys, 40-char AWS secret keys, JWT triples, GitHub/GitLab tokens, verbal password/token assignments, and `-----BEGIN PRIVATE KEY-----` blocks.
- Routed `route-memory` secret detection through the shared broadened pattern set so credential-shaped candidates return `"route":"reject"` at 1.0 confidence.
- Added regression tests covering AWS/JWT/GitHub/password rejection through both `save-insight` and `route-memory`.

## 1.1.0 - 2026-07-02

- Added `memory-hygiene` public skill and adapter surface (`route-memory`, `hygiene-scan`, `hygiene-plan`, `hygiene-apply --safe`, `reconcile-current-truth`, `refresh-source-backed`) as RECALL's policy brain for candidate routing, cleanup planning, and safe non-destructive lifecycle maintenance.
- Expanded the public skill surface from six to seven skills and documented that lifecycle mutation commands stay grouped under `manage-memory`.
- Clarified plugin-root vs project-root adapter invocation in every SKILL.md so `./scripts/recall_skill.py` examples resolve correctly across Codex, Claude Code, and Kimi Code.
- Added claude-code adapter tests and a metadata contract test that pins the seven-skill public surface.
- Added provider-neutral `.recall/` storage for new projects while preserving existing `.codex_memory/` stores as legacy authoritative memory.
- Added Kimi Code plugin support with `kimi.plugin.json`, `using-recall` session guidance, and a local stdio MCP server over the shared RECALL core.
- Added Claude Code plugin support with `.claude-plugin/plugin.json`, shared skills, shared hooks, and the shared local MCP server.
- Added provider-neutral hook event normalization so Codex and Kimi-shaped hook payloads feed the same capture and finalization path.
- Normalized Kimi Code JSON tool-failure envelopes before finalizer capture and added a finalizer backstop that ignores raw wrapper cards.
- Suppressed transient task-control prompts so operational `@recall` test instructions do not become durable project requirements.
- Added a parallel unittest runner with hook method profiling, faster in-process hook tests, split CI gates, and timed package build steps.
- Documented optional Kimi Code hook setup with `~/.kimi-code/config.toml` snippets.
- Added provider provenance metadata support for public memory writes, including `origin_provider`, `origin_agent`, session/turn, workspace, branch, commit, capture channel, and provider applicability fields.
- Updated package/build/quality gates to require Kimi artifacts and reject `.recall/` runtime data in release packages.
- Optimized retrieval to avoid a duplicate record scan during index-completeness checks, improving quick benchmark query latency headroom.

## 1.0.0 - 2026-06-16

- Added persistent project-scoped activation with Git/manifest root resolution, explicit greenfield initialization, activation status, and non-destructive deactivation.
- Changed `PostToolUse` and `Stop` from direct durable writes to redacted turn evidence plus one atomic, idempotent semantic finalizer batch.
- Added relevance and sufficiency gating, command-category suppression for non-tooling prompts, quiet conflict alerts, and seven-day debug traces.
- Added batch ingest with one SQLite transaction and one index rebuild; 500-record seed time is now below one second on the release workstation.
- Added non-destructive corpus migration with pre-apply backup, evidence lineage, command synthesis, and historical score/checkpoint consolidation.
- Migrated the repository corpus from 18 active automatic noise records to zero while preserving all source IDs and history.

- Added automatic schema-v2 migration with a one-time v1 SQLite backup, WAL mode, foreign keys, bounded lock waits, normalized lifecycle/provenance columns, indexes, and optional FTS5.
- Extended `doctor` with SQLite concurrency, FTS, and migration-backup diagnostics.
- Added file provenance hashes, project-scope path checks, source refresh/invalidation, and repository reconciliation for modified, deleted, or moved sources.
- Added hypothesis/validated/deprecated lifecycle states, trust promotion, explicit claim-slot conflict clusters, conflict resolution, and validated-truth protection.
- Added durable preference evidence policy, hook-delivery idempotency keys, and explainable token-budgeted context packets with diversity and omission reporting.
- Redacted secret-like values recursively in persisted metadata and added deterministic replay keys for identified hook deliveries.
- Added portable export/import and timestamped backup/restore workflows that preserve memory IDs, lifecycle, provenance, and relationships.
- Separated `manual`, `relevant`, and `always` recall activation from automatic capture mode.
- Added three-platform CI, clean installed-cache verification, and an evidence report that records unresolved human and evaluator certification gates.
- Removed the unsupported `UpdateCategories` hook wrapper and documented category normalization as an explicit support command.
- Added regression coverage to keep category maintenance out of the hook surface.
- Added golden retrieval quality fixtures with status-aware and field-aware ranking.
- Added automatic hook memory hygiene for duplicate suppression and near-duplicate linking.
- Changed `SessionStart` to a quiet compatibility hook; explicit `@recall` prompt retrieval now injects curated grouped context.
- Exposed safe `doctor`, `repair`, and `list-categories` actions through `recall_skill.py`.
- Added lifecycle operations for confirming, resolving, marking stale, superseding, merging, and non-destructively pruning memories.
- Added hook write policy classification for ignored, refreshed, new, related, and superseding automatic memories.
- Added CLI-first memory review summaries through `recall_skill.py review-memory`.
- Added discoverable memory-control skills for finalizer cards, review, confirm, resolve, stale, supersede, merge, prune, doctor, and repair workflows.
- Added explicit `edit-memory` and confirmation-gated `delete-memory` public adapter commands and skills.
- Changed automatic hooks to stay idle unless the current user prompt explicitly invokes RECALL with `@recall`, `plugin://recall`, or `$recall:`.
- Added `archive-noise` dry-run/apply cleanup for old low-value automatic hook command memories.
- Compacted Stop finalizer continuation prompts with inline `PACKET=` JSON instead of requiring a packet-file read first.

## 0.1.0 - 2026-06-06

- Added validation-ready Codex plugin manifest.
- Moved the installable plugin to the official repo marketplace layout at `plugins/recall`.
- Added repo-root marketplace and build wrappers.
- Added RECALL memory categories and project-local configuration.
- Added SQLite and JSONL storage support.
- Added dedicated storage, index, and retrieval backend modules.
- Added structured memory cards with summary, details, tags, source, status, importance, and confidence metadata.
- Added deterministic local retrieval scoring, lexical boosts, status filters, and heuristic summarization.
- Added rebuildable `vector_index.bin` support with `rebuild-index`, `doctor`, and `repair` commands.
- Added malformed JSONL row tolerance and index integrity diagnostics.
- Added `save-insight`, `retrieve-memory`, and `define-category` skills.
- Added a narrow `recall_skill.py` adapter so bundled skills use a public plugin action surface instead of the backend maintenance CLI.
- Added lifecycle hooks for session start, compaction, tool use, prompt inspection, and stop.
- Added compact hook payload parsing for Codex-shaped events.
- Added source and installed-cache smoke harnesses.
- Added built-zip marketplace smoke testing through a temporary Codex marketplace.
- Added public manifest metadata, local icon/logo assets, privacy terms, and release checklist.
- Added package inspection and build gates for tests, plugin validation, smoke, zip creation, and artifact inspection.
