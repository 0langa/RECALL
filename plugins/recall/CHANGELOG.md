# Changelog

## 1.6.0 - 2026-09-13

Release candidate.
This entry does not claim that the tag or public release exists.

- Made SQLite save selection and writes use one `BEGIN IMMEDIATE` transaction.
- Added a store-local process lock and atomic per-file replacement to the JSONL write path.
- Kept JSONL as a supported backend for normal process concurrency.
- Documented that JSONL has no multi-file rollback and that multi-file power-loss safety is not certified.
- Added stable retry keys across public save and confirmation paths.
- Added explicit preference scope to save identity.
- Made public root resolution fail closed for missing or ambiguous project roots.
- Added a memory-free turn guard before public memory work and hook memory-data access.
- Added observed-evidence receipts for material successful test, build, and release results.
- Required exact fact evidence before a card can become `validated`.
- Stopped status labels, counters, session names, timestamps, and caller-supplied receipt data from acting as proof.
- Kept structured claim keys and values opaque and exact.
- Kept conflicting current claim values separate and marked them for review.
- Added stable hygiene plan and operation identities.
- Separated scan, output, and action limits.
- Made hygiene apply require the exact reviewed plan.
- Added CLI `hygiene-plan --save-plan` and `hygiene-apply --plan-file` flow.
- Kept the MCP full-plan flow unchanged.
- Documented that the legacy `claim_key` plan route uses `response.plan` for apply.
- Added source-observation checks before hygiene actions.
- Added a known fail-closed follow-up: saved plans reject equivalent `./README.md` and `.\README.md` source forms; use canonical `README.md` and create a new plan.
- Preserved retrieval health warnings when card selection or budget limits remove all card text.
- Hardened secret-shape handling while keeping unlabelled 40-hex Git revisions usable.
- Added a bounded 5,000-card synthetic SQLite regression check.
- Recorded its candidate-to-v1.5.5 median ratio as `0.9974007` under high host load.
- Made no speed claim from that check.
- Updated architecture text from the old 64-D value to the actual 256-D local hash embedder.
- Moved the Codex MCP server declaration to the root `.mcp.json` file that current Codex loads.
- Set GitHub install pins to `v1.6.0`.

Evidence limits at candidate freeze:

- Runtime Review A found two P1 and two P2 defects.
- The one allowed fix pass addressed them, and Review B passed with no open P0 or P1.
- Final clean-candidate source gates are still required before release acceptance.
- Exact ZIP proof is pending.
- Native installed-package proof is pending.
- Matched-benefit proof is pending.
- CI proof is pending.
- Tag and public release proof are pending.
- The 21-case hygiene fixture is bounded lexical evidence, not broad semantic truth proof.

Host readiness used Codex CLI `0.154.0`, Claude Code `2.1.268`, and Kimi Code `0.42.0`.
Readiness does not prove the exact package.
Final public evidence belongs with the [v1.6.0 GitHub release](https://github.com/0langa/RECALL/releases/tag/v1.6.0).

## 1.5.5 - 2026-08-19

- Declared `mcpServers` inline in the Codex manifest.
- Matched the Claude Code and Kimi Code MCP server declarations.
- Removed the need for a manual Codex MCP entry.

## 1.5.4 - 2026-08-05

- Refreshed release-roadmap truth.
- Moved quality workflow actions to Node 24 runtimes.

## 1.5.3 - 2026-07-27

- Removed workstation-specific names and paths from public files.
- Added a regression guard for personal path data.

## 1.5.2 - 2026-07-12

- Added marketplace artwork metadata for Codex.
- Kept provider manifests and MCP metadata version aligned.

## 1.5.1 - 2026-07-11

- Added transactional SQLite idempotency-key writes.
- Added SQLite corruption checks and backup restore support.
- Added an install-pin contract test.

## 1.5.0 - 2026-07-06

- Fixed secret-scanner false positives for common type and self-reference text.
- Fixed two skill quality findings.
- Made the strict light benchmark a blocking CI gate.

## 1.4.0 - 2026-07-06

- Added IDF, FTS5 reranking, and local hash embedding signals.
- Changed the local hash embedder from 64 to 256 dimensions.
- Kept paraphrase results separate from blocking lexical and safety gates.

## 1.3.0 - 2026-07-05

- Added document-duplicate checks, configurable staleness, compact retrieval output, capture modes, and blocking lint gates.

## 1.2.0 - 2026-07-05

- Added the canonical behavior contract, MCP lifecycle tools, health flags, hygiene checks, and cross-provider parity tests.

## 1.1.1 - 2026-07-02

- Rejected more secret-shaped content on save and route paths.

## 1.1.0 - 2026-07-02

- Added the seventh public skill, provider-neutral storage, Kimi Code support, Claude Code support, and provider provenance.

## 1.0.0 - 2026-06-16

- Added project activation, buffered hooks, lifecycle tools, schema v2, source provenance, conflict handling, export/import, three-platform CI, and public review commands.

## 0.1.0 - 2026-06-06

- Added the first Codex plugin, SQLite and JSONL storage, local retrieval, hooks, skills, smoke tests, package inspection, and build flow.
