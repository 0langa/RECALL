# RECALL Agent Implementation Protocol

Future Codex agents working on RECALL must follow this protocol.

## read first

Read these before editing:

- `RECALL_quality_suite/README.md`
- `RECALL_quality_suite/RUNBOOK.md`
- `RECALL_quality_suite/docs/TEST_PLAN.md`
- `RECALL_quality_suite/docs/DEVELOPMENT_WORKFLOW.md`
- `RECALL_quality_suite/docs/TDD_PROCESS.md`
- `RECALL_quality_suite/docs/RELEASE_ROADMAP_GATES.md`
- `RECALL_quality_suite/docs/MEMORY_QUALITY_EVOLUTION_PLAN.md`
- `RECALL_quality_suite/rubrics/production_release_criteria.md`
- `RECALL_quality_suite/rubrics/source_blind_quality_gate.md`
- `plugins/recall/README.md`
- `plugins/recall/docs/RELEASE_CHECKLIST.md`

## plan work

- Verify repo state first.
- Identify whether current work is docs-only, refactor, behavior, hook, storage, packaging, or release-process work.
- State current maturity truth plainly: RECALL is alpha-stage unless gates prove otherwise.
- Choose the minimum required validation set before editing.

## update tests

- Add or update failing tests first when practical for behavior or suite-structure changes.
- Prefer existing suite locations unless a new area needs a distinct contract file.
- Keep tests aligned with the public surface and current documented truth.
- Add source-blind fixture/test updates when memory expectations change.

## run validation

Always run at least:

```bash
python RECALL_quality_suite/scripts/run_recall_quality_suite.py --repo-root . --quick
```

If plugin code changed, also run:

```bash
cd plugins/recall
python -m unittest discover -s tests
python ./scripts/smoke_recall.py --json
```

Escalate to full suite, performance, build, and package checks when change scope requires them.

## update docs

Update docs in the same task when behavior, release truth, validation commands, or memory expectations change.

Do not leave control docs behind the code.

## preserve release criteria

- Keep `rubrics/production_release_criteria.md` strict.
- Keep `rubrics/source_blind_quality_gate.md` mandatory for final release.
- Record blockers instead of downgrading the bar.

## never

Never do these:

- Never call alpha behavior final, production-ready, or release-ready without evidence.
- Never weaken gates just because current code cannot pass them yet.
- Never hide failing evidence behind vague status language.
- Never treat RECALL memory as infallible source of truth.
- Never remove safety/privacy expectations to make a release easier.

## final status

Report:

- files created
- files modified
- tests run
- test results
- remaining gaps
- next recommended task

Be concise, but include any blocker or non-run validation explicitly.
