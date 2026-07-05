# RECALL Benchmark & Evaluation Harness

Maintainer tooling — lives in the repository, never ships in the plugin zip.
Measures what RECALL actually costs and how well it behaves, provider-local,
with **zero LLM/API calls** in the harness itself.

## Why token cost is measurable offline

RECALL never calls a model. Its entire API-token cost is what it injects into
the agent's context: session-start context, tool schemas, retrieval
injections, tool results, system messages. The harness drives the real hooks
(stdin JSON), the real MCP server (stdio JSON-RPC), and the real skill
adapter, records every agent-visible emission tagged by channel (taxonomy in
`recall_bench/channels.py`, derived from `token_usage_surfaces.md`), and
reports:

- **fixed overhead per session** (paid even if memory is never used),
- **marginal cost per turn**, and a 20-turn session projection,
- optional `$` projection via `--price-per-million`.

## Layer 1 — deterministic engine benchmark

```bash
python bench/run_bench.py run --mode light                      # <~60s smoke
python bench/run_bench.py run --mode normal --price-per-million 3.0
python bench/run_bench.py run --mode normal --emit-judge --price-per-million 3.0
python bench/run_bench.py run --mode complete --save-baseline bench/baselines/vX.Y.Z.json
python bench/run_bench.py run --config my_custom_config.json    # custom sets
python bench/run_bench.py run --mode light --baseline bench/baselines/v1.3.0.json --strict
```

Outputs land in `bench/runs/<mode>-<seed>/`: `journal.jsonl` (every emission +
latency + probe + snapshot), `report.json` (machine), `report.md` (human).

Measured surfaces: token cost per channel, injection-gate confusion matrix
(labeled scenario turns), golden-query retrieval precision/MRR, lifecycle
flag correctness, conflict marking, write-time dedup, secret rejection,
hygiene detection/false positives on a planted-bad pack, compact-vs-verbose
delta, contract exposure, hook latencies p50/p95, store growth over long-run
session replay, and a secret-leak sweep over every recorded emission.

**Determinism:** same seed → identical `emission_hash` (volatile substrings —
timestamps, temp paths, age-drifting scores — are normalized out). A changed
hash with an unchanged version means behavior changed; find out why.

**Custom configs** are the primary interface; `light`/`normal`/`complete` are
just presets in `bench/configs/`. Scenario scripts live in `bench/scenarios/`
(schema enforced by `recall_bench/scenarios.py`; label turns with
`should_inject` ground truth). Fabricated stores: tiers fresh/working/mature,
plus golden retrieval targets, lifecycle-flagged cards, claim conflicts, and
a planted-bad hygiene pack (`recall_bench/store_fabricator.py`).

## Layer 2 — agent compliance (the calling agent is the test subject)

```bash
python bench/run_bench.py compliance-setup            # builds one sandbox per task
# follow bench/runs/compliance/INSTRUCTIONS.md: run each task prompt in a
# FRESH agent session with cwd = that task's workspace (RECALL installed).
python bench/run_bench.py compliance-grade --workdir bench/runs/compliance
```

Task prompts never reveal expected RECALL behavior. Grading is artifact-based:
store diffs, debug traces, store content — should-save/shouldn't-save,
category choice, secret refusal, update-vs-duplicate, retrieval evidence
(hook path only; direct MCP retrieval is not observable from artifacts).
Compliance results are model-dependent — keep them in a separate bucket from
Layer 1 numbers and never blend them into one score.

## Judge (optional LLM scoring — always manual)

The harness only emits and aggregates files; it never calls a model.

**One-message shortcut:** the repo-local skill `.claude/skills/recall-bench/`
wraps this whole section — invoke `recall-bench` ("run a judged normal bench")
from any agent session opened in this repo and that agent runs the harness,
acts as the judge itself, aggregates, and reports. Invoke it from a
cheap-model session; the session's model is the judge. Manual steps below
remain the underlying mechanism.

1. Run with judge emission on (complete preset does): produces `judge_tasks.jsonl`.
2. Give the file to ANY agent (a cheap one — the rubrics are simple 1–5
   scores) with: "Score each task per its instructions; write one JSON line
   per task to judge_scores.jsonl matching the score_schema in the header."
3. Aggregate:

```bash
python bench/run_bench.py judge-aggregate --tasks .../judge_tasks.jsonl --scores .../judge_scores.jsonl
```

Sanity-check a judge run: the aggregate reports `invalid` for malformed
entries and `scored/of_tasks` coverage. Re-judging an old journal with a
different model is always possible — journals are the source of truth.

## Baselines & CI

Release baselines live in `bench/baselines/<version>.json`
(`--save-baseline`). Compare any run with `--baseline`; add `--strict` to
exit 1 on violations (token growth beyond thresholds, quality drops, any
secret leak). Default thresholds: `recall_bench/baseline.py`. CI runs light
mode non-blocking and uploads the report; flip to `--strict` once baselines
have proven stable.

## Harness self-tests

```bash
python -m pytest bench/tests -q
```
