# RECALL — Status & Roadmap
_Maintenance audit: 2026-08-05_

## What this is

Local-first persistent project memory for AI coding agents. RECALL stores decisions,
requirements, risks, commands, and debugging history in a per-project `.recall/` store (legacy
`.codex_memory/` still readable) and serves it back to Codex, Claude Code, and Kimi Code through
one shared plugin: seven public skills, provider hooks, and an MCP server over a single engine.
No hosted service, no network calls, secret-shaped content rejected at write time.

Stack: Python 3.11, SQLite (schema v2, FTS5) with a JSONL alternative, deterministic local 256-D
hash embeddings, three provider manifests (`.codex-plugin/`, `.claude-plugin/`,
`kimi.plugin.json`) over one codebase in `plugins/recall/scripts/`, pytest, GitHub Actions.

## Current state

- **Released: v1.5.3** — `main` is tagged and the GitHub release contains `recall.zip`; stable
  Codex installation is pinned to `--ref v1.5.3`. Tag history now includes v1.5.1, v1.5.2, and
  v1.5.3 after v1.5.0. One shared source tree continues to ship the Codex, Claude Code, and Kimi
  manifests.
- **Batch-5 production hardening shipped as v1.5.1**, rather than remaining an unreleased v1.6.0
  candidate: idempotency-key writes are transactional, `doctor`/`repair` handle store corruption,
  install pins have regression coverage, and CI tools are pinned. v1.5.2 added Codex artwork
  metadata; v1.5.3 removed workstation-specific public metadata and added a regression guard.
- **Current validation (2026-08-05)**: the CI-style non-smoke runner passes all 29 test modules;
  exact CI-pinned Ruff and Mypy pass; the 17 bench-harness tests and strict light benchmark pass
  with zero secret leaks; the quick quality suite and documented portable package build pass.
  The latest remote `RECALL Quality` workflow for v1.5.3 completed successfully.
- **Quality gates**: `.github/workflows/recall-quality.yml` runs lint, strict `bench-light`, a
  six-way unit matrix, coverage, three-OS smoke, quality suite, and package jobs. The release
  build validates the manifest when the local validator is available, runs source smoke, and
  inspects the generated ZIP.
- **Follow-up risks to verify before changing them**:
  - The hook layer needs broader fixture coverage, especially malformed and provider-specific
    payloads.
  - Near-duplicate hygiene is a full-table fuzzy scan; benchmark it at a substantially larger
    store before changing its algorithm.
  - The local hash embedder has finite paraphrase headroom; keep that metric separate from the
    blocking lexical and safety gates.
  - The optional judged benchmark has no recorded judge baseline, and live provider hook-payload
    drift still needs versioned fixtures.

## Release discipline

v1.5.3 is the current shipped baseline. Do not cut v1.6.0 merely to re-release Batch-5 work that
already shipped in v1.5.1. A future release should have a deliberate user-facing scope and:

- version alignment in the three manifests, `kimi_mcp_server.py`, and
  `test_package_metadata.py`;
- a rebuilt, inspected `recall.zip` and a published GitHub release;
- the full lint, strict benchmark, unit, smoke, quality, and package gates;
- explicit marketplace work only in its owning repository.

The next maintenance milestone remains:

- `hooks/scripts/` coverage at ≥75% with fixture tests for every hook event.
- Save-time dedup and hygiene scans measured on a ~5,000-record store, with
  `find_related_record` either candidate-filtered or explicitly bounded.
- One judged benchmark run recorded as a quality baseline next to `bench/baselines/`.
- A contract test pinning current live hook payload shapes for all three providers.

## Roadmap

### Phase 1 — Now (next 1–2 weeks)

1. **No release is currently queued.** Select and implement a scoped user-facing change before
   planning another version bump; do not use this roadmap as evidence that v1.6.0 already exists.
2. **Hook-layer test pass.** Fixture-driven tests for `plugins/recall/hooks/scripts/` covering
   SessionStart, UserPromptSubmit (prompt_inspector), PostToolUse, PreCompact, and Stop — happy
   path plus malformed payloads, missing fields, and non-activated projects. Target: lift
   `hook_io.py` and `session_start.py` out of the 40s; consider turning the coverage job into a
   ratchet once the number is respectable.
3. **Run the judged bench once** following `bench/README.md`'s manual instructions (from a
   cheap-model session; never auto-run, per the project's own rule) and commit the aggregated
   judge scores so future retrieval changes have a quality anchor, not just token/latency
   numbers.

### Phase 2 — Next (2–6 weeks)

4. **Scale tier.** Add a ~5k-record tier to the bench store fabricator; measure hygiene scan and
   save-time dedup latency at that size. Then fix the O(n): pre-filter `find_related_record`
   candidates via fingerprint prefix, shared-token bucketing, or an FTS5 candidate query before
   the fuzzy Jaccard pass.
5. **Hook payload drift guard.** Capture real hook payloads from current Codex / Claude Code /
   Kimi CLI versions as versioned fixtures; add contract tests plus a `doctor` check that
   reports unrecognized payload shapes instead of degrading silently.
6. **Paraphrase ceiling decision.** Either document 0.6 as the accepted local-first ceiling in
   README, or add an opt-in, config-gated embedding backend (user-supplied local model path;
   still zero-network, never ship weights). The remaining misses are zero-shared-vocabulary
   queries no lexical method can reach.

### Phase 3 — Later (optional/stretch)

7. Embedding-based doc-duplication detection — the current check is lexical token containment
   against README/docs paragraphs and misses paraphrased duplicates (PROJECT_STATE deferred
   item).
8. Legacy-store bench tier using a real user-supplied `.codex_memory` store, plus
   `migrate-store` validation at scale.
9. Scheduled CI job that reruns the smoke matrix against the latest provider CLI releases — the
   2026-06-25 cross-provider retest was manual; automating it would catch provider breakage
   between releases.
10. Consolidate the root-level planning docs (WORK_STATUS.md at 26 KB, the 45 KB architecture
    blueprint, `token_usage_surfaces.md`) into `docs/` with a short index; they're valuable
    history but currently crowd the repo root a new contributor sees first.

## Effort to "finished"

**M.** The hook-coverage, scale, and payload-drift work are roughly 2–3 part-time weeks combined.
Any future release estimate depends on its deliberately chosen scope.
