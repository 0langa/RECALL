# Source-Blind Memory Operating Layer Quality Gate

This gate is mandatory for final release. Final release is blocked until this evaluation passes.

## Setup

1. Fresh agent session.
2. Agent sees only the generated `codex_memory` eval-pack folder, copied from the active RECALL memory store.
3. Repository, source files, Git history, issues, and docs are blocked.
4. Evaluator has hidden ground truth from real repo, docs, commits, and maintainer knowledge.
5. Ask the three questions below.

## Gate 1: Current architecture and responsibility map

> Based only on the generated `codex_memory` eval-pack folder, reconstruct the current architecture of the project. Include main components, responsibilities, interactions, owned files/data/artifacts, memory-layer workflow, RECALL's role, boundaries, invariants, non-goals, and known uncertainties.

## Gate 2: Historical decisions, reversals, and regression risks

> Using only the generated `codex_memory` eval-pack folder, identify the most important technical decisions made so far. For each, explain the decision, rationale, rejected alternatives, current/deprecated status, later refinements, regressions prevented, and what future agents must not undo.

## Gate 3: Source-free implementation planning

> Based only on the generated `codex_memory` eval-pack folder, propose a concrete implementation plan for the next high-priority feature/fix/improvement. Include affected areas, expected behavior, dependencies, steps, risks, conventions, validation, avoid-list, and what cannot be known without source access.

## Scoring dimensions

Score 0-5:

1. Factual accuracy.
2. Specificity.
3. Completeness.
4. Historical awareness.
5. Current-state awareness.
6. Actionability.
7. Hallucination safety.
8. Regression prevention.

## Passing standard

- No category below 4.
- Average per question >= 4.5.
- Hallucination safety must be 5 for all questions.
- Current-state awareness must be 5 for all questions.
- Confident false claims are automatic failures for the affected question.
- Failing this gate means RECALL is not eligible for final release.
