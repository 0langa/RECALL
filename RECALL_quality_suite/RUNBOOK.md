# RECALL Quality Suite Runbook

## Development workflow entry point

Read these first and follow them in order:

1. `docs/DEVELOPMENT_WORKFLOW.md`
2. `docs/TDD_PROCESS.md`
3. `docs/RELEASE_ROADMAP_GATES.md`
4. `docs/MEMORY_QUALITY_EVOLUTION_PLAN.md`
5. `docs/AGENT_IMPLEMENTATION_PROTOCOL.md`

Use this runbook for command execution after the workflow is understood.

## Local active-development loop

```bash
python RECALL_quality_suite/scripts/run_recall_quality_suite.py --repo-root . --quick
```

Use this after normal code edits.

The suite runs independent gates in parallel by default. If a failure looks order-sensitive or resource-sensitive, rerun serially:

```bash
python RECALL_quality_suite/scripts/run_recall_quality_suite.py --repo-root . --quick --serial
```

## Full pre-release loop

```bash
cd plugins/recall
python -m unittest discover -s tests
python ./scripts/smoke_recall.py --json
cd ../..
python RECALL_quality_suite/scripts/run_recall_quality_suite.py --repo-root .
```

Then build the plugin ZIP and run package hygiene:

```bash
cd plugins/recall
python ..\..\RECALL_quality_suite\scripts\package_hygiene_check.py --plugin-root . --zip dist/recall.zip
```

## Source-blind agent evaluation pack

```bash
python RECALL_quality_suite/scripts/source_blind_agent_gate.py --plugin-root plugins/recall --out-dir source_blind_eval_pack
```

Give the test agent only:

```text
source_blind_eval_pack/codex_memory/
source_blind_eval_pack/agent_questions.md
```

Keep the evaluator scorecard and fixture inventory hidden:

```text
source_blind_eval_pack/evaluator_scorecard.md
source_blind_eval_pack/fixture_inventory.json
```

## Result files

```text
quality_results/recall_quality_report.json
quality_results/recall_quality_report.md
```

## Stage discipline

- Treat RECALL as alpha-stage unless promotion evidence says otherwise.
- The source-blind gate is required for final release, not optional polish.
- Record any promotion blocker in `rubrics/production_release_criteria.md` before closing work.
