---
name: recall-bench
description: Use this skill when the user explicitly asks to run, judge, or compare a RECALL benchmark (e.g. "run a judged normal bench", "recall-bench light", "benchmark RECALL against the baseline"). It runs the deterministic bench harness, optionally acts as the LLM judge for emitted judge tasks, aggregates scores, and reports results. Never invoke for ordinary RECALL memory usage, plugin development, or test-suite runs.
---

# RECALL Benchmark Runner (repo-local skill)

Run the RECALL benchmark end to end, including the judged variant, and report
a concise summary. You (the invoked agent) are the judge — that is by design:
the harness makes zero LLM/API calls, and the user invokes this skill from a
session whose model they consider cheap enough to score rubrics.

Work from the repository root (the directory containing `bench/`). All
commands are local; nothing here contacts a network or needs credentials.

## Arguments

Parse from the user's request; defaults in bold:

- mode: `light` | **`normal`** | `complete`
- judged: **yes** if the user says "judged"/"with judge"; otherwise no
- baseline: compare against `bench/baselines/<latest>.json` **when one exists**
- price: pass `--price-per-million <X>` if the user names a price; else omit

## Workflow

1. Run the harness (this part is deterministic and free):

```bash
python bench/run_bench.py run --mode <mode> [--emit-judge] [--baseline bench/baselines/<latest>.json] [--price-per-million X]
```

Use `--emit-judge` only for judged runs. `complete` mode emits judge tasks by
itself. Outputs land in `bench/runs/<mode>-<seed>/`.

2. If judged — score the tasks YOURSELF, then aggregate:
   - Read `bench/runs/<mode>-<seed>/judge_tasks.jsonl`. The first line is a
     header whose `score_schema` defines the output shape. Every other line is
     one task: `rubric`, `instructions` (a 1–5 rubric), and `artifact`.
   - For each task, score strictly per its `instructions`. One-sentence
     justification, no longer. Include the boolean flags a rubric asks for
     (`contains_noise` for card_quality, `would_mislead` for
     injection_usefulness). Copy `task_id` exactly.
   - Write one JSON line per task to
     `bench/runs/<mode>-<seed>/judge_scores.jsonl`.
   - Aggregate:

```bash
python bench/run_bench.py judge-aggregate --tasks bench/runs/<mode>-<seed>/judge_tasks.jsonl --scores bench/runs/<mode>-<seed>/judge_scores.jsonl
```

   - If the aggregate reports entries under `invalid`, fix those score lines
     and re-run the aggregate. Coverage (`scored/of_tasks`) must be complete.

3. Report to the user, in this order:
   - PASS/FAIL of baseline comparison (list any violations verbatim)
   - Token cost: fixed overhead/session, marginal/turn, 20-turn projection
     (+ dollars if priced)
   - Quality: injection-gate accuracy, golden retrieval hit rate, flag
     correctness, hygiene detection, secret-leak sweep result
   - Judge means per rubric + flag counts (judged runs only)
   - Paths: `report.md`, `report.json`, `judge_scores.jsonl`
   - The `emission_hash` (note if it changed vs the previous run of the same
     mode+seed while the code was unchanged — that means behavior drifted)

## Hard rules

- Never modify engine code, scenarios, labels, thresholds, or baselines to
  improve numbers. If a metric looks wrong, report it — do not fix it here.
- Never write a new baseline (`--save-baseline`) unless the user explicitly
  asks for one.
- Judge scoring happens in THIS session only; never spawn paid sub-agents or
  call external services for judging.
- If `judge_tasks.jsonl` is missing after a judged run, say so and show the
  run's stdout — do not fabricate scores.
- Layer-2 compliance runs (`compliance-setup`/`compliance-grade`) are a
  separate, human-mediated workflow — mention `bench/README.md` if asked, do
  not run them from this skill.

## Example

User: "run a judged normal bench at $3 per million"

```bash
python bench/run_bench.py run --mode normal --emit-judge --price-per-million 3.0 --baseline bench/baselines/v1.3.0.json
# ...score bench/runs/normal-1337/judge_tasks.jsonl -> judge_scores.jsonl yourself...
python bench/run_bench.py judge-aggregate --tasks bench/runs/normal-1337/judge_tasks.jsonl --scores bench/runs/normal-1337/judge_scores.jsonl
```

Then summarize as in step 3.
