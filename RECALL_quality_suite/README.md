# RECALL Quality Suite

A source-aware and source-blind testing/evaluation suite for the active development and production-readiness phase of **RECALL**, the Codex local-first project-memory plugin.

This package is designed to be unzipped into the root of the `0langa/RECALL` repository, but it can also run from outside the repo by passing `--repo-root` or `--plugin-root`.

RECALL is not final yet. Treat it as alpha-stage unless the roadmap gates and production criteria prove otherwise.

## What it adds

- Static plugin-shape and manifest contract checks.
- Public `recall_skill.py` CLI contract tests.
- Hook lifecycle integration tests using realistic Codex hook payloads.
- Source-blind retrieval-readiness tests for architecture, decision history, and implementation-planning memory.
- Performance benchmark for write/query/rebuild/doctor operations.
- Package hygiene checks for built ZIP artifacts.
- Human scoring rubrics for the real source-blind agent evaluation.
- Production-release criteria and result interpretation docs.
- CI workflow template.

## Control docs

Use these as the development-control system for RECALL:

- [RUNBOOK.md](RUNBOOK.md)
- [docs/TEST_PLAN.md](docs/TEST_PLAN.md)
- [docs/EXTENDING.md](docs/EXTENDING.md)
- [docs/DEVELOPMENT_WORKFLOW.md](docs/DEVELOPMENT_WORKFLOW.md)
- [docs/TDD_PROCESS.md](docs/TDD_PROCESS.md)
- [docs/RELEASE_ROADMAP_GATES.md](docs/RELEASE_ROADMAP_GATES.md)
- [docs/MEMORY_QUALITY_EVOLUTION_PLAN.md](docs/MEMORY_QUALITY_EVOLUTION_PLAN.md)
- [docs/AGENT_IMPLEMENTATION_PROTOCOL.md](docs/AGENT_IMPLEMENTATION_PROTOCOL.md)
- [rubrics/production_release_criteria.md](rubrics/production_release_criteria.md)
- [rubrics/source_blind_quality_gate.md](rubrics/source_blind_quality_gate.md)
- [docs/RESULTS_INTERPRETATION.md](docs/RESULTS_INTERPRETATION.md)

## Quick start

From the repository root:

```bash
python recall_quality_suite/scripts/run_recall_quality_suite.py --repo-root .
```

From the plugin root:

```bash
cd plugins/recall
python ../../recall_quality_suite/scripts/run_recall_quality_suite.py --plugin-root .
```

Fast local loop:

```bash
python recall_quality_suite/scripts/run_recall_quality_suite.py --repo-root . --quick
```

The runner executes independent gates in parallel by default. The quick runner also uses the smaller performance benchmark profile for active development. Full release evidence still requires the non-quick run.

Serial diagnostic run:

```bash
python recall_quality_suite/scripts/run_recall_quality_suite.py --repo-root . --quick --serial
```

Use `--jobs <n>` to cap concurrent gates when the machine is already under load.

Performance-only:

```bash
python recall_quality_suite/perf/benchmark_recall_memory.py --plugin-root plugins/recall --records 500 --queries 30
```

Package hygiene, after building `dist/recall.zip`:

```bash
python recall_quality_suite/scripts/package_hygiene_check.py --plugin-root plugins/recall --zip plugins/recall/dist/recall.zip
```

## Output

The runner writes:

```text
quality_results/
  recall_quality_report.json
  recall_quality_report.md
```

The process exits non-zero if a mandatory gate fails.
