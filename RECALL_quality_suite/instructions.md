# RECALL Quality Suite Bootstrap Task

You are working in the `0langa/RECALL` repository.

Your objective is to turn the current `RECALL_quality_suite` into the central development-control system for RECALL from its current alpha-stage state toward the final production-grade product described below.

RECALL is not final yet. Treat it as alpha-stage unless hard evidence proves otherwise.

Final product promise:

> RECALL can be installed by a normal Codex user, silently maintain high-quality project memory across long real development work, recover useful context in a fresh session, avoid stale or hallucinated guidance, protect secrets, repair itself when memory/index state degrades, and pass strict automated plus source-blind human evaluation gates.

Until that is true, RECALL is only a foundation, alpha, beta, or release candidate.

## Your First Required Action

Before editing code, read and understand:

```text
RECALL_quality_suite/README.md
RECALL_quality_suite/RUNBOOK.md
RECALL_quality_suite/docs/TEST_PLAN.md
RECALL_quality_suite/docs/EXTENDING.md
RECALL_quality_suite/rubrics/production_release_criteria.md
RECALL_quality_suite/rubrics/source_blind_quality_gate.md
plugins/recall/README.md
plugins/recall/docs/RELEASE_CHECKLIST.md
````

If any of these files are missing, create or repair them as part of this task.

## Main Goal

Upgrade the current quality suite so it does not merely test existing RECALL behavior, but actively defines and enforces the development path from alpha to final product.

The suite must become a strict, maintainable, test-driven development framework for RECALL.

## Required Deliverables

Create or improve the following documentation files:

```text
RECALL_quality_suite/docs/DEVELOPMENT_WORKFLOW.md
RECALL_quality_suite/docs/TDD_PROCESS.md
RECALL_quality_suite/docs/RELEASE_ROADMAP_GATES.md
RECALL_quality_suite/docs/MEMORY_QUALITY_EVOLUTION_PLAN.md
RECALL_quality_suite/docs/AGENT_IMPLEMENTATION_PROTOCOL.md
```

These files must be concrete, strict, and actionable. They must not be vague essays.

## Required Content

### DEVELOPMENT_WORKFLOW.md

Define how RECALL development must proceed from now on.

Include:

* how agents classify each change
* which test layer must be touched for each change type
* required validation commands
* when docs must be updated
* when source-blind fixtures must be updated
* how release blockers are recorded
* how memory discipline is preserved during RECALL’s own development

### TDD_PROCESS.md

Define the test-first process.

Include:

* rule that meaningful behavior changes require tests
* unit vs integration vs source-blind vs performance test selection
* how to write failing tests first when practical
* how to handle bugs
* how to handle refactors
* how to handle docs-only changes
* what counts as “done”
* what is forbidden, such as weakening tests to pass

### RELEASE_ROADMAP_GATES.md

Define milestone gates:

* Alpha
* Beta
* Release Candidate
* Final Product

For each milestone, include:

* required capabilities
* required test evidence
* required docs
* source-blind expectations
* performance expectations
* security/privacy expectations
* install lifecycle expectations
* what blocks promotion to the next stage

Make clear that the current project should be treated as alpha-stage.

### MEMORY_QUALITY_EVOLUTION_PLAN.md

Define how RECALL memory quality must improve over development.

Include:

* current memory quality expectations
* target final memory quality expectations
* source-blind evaluation process
* stale/superseded memory handling
* contradiction detection expectations
* long-session endurance expectations
* cross-agent consistency expectations
* missing-information honesty expectations
* how fixtures should evolve from synthetic to real project-history-based cases

### AGENT_IMPLEMENTATION_PROTOCOL.md

Define exact rules for future Codex agents working on RECALL.

Include:

* what to read first
* how to plan work
* how to update tests
* how to run validation
* how to update docs
* how to preserve release criteria
* what never to do
* how to report final status
* how to avoid calling alpha behavior final

## Suite Improvements Beyond Docs

After adding those files, inspect the current suite and improve it where obviously needed.

At minimum:

1. Ensure the main suite README links to the new docs.
2. Ensure `RUNBOOK.md` includes the development workflow entry point.
3. Ensure `rubrics/production_release_criteria.md` reflects the alpha → beta → release candidate → final path.
4. Ensure the source-blind quality gate is described as mandatory for final release, not optional.
5. Add or update tests only if needed to verify the new suite structure/docs exist and are discoverable.

## Validation

Run the appropriate checks after changes.

At minimum:

```bash
python RECALL_quality_suite/scripts/run_recall_quality_suite.py --repo-root . --quick
```

Also run existing RECALL tests if the implementation touches plugin code:

```bash
cd plugins/recall
python -m unittest discover -s tests
python ./scripts/smoke_recall.py --json
```

If a command fails, fix the cause. Do not ignore failures.

## Standards

Do not water down the final product definition.

Do not describe RECALL as production-ready, release-ready, or final unless the full gates pass.

Do not remove strict criteria just because the current project cannot satisfy them yet.

Do not make the suite only validate the current codebase. It must guide the future development path.

Do not create vague placeholder docs. Every document must be useful to the next agent.

Do not bypass memory-quality or source-blind evaluation requirements.

## Final Response Format

When finished, report:

* files created
* files modified
* tests run
* test results
* remaining gaps
* next recommended task

Keep the final response concise but complete.

```
```
