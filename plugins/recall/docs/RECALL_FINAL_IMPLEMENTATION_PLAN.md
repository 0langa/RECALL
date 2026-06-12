# RECALL Final Implementation Plan

Status: Proposed execution roadmap
Date: 2026-06-12
Target: A production-ready, local-first persistent-memory plugin for Codex

## 1. Purpose

This plan defines the work required to finish RECALL as a trustworthy, useful,
efficient, and maintainable Codex plugin. It converts the current implementation,
the persistent-memory architecture blueprint, official Codex behavior, RECALL
project memory, and PluginEval results into an ordered engineering program.

No engineering plan can guarantee literal perfection. This plan instead defines
objective completion gates. RECALL is considered finished only when every required
gate in this document passes with recorded evidence.

## 2. Product Outcome

RECALL should give Codex durable project knowledge without making the user manage a
database, repeat prior context, accept stale claims, or pay an excessive token cost.

The final plugin must be:

- Local-first and useful without a hosted account or external API.
- Quiet by default and controllable at project and thread level.
- Precise about what it knows, what it inferred, and what may be stale.
- Safe across concurrent Codex agents and interrupted writes.
- Effective after new threads, resumes, and context compaction.
- Token-budgeted, progressively disclosed, and fast on realistic stores.
- Inspectable and reversible through first-class review and lifecycle commands.
- Correctly packaged for Codex plugins, skills, hooks, and optional MCP tools.
- Supported on Windows, macOS, and Linux with a documented runtime story.
- Measured by semantic quality, not only unit tests and static contracts.

## 3. Non-Goals

- Do not turn RECALL into a general code knowledge graph.
- Do not require cloud embeddings, hosted storage, or a paid extraction model.
- Do not silently edit `AGENTS.md`, global Codex configuration, or user memory.
- Do not make every tool result or assistant message a durable memory.
- Do not treat stored memory as more authoritative than the live repository or a
  newer explicit user instruction.
- Do not duplicate native Codex memories. RECALL remains project-scoped and
  inspectable while native memories remain an optional background layer.

## 4. Current Baseline

### 4.1 Existing strengths

- Project-local `.codex_memory/` storage.
- Python standard-library implementation with SQLite and JSONL support.
- Deterministic local embeddings and hybrid lexical/semantic ranking.
- Five bundled skills with a narrow public `recall_skill.py` adapter.
- `SessionStart`, `UserPromptSubmit`, `PostToolUse`, `PreCompact`, and `Stop`
  hook integration.
- Explicit opt-in activation that prevents global background noise.
- Review, audit, confirm, resolve, stale, supersede, merge, prune, edit, delete,
  doctor, repair, and noise-archive workflows.
- Secret redaction and local-only documentation.
- Unit, smoke, package-hygiene, contract, and 500-record performance coverage.
- Plugin Creator validation currently passes.

### 4.2 Durable project decisions

- Memory quality review is first-class through `audit-memory` and richer
  `review-memory` output.
- Truth quality comes before broader interfaces.
- The preferred order is schema and storage, provenance and staleness, trust and
  contradictions, budgeted retrieval, semantic evaluation, then optional MCP and
  structural integrations.

### 4.3 Current PluginEval quick baseline

| Skill | Score | Main gap |
|---|---:|---|
| `manage-memory` | 79.66 | Triggering accuracy and progressive disclosure |
| `review-memory` | 77.27 | Triggering accuracy and progressive disclosure |
| `save-insight` | 58.88 | Triggering, structure, references, related workflow |
| `define-category` | 57.12 | Triggering, scope, structure, references |
| `retrieve-memory` | 56.21 | Triggering, structure, references, related workflow |

Quick evaluation is static-only. It cannot establish output quality, robustness,
scope calibration, real activation accuracy, or runtime correctness. Final release
therefore requires standard and deep evaluation.

### 4.4 Principal remaining risks

- Stored facts lack first-class source hashes and automatic source invalidation.
- Contradiction handling is mostly explicit rather than semantic and systematic.
- Confirmation metadata is not yet a coherent trust lifecycle.
- SQLite is not yet configured as a robust concurrent-agent store.
- Token accounting and context assembly are approximate.
- Complexity is concentrated in large Python modules.
- Quality gates measure mechanics more thoroughly than semantic usefulness.
- Python availability remains part of the installation and hook reliability story.

## 5. Official Codex Constraints

Implementation must remain aligned with the current official Codex documentation:

- Skills use progressive disclosure. Their names and descriptions are present in
  the initial skill list, while full instructions load only on activation.
- The initial skill list is capped at roughly 2% of the context window or 8,000
  characters when the context size is unknown. Trigger descriptions must therefore
  be concise, discriminative, and front-loaded.
- Plugins are the installable distribution unit and may bundle skills, MCP server
  configuration, lifecycle hooks, apps, and assets.
- Hooks are enabled by default. The canonical feature key is `hooks`; the older
  `codex_hooks` key is deprecated.
- Non-managed command hooks require trust. Changed hook definitions receive a new
  hash and must be reviewed again.
- Matching hooks can run concurrently. RECALL cannot assume hook ordering.
- `PostToolUse` matchers can cover Bash, `apply_patch`, Edit, Write, and MCP tools.
- Only command hook handlers execute today; prompt and agent handlers are parsed but
  skipped.
- Plugin-provided local STDIO MCP servers are supported, but should be added only
  when they improve the public action surface without duplicating backend logic.
- Native Codex memories are optional, background-generated, and unavailable in some
  regions. Hard project rules belong in `AGENTS.md` or checked-in documentation.

Primary references:

- [Agent Skills](https://developers.openai.com/codex/skills)
- [Build plugins](https://developers.openai.com/codex/plugins/build)
- [Plugins](https://developers.openai.com/codex/plugins)
- [Hooks](https://developers.openai.com/codex/hooks)
- [Model Context Protocol](https://developers.openai.com/codex/mcp)
- [Memories](https://developers.openai.com/codex/memories)

## 6. Architecture Target

```text
Bundled skills -----------+
Lifecycle hooks ----------+--> public application service --> storage service
Optional local MCP -------+             |                         |
recall_skill.py CLI ------+             |                         +--> SQLite WAL
                                         |                         +--> FTS index
                                         |                         +--> vector index
                                         |
                                         +--> capture policy
                                         +--> provenance service
                                         +--> lifecycle/conflict service
                                         +--> retrieval/context service
                                         +--> review/health service
```

All interfaces must call the same application services. Hooks, skills, CLI, and MCP
must not implement separate memory behavior.

## 7. Definition Of Done

RECALL is finished only when all of these are true:

1. Every active recalled claim has lifecycle state, confidence, provenance, and a
   deterministic explanation of why it ranked.
2. Source-linked memory is marked stale when its source changes, moves, or disappears.
3. Contradictory active claims are detected, surfaced, and prevented from appearing as
   equally current truth.
4. Concurrent agent writes do not corrupt the store or lose accepted memory updates.
5. Context packets stay within their declared token budget and disclose omissions.
6. Long sessions do not create unbounded repetitive memory.
7. Source-blind agents recover current architecture, decisions, risks, commands, and
   next steps with the required precision.
8. Every skill reaches at least Gold in PluginEval standard evaluation and no skill is
   below 75 in any high-weight dimension.
9. The plugin passes unit, integration, migration, concurrency, performance, package,
   installed-cache, and cross-platform tests.
10. A clean install, hook trust, new-thread recall, compaction, update, rollback, and
    uninstall path are documented and verified.

## 8. Execution Protocol

Apply this protocol to every phase:

1. Create or update focused tests before changing behavior.
2. Keep public workflows on skills, hooks, `recall_skill.py`, and later the optional
   MCP facade. Treat backend modules as internal.
3. Make schema migrations forward-compatible and idempotent.
4. Preserve user-created memory and existing lifecycle history.
5. Update public documentation and changelog in the same phase as behavior.
6. Run the smallest relevant tests during implementation, then the full release gate.
7. Use one reviewable commit per coherent task or migration step.
8. Record important architecture decisions and newly discovered risks in RECALL.
9. Run Plugin Creator validation after plugin structure or metadata changes.
10. Update the plugin cachebuster only for an installable verification or release build,
    using Plugin Creator's update helper rather than hand-editing marketplace state.

## 9. Phase 0: Freeze Baselines And Acceptance Fixtures

### Goal

Create reproducible evidence for current behavior before changing storage or ranking.

### Steps

1. Capture current unit, smoke, quality-suite, performance, package, and PluginEval
   results in a dated baseline report.
2. Add realistic source-blind fixtures derived from RECALL history, with hidden ground
   truth for architecture, decisions, risks, commands, open work, and uncertainty.
3. Add mixed-history fixtures containing duplicates, corrections, contradictions,
   superseded claims, deleted files, renamed files, and incomplete knowledge.
4. Define precision, recall, stale-truth, contradiction, noise, latency, and token-cost
   metrics.
5. Define the release scorecard in machine-readable JSON.

### Primary files

- `RECALL_quality_suite/fixtures/`
- `RECALL_quality_suite/rubrics/`
- `RECALL_quality_suite/scripts/source_blind_agent_gate.py`
- `RECALL_quality_suite/perf/`
- `RECALL_quality_suite/docs/`

### Exit gate

- Baseline report is reproducible from one command.
- Source-blind evaluation can fail independently of contract tests.
- Hidden ground truth is not exposed to the evaluated agent.

## 10. Phase 1: Split The Internal Architecture

### Goal

Reduce complexity before introducing schema and lifecycle changes.

### Steps

1. Define application-level request and response models for save, retrieve, review,
   lifecycle, health, and context-packet operations.
2. Split storage concerns from memory policy in `memory_manager.py`.
3. Move ranking, provenance, lifecycle, and capture decisions into focused services.
4. Keep compatibility wrappers so current skills, hooks, and tests continue to work.
5. Add module-level complexity thresholds and prevent new oversized functions.

### Proposed modules

- `scripts/services/memory_service.py`
- `scripts/services/retrieval_service.py`
- `scripts/services/provenance_service.py`
- `scripts/services/lifecycle_service.py`
- `scripts/services/health_service.py`
- `scripts/models.py`

### Exit gate

- No public command changes.
- Existing tests remain green.
- Core service modules have explicit typed contracts and focused responsibilities.
- Complexity no longer blocks safe schema work.

## 11. Phase 2: Schema V2 And Concurrent Storage

### Goal

Create an explicit, migratable, concurrent-safe memory model.

### Steps

1. Add schema-v2 fields for memory type, title, status, trust, confidence,
   importance, source kind, source path, source hash, source revision, created time,
   updated time, confirmed time, accessed time, expiry, and lineage.
2. Normalize frequently queried lifecycle and provenance fields into columns while
   preserving extensible metadata JSON.
3. Add migration bookkeeping and automatic backup before migration.
4. Enable SQLite WAL, foreign keys, and a bounded busy timeout.
5. Add indexes for project, status, type/category, source path, and timestamps.
6. Add FTS5 when available, with a tested lexical fallback when it is unavailable.
7. Keep JSONL as an import/export and recovery format rather than an equally complex
   second live backend unless a demonstrated requirement justifies it.

### Tests

- V1 to V2 migration with real fixtures.
- Repeated migration idempotence.
- Interrupted migration recovery.
- Multi-process reader/writer stress.
- Lock timeout and retry behavior.
- Export/import round trip.

### Exit gate

- Zero lost or duplicated records under the concurrency stress profile.
- Existing stores migrate without manual intervention.
- Doctor identifies schema and migration state precisely.

## 12. Phase 3: Provenance And Staleness

### Goal

Tie memory claims to inspectable evidence and invalidate them when evidence changes.

### Steps

1. Add source descriptors for files, user statements, commands, tests, commits,
   finalizers, and inferred summaries.
2. Store project-relative paths, content hashes, optional line/symbol hints, and Git
   revision where available.
3. Add `invalidate-by-file` and `refresh-source` application operations.
4. Parse `apply_patch`, Edit, Write, Bash, and matching MCP tool payloads for changed
   paths without assuming that all file writes pass through hooks.
5. Add an on-demand repository reconciliation scan to catch writes missed by hooks.
6. Detect modified, deleted, moved, and recreated files.
7. Clearly mark stale context and exclude it from normal active recall unless no current
   alternative exists and historical context is explicitly requested.

### Tests

- Source modified after memory creation.
- Source deleted, renamed, and recreated with different contents.
- Same filename in different directories.
- Windows case and path separator handling.
- Hook-missed write found by reconciliation.

### Exit gate

- No source-linked stale claim appears as confident current truth in the fixture suite.
- Review output explains the source and invalidation reason.

## 13. Phase 4: Trust, Contradictions, And Lifecycle Governance

### Goal

Maintain one defensible current view without destroying useful history.

### Lifecycle

Use explicit states with documented transitions:

```text
hypothesis -> active -> validated
     |          |          |
     +--------> stale <-----+
                |
                +--> superseded
                +--> deprecated
                +--> archived
```

Resolved task and bug state may remain orthogonal metadata rather than replacing the
truth lifecycle.

### Steps

1. Convert confirmation counters into an explicit trust policy.
2. Add promote, deprecate, and conflict-resolution operations.
3. Find contradiction candidates using lexical overlap, local embeddings, category,
   entity/claim slots, and lifecycle state.
4. Use deterministic rules for obvious replacements and explicit supersession.
5. Surface ambiguous conflicts for review instead of silently choosing one.
6. Prevent two unresolved contradictory claims from both appearing as validated truth.
7. Preserve lineage among replacements, merges, splits, and corrections.
8. Add conflict clusters and health recommendations to `audit-memory`.

### Exit gate

- Contradiction fixtures reach the expected lifecycle result.
- Automatic resolution has no destructive false-positive case in the release fixture set.
- Every superseded claim points to its replacement when one exists.

## 14. Phase 5: Preference Evidence Policy

### Goal

Prevent accidental preference learning from drafts, temporary constraints, or model text.

### Rules

Durable preferences may come only from:

- Explicit standing preferences.
- Approved or rejected plans with reasons.
- Accepted, rejected, adjusted, or undone edits.
- Manual rewrites that change style, structure, or workflow rather than facts.

Do not learn preferences from:

- Unreviewed drafts.
- Model output that received no user decision.
- Fact, date, citation, or domain corrections.
- One-task constraints unless the user says they should apply in the future.

### Steps

1. Add preference evidence type, scope, decision ID, confidence, and supporting event IDs.
2. Require two meaningful decisions or one explicit declaration before automatic
   promotion to a reusable preference.
3. Keep low-confidence preferences reviewable but out of automatic recall.
4. Add contradiction handling for newer explicit preferences without erasing history.

### Exit gate

- Preference tests distinguish constraints, corrections, drafts, and durable decisions.
- No fixture promotes a one-off instruction into a standing preference.

## 15. Phase 6: Ingestion And Finalizer Quality

### Goal

Store fewer, better memories with bounded end-of-turn cost.

### Steps

1. Define a memory-worthiness rubric for durability, future value, specificity,
   novelty, evidence, and confidence.
2. Apply the same write policy to skills, prompt capture, hooks, finalizers, and future
   MCP tools.
3. Keep exact duplicates as confirmations or updates rather than new records.
4. Link near duplicates and prefer merge recommendations over repetitive cards.
5. Enforce finalizer limits by token budget and card value, not only card count.
6. Add cooldown and idempotency keys for repeated hook delivery.
7. Add retention rules for active context, project state, progress, command evidence,
   and session summaries.
8. Distill old session summaries into reviewed patterns without deleting decisions.

### Exit gate

- Read-only tool workloads create zero durable records by default.
- Long-session fixtures remain above the required signal-to-noise ratio.
- Replaying the same hook payload is idempotent.

## 16. Phase 7: Retrieval And Token Budgets

### Goal

Return the smallest context packet that lets Codex act correctly.

### Steps

1. Replace approximate word counting with a calibrated token estimator and conservative
   fallback.
2. Create retrieval tiers: current project state, validated decisions and constraints,
   task-relevant facts, useful procedures, then historical context.
3. Add category and source diversity so repeated memories cannot consume the packet.
4. Add maximum card lengths and title-only fallback under budget pressure.
5. Exclude stale, superseded, deprecated, and archived records from normal current recall.
6. Return score components and omission counts for explainability.
7. Add query expansion for project terminology without broadening unrelated recall.
8. Measure cold-start and warm-query performance at 500, 5,000, and 50,000 records.

### Exit gate

- Every packet is within its declared budget.
- Current truth wins all stale/superseded ranking fixtures.
- Source-blind answer quality meets the release thresholds at each store size.
- p95 retrieval meets the performance scorecard.

## 17. Phase 8: Hooks, Threads, And Compaction

### Goal

Integrate correctly with current Codex lifecycle behavior while remaining quiet.

### Steps

1. Keep SessionStart quiet by default, but support configurable recall activation:
   `manual`, `relevant`, and `always`.
2. Separate retrieval activation from capture mode.
3. Make hook handlers idempotent and safe under concurrent execution.
4. Support current event and matcher behavior, including `PostCompact` where it improves
   context refresh.
5. Preserve compaction evidence before context is lost and refresh current memory after
   compaction.
6. Bound Stop continuation behavior so it cannot loop or repeatedly block a turn.
7. Test untrusted hooks, newly changed hook hashes, disabled hooks, missing Python, timeout,
   malformed payload, and partial plugin installation.
8. Update documentation to use the canonical `hooks` feature name.

### Exit gate

- All hook events exit successfully on valid and malformed payloads.
- No hook failure prevents normal Codex use.
- Compaction tests preserve durable facts exactly once.
- Manual mode performs no automatic durable writes.

## 18. Phase 9: Skills And User Experience

### Goal

Make RECALL easy for Codex to invoke correctly and easy for users to understand.

### Steps

1. Finish the in-progress `manage-memory` and `review-memory` skill improvements.
2. Upgrade `retrieve-memory`, `save-insight`, and `define-category` with:
   - Discriminative frontmatter triggers.
   - Explicit inputs and outputs.
   - Examples for simple, moderate, and edge cases.
   - Troubleshooting and failure behavior.
   - Non-empty references for progressive disclosure.
   - Related-skill links that do not imply orchestration.
3. Add `agents/openai.yaml` only where UI metadata or explicit invocation policy provides
   real value.
4. Keep skill instructions focused on public workflows and hide backend maintenance detail.
5. Test should-trigger and should-not-trigger prompt sets for each skill.
6. Run PluginEval quick during editing, standard before merge, and deep certification before
   release.

### Exit gate

- Every skill scores at least 80 overall in standard evaluation.
- Triggering accuracy and orchestration fitness are each at least 0.75.
- No anti-pattern flags, dead references, or dead cross-skill links.
- Deep evaluation has acceptable failure rate and score variance.

## 19. Phase 10: Optional Local MCP Facade

### Goal

Provide structured tools without replacing the working skills and CLI path.

### Preconditions

- Phases 1 through 9 pass.
- A measured usability or reliability benefit over shell-based adapter calls is documented.

### Proposed tools

- `recall_context`
- `search_memory`
- `save_memory`
- `review_memory`
- `memory_health`
- `list_conflicts`
- `promote_memory`
- `mark_memory_stale`
- `supersede_memory`
- `invalidate_by_file`

### Steps

1. Build a local STDIO server that calls the shared application services.
2. Keep tools narrow, typed, and project-scoped.
3. Provide concise server instructions with the critical guidance in the first 512
   characters.
4. Configure safe approval defaults and tool timeouts.
5. Package MCP configuration through the supported plugin mechanism.
6. Test CLI/skill/MCP behavioral parity.

### Exit gate

- MCP adds no duplicate storage or policy implementation.
- Tool schemas reject malformed, cross-project, and secret-like writes.
- Plugin remains fully useful when MCP is disabled.

## 20. Phase 11: Privacy, Security, And Recovery

### Goal

Make local memory safe to operate, inspect, share, back up, and remove.

### Steps

1. Centralize secret detection and apply it before persistence, logs, indexes, exports,
   hook packets, and error messages.
2. Add configurable sensitive-path exclusions and repository ignore rules.
3. Add project-scope canonicalization and symlink escape protection.
4. Define backup, restore, export, import, and corruption-repair workflows.
5. Add secure-delete limitations to documentation; prefer archival and store replacement.
6. Ensure diagnostics never print full secret-like content.
7. Add fuzz tests for malformed JSON, metadata, paths, encodings, and hook payloads.

### Exit gate

- Secret fixtures do not survive in any persistent artifact.
- Cross-project writes are rejected.
- Backup/restore preserves IDs, lifecycle, provenance, and relationships.
- Corrupt indexes can be rebuilt from authoritative records.

## 21. Phase 12: Evaluation Laboratory

### Goal

Prove that RECALL improves future Codex work rather than merely storing data.

### Required evaluations

1. Source-blind architecture recovery.
2. Current-vs-stale truth selection.
3. Contradiction discovery and resolution.
4. Missing-information honesty.
5. Cross-agent consistency.
6. Long-session endurance and noise growth.
7. Multi-process concurrency.
8. Context compaction survival.
9. Trigger precision and recall for every skill.
10. Token cost and latency at increasing store sizes.
11. Windows, macOS, and Linux installed-plugin smoke tests.
12. Upgrade from the oldest supported RECALL store.

### Release thresholds

- Source-blind factual precision: at least 0.90.
- Stale-current selection accuracy: 1.00 on release fixtures.
- Contradiction detection recall: at least 0.90 with reviewed false positives.
- Missing-information honesty: no confident invented source detail.
- Cross-agent major-fact agreement: at least 0.90.
- Active signal-to-noise estimate: at least 0.90 after endurance workload.
- Retrieval packet budget violations: zero.
- Corrupt or lost records in concurrency tests: zero.
- PluginEval standard: every skill at least 80.
- PluginEval deep: no skill below Gold release threshold unless a documented harness
  limitation is approved.

## 22. Phase 13: Packaging, Installation, And Release

### Goal

Ship a reproducible plugin whose installed behavior matches source behavior.

### Steps

1. Decide and document the Python runtime requirement or bundle a supported launcher.
2. Run Plugin Creator validation against the source plugin.
3. Build the distribution archive and inspect every packaged path.
4. Reject caches, personal paths, local memory, credentials, test artifacts, and stale
   generated files.
5. Update the cachebuster with Plugin Creator's helper.
6. Reinstall from the configured marketplace and start a new thread.
7. Review and trust the exact packaged hooks.
8. Verify all five skills, hook events, storage initialization, memory lifecycle,
   compaction, and optional MCP tools from the installed cache.
9. Verify update, downgrade/rollback, disable, uninstall, and retained-data behavior.
10. Publish release notes, migration notes, known limitations, privacy terms, and the
    completed scorecard.

### Exit gate

- Source, archive, and installed-cache tests all pass.
- A clean machine can install and complete the quickstart without repository knowledge.
- Release artifacts are reproducible and contain no private state.
- The release checklist and evidence report are complete.

## 23. CI And Quality Gates

The final CI pipeline should run these jobs:

1. Formatting and static validation.
2. Unit tests by module.
3. Storage migration tests.
4. Hook contract tests.
5. Skill adapter contract tests.
6. Concurrency stress tests.
7. Retrieval and token-budget tests.
8. Source-blind semantic quality tests.
9. Performance benchmarks with regression thresholds.
10. PluginEval quick on every pull request.
11. PluginEval standard on release candidates.
12. Plugin Creator validation.
13. Package hygiene and archive inspection.
14. Source and installed-cache smoke tests.
15. Cross-platform matrix.

No release job may silently downgrade a failed semantic or packaging gate to a warning.

## 24. Recommended Commit Sequence

1. `test: lock semantic and lifecycle baselines`
2. `refactor: introduce memory application services`
3. `feat: add schema v2 migration and sqlite concurrency settings`
4. `feat: track source provenance and stale memory`
5. `feat: add trust lifecycle and conflict review`
6. `feat: enforce preference evidence policy`
7. `feat: harden ingestion and retention policy`
8. `feat: add budgeted explainable context packets`
9. `fix: make hooks idempotent and compaction-safe`
10. `docs: finish public skill workflows and references`
11. `feat: add optional local memory mcp facade`
12. `test: add security recovery and endurance gates`
13. `chore: certify and package recall release`

Schema migration, hook behavior, and optional MCP work should remain separate commits so
each can be reviewed and rolled back independently.

## 25. Final Release Checklist

- [ ] All Definition of Done items pass.
- [ ] All phase exit gates have recorded evidence.
- [ ] Current official Codex docs have been rechecked for skills, hooks, MCP, plugins,
      memories, and config changes.
- [ ] Plugin Creator validation passes.
- [ ] All skills pass PluginEval standard and deep release gates.
- [ ] Source-blind semantic evaluation passes.
- [ ] Concurrency, migration, recovery, and cross-platform tests pass.
- [ ] Token and latency budgets pass at all required store sizes.
- [ ] Source archive and installed-cache behavior match.
- [ ] Privacy, terms, install, migration, troubleshooting, and release docs are current.
- [ ] Hook trust and new-thread pickup are verified from a clean installation.
- [ ] No open P0 or P1 issue remains.
- [ ] Release scorecard is published with limitations stated honestly.

## 26. First Execution Slice

Begin with a narrow pull request containing only Phase 0 and the compatibility shell of
Phase 1:

1. Add source-blind and mixed-history baseline fixtures.
2. Add the machine-readable release scorecard.
3. Record current semantic, performance, and PluginEval results.
4. Introduce application request/response models without changing behavior.
5. Move one read-only path, `review-memory`, through the new service boundary.
6. Run the complete current quality suite and compare against baseline.

This first slice establishes evidence and the internal boundary needed for every later
phase without risking the current storage format.
