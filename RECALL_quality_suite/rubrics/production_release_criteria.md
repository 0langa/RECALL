# Production Release Criteria

Current truth: RECALL should be treated as alpha-stage until staged promotion evidence says otherwise.

## Stage path

Promotion path:

1. Alpha
2. Beta
3. Release Candidate
4. Final Product

The current project is not Final Product by default just because automated tests pass.

## Promotion evidence required at every stage

### Automated gates

- [ ] `python -m unittest discover -s tests` passes from `plugins/recall`.
- [ ] `scripts/smoke_recall.py --json` passes.
- [ ] Static plugin contract passes.
- [ ] Public skill adapter contract passes.
- [ ] Hook lifecycle contract passes.
- [ ] Source-blind retrieval-readiness contract passes.
- [ ] Performance benchmark passes configured thresholds.
- [ ] Built ZIP package hygiene passes.
- [ ] Build wrapper succeeds on the target release platform.
- [ ] README, privacy, terms, install, changelog, and release docs are current.

### Runtime safety

- [ ] All runtime memory stays inside the active project memory directory (`.recall/`, or legacy `.codex_memory/` when that fallback is active).
- [ ] `.recall/` and `.codex_memory/` runtime data are never included in release artifacts.
- [ ] Secret-like strings are redacted before storage.
- [ ] Malformed hook payloads safely no-op.
- [ ] Hook failures must not block the user's Codex session.
- [ ] Existing memory can be repaired if the vector index is missing/corrupt.
- [ ] SQLite old-schema records still migrate/read correctly.
- [ ] JSONL corrupt rows are skipped and diagnosed.

### Retrieval quality

- [ ] Current/active memory outranks superseded memory.
- [ ] Structured fields, tags, status, importance, and category weights affect ranking as intended.
- [ ] High-signal durable categories can beat noisy session summaries.
- [ ] Failure/debug queries surface risks and debug history.
- [ ] Query ordering is deterministic under equal scores.

## Stage-specific expectations

### Alpha

- Foundation behavior exists, but important quality evidence may still be incomplete.
- Synthetic source-blind fixtures are acceptable at this stage.
- Install flow may still depend on maintainer verification.

### Beta

- Install, repair, stale handling, and public workflow evidence must be repeatable.
- Real project-history-backed source-blind fixtures should begin replacing purely synthetic coverage.
- Major release blockers must be explicitly tracked.

### Release Candidate

- End-to-end install lifecycle, package hygiene, and performance evidence must all pass.
- Source-blind answers must be current-aware, specific, and low-hallucination.
- Open blockers should be rare, explicit, and unacceptable for final release.

### Final Product

- Normal-user install path is validated.
- Source-blind human evaluation is mandatory for final release.
- Security, privacy, and long-session memory quality expectations are supported by evidence.

## Source-blind human evaluation

A fresh agent with access only to the active RECALL memory store must answer the three quality-gate questions with:

- Average score per question >= 4.5 / 5.
- No scoring category below 4.
- Hallucination safety = 5 for every question.
- Current-state awareness = 5 for every question.
- Any confident false source-code, architecture, or project-state claim is an automatic failure.

## Open release blockers

Record unresolved blockers here until fixed.

- [ ] Human source-blind evaluation has not yet been run and passed against the final rubric.
  Blocks Final Product.
  Evidence: the suite has automated source-blind retrieval checks and eval-pack generation, but no recorded hidden-ground-truth human gate result yet.
- [ ] The normal-user install story still depends on local Python availability and interactive Codex hook trust review.
  Blocks Final Product.
  Evidence: `plugins/recall/README.md` and `plugins/recall/docs/RECALL_V1_COMPLETION_PLAN.md` both document Python-runtime and hook-trust constraints.
- [ ] Source-blind fixture realism is improved but still partial; it now includes project-history-backed cards, not a completed long-session or human-scored evidence set.
  Blocks Release Candidate promotion if blind answers remain weak or inconsistent.
  Evidence: the quality suite now includes mixed synthetic and project-history-backed blind cards, but long-session blind evidence and human-scored convergence are still pending.

## Release blocker examples

- Any runtime data in package ZIP.
- Any unredacted token/password/API-key-like value stored by RECALL.
- Any hook crash on malformed JSON.
- Any source-blind answer that fabricates exact code details absent from memory.
- Any stale memory treated as current truth.
