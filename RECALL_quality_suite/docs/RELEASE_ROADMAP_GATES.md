# RECALL Release Roadmap Gates

Current truth: the current project should be treated as alpha-stage unless hard evidence proves promotion criteria have passed.

## Promotion rules

- Promotion is sequential: Alpha -> Beta -> Release Candidate -> Final Product.
- Passing lower-stage gates does not imply higher-stage readiness.
- A stage is achieved only when its required capabilities, evidence, docs, and blockers all satisfy the gate.

## Alpha

Alpha means foundation exists but correctness, install reliability, and memory quality are still under active hardening.

### Required capabilities

- Local-first memory storage under project `.codex_memory/`.
- Public save/retrieve/category workflows exist.
- Core hooks exist and fail safely.
- Doctor/repair/rebuild path exists in some usable form.

### Required test evidence

- Core plugin unit tests pass.
- Quick quality suite passes.
- Smoke harness proves basic source checkout behavior.

### Required docs

- README, install guidance, privacy, terms, release checklist.
- Quality suite README, runbook, test plan.

### Source-blind expectations

- Synthetic source-blind fixtures exist.
- Fresh-agent answers are directionally useful, but not yet sufficient for release.

### Performance expectations

- No obvious unbounded regressions in basic write/query flows.

### Security/privacy expectations

- Local-only design remains true.
- Secret-like content is redacted.
- Runtime memory stays out of artifacts.

### Install lifecycle expectations

- Maintainer can install and smoke-test the plugin from source or marketplace setup.

### Blocks promotion to Beta

- Missing repeatable install evidence.
- Missing regression coverage on public workflows.
- Memory quality still mostly synthetic or fragile.

## Beta

Beta means real development use is plausible, but stage-hardening and blind-eval quality are not yet final.

### Required capabilities

- Stable public CLI/skill surface.
- Reliable stale/superseded memory handling.
- Repair/doctor workflows prove recoverability.
- Hook write policy avoids obvious noisy or dangerous captures.

### Required test evidence

- Full plugin tests pass.
- Quick and full suite pass in maintainer environment.
- Performance benchmark passes configured thresholds.
- Package hygiene passes on built artifact.

### Required docs

- Development workflow, TDD process, roadmap gates, memory evolution plan, and agent protocol are current.
- Release blockers are recorded explicitly.

### Source-blind expectations

- Source-blind fixtures include real project-history-backed facts, not only synthetic cards.
- Blind answers are specific, current-aware, and honest about uncertainty.

### Performance expectations

- Query/write/rebuild/doctor performance is within conservative thresholds.

### Security/privacy expectations

- Redaction holds in positive and failure paths.
- Corrupt or malformed inputs degrade safely.

### Install lifecycle expectations

- Installed-bundle smoke and installed-cache verification are repeatable.
- New-thread skill discovery is verified.

### Blocks promotion to Release Candidate

- Source-blind evidence still weak or inconsistent.
- Install lifecycle still maintainer-fragile.
- Performance or package hygiene failures.

## Release Candidate

Release Candidate means RECALL is candidate-quality for normal users, but still awaiting final promotion evidence.

### Required capabilities

- Silent high-quality memory maintenance across real development work.
- Fresh-session context recovery without stale guidance dominating.
- Clear review/reconciliation workflow for stale, superseded, merged, and archived memory.
- Honest handling of unknowns and contradictions.

### Required test evidence

- Full automated suite passes.
- Full plugin validation, smoke, build, package inspection, and hygiene all pass.
- No unresolved release blocker remains for the RC scope.

### Required docs

- Release notes and checklist reflect current behavior exactly.
- Source-blind rubric and production criteria are current.

### Source-blind expectations

- Blind answers consistently reconstruct architecture, decisions, and next-step plans from memory alone.
- Hallucination safety and current-state awareness are strong enough to make RC evaluation meaningful.

### Performance expectations

- Long-session accumulation does not cause obvious collapse in relevance or latency under benchmarked loads.

### Security/privacy expectations

- No known unredacted secret-storage path remains.
- Repair/rebuild flows do not leak or fabricate state.

### Install lifecycle expectations

- A normal Codex user can install, enable, trust hooks, and complete core workflows without maintainer-only tricks.

### Blocks promotion to Final Product

- Human source-blind gate not yet passed at final threshold.
- Any install step still depends on tribal knowledge.
- Any unresolved contradiction/staleness failure that can mislead users.

## Final Product

Final Product means the product promise is true in evidence, not aspiration.

### Required capabilities

- Normal-user install path works.
- RECALL silently maintains useful project memory during long real work.
- Fresh sessions recover high-signal current context.
- Stale or hallucinated guidance is actively suppressed or surfaced honestly.
- Repair/self-healing workflows recover from degraded memory/index state.

### Required test evidence

- Automated suite passes.
- Plugin tests and smoke pass.
- Performance benchmark passes.
- Package hygiene passes on final artifact.
- Release checklist passes end to end.

### Required docs

- All user, maintainer, rubric, and release docs match final behavior.

### Source-blind expectations

- Mandatory final source-blind human evaluation passes with no confident false claims.

### Performance expectations

- Long-session and rebuild behavior remain within declared conservative thresholds for supported environments.

### Security/privacy expectations

- Local-only, redaction, package hygiene, and safe-failure guarantees hold in evidence.

### Install lifecycle expectations

- Source and built-zip installation paths are documented and validated.

### What blocks promotion beyond this stage

- Any regression that breaks the final product promise returns the project to an earlier practical stage until fixed.
