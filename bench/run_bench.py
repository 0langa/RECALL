#!/usr/bin/env python3
"""RECALL benchmark CLI.

    python bench/run_bench.py run --mode light [--seed N] [--price-per-million X]
                                  [--baseline bench/baselines/vX.json] [--out DIR]
    python bench/run_bench.py judge-aggregate --tasks <judge_tasks.jsonl> --scores <judge_scores.jsonl>
    python bench/run_bench.py compliance-setup [--out DIR] [--seed N]
    python bench/run_bench.py compliance-grade --workdir DIR

Deterministic engine benchmark; makes zero LLM/API calls. See bench/README.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BENCH_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH_ROOT))

from recall_bench import BENCH_SCHEMA_VERSION, baseline as baseline_mod, compliance, judge, metrics, report as report_mod, scenarios as scenarios_mod  # noqa: E402
from recall_bench.engine import BenchEngine  # noqa: E402
from recall_bench.probes import run_probes  # noqa: E402
from recall_bench.recorder import Recorder, read_journal  # noqa: E402


def recall_version() -> str:
    manifest = BENCH_ROOT.parent / "plugins" / "recall" / ".claude-plugin" / "plugin.json"
    return json.loads(manifest.read_text(encoding="utf-8"))["version"]


def load_config(args: argparse.Namespace) -> dict:
    if args.config:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    else:
        config = json.loads((BENCH_ROOT / "configs" / f"{args.mode}.json").read_text(encoding="utf-8"))
    if args.seed is not None:
        config["seed"] = args.seed
    if args.sessions is not None:
        config["sessions_per_scenario"] = args.sessions
    if args.turn_limit is not None:
        config["turn_limit"] = args.turn_limit
    return config


def cmd_run(args: argparse.Namespace) -> int:
    config = load_config(args)
    out_dir = Path(args.out) if args.out else BENCH_ROOT / "runs" / f"{config['mode']}-{config['seed']}"
    out_dir.mkdir(parents=True, exist_ok=True)
    journal_path = out_dir / "journal.jsonl"
    recorder = Recorder(journal_path)
    engine = BenchEngine(recorder, seed=config["seed"], keep_dirs=args.keep_dirs)
    scenario_list = scenarios_mod.load_all(BENCH_ROOT / "scenarios", config["scenarios"])
    try:
        if config["phases"].get("static", True):
            engine.measure_static_surfaces()
        scenario_results: dict[str, dict] = {}
        if config["phases"].get("scenarios", True):
            for scenario in scenario_list:
                scenario_results[scenario["name"]] = engine.run_scenario(
                    scenario,
                    sessions=config.get("sessions_per_scenario", 1),
                    turn_limit=config.get("turn_limit"),
                )
        if config["phases"].get("probes", True):
            probe_name = config.get("probe_scenario")
            if probe_name in scenario_results:
                target = scenario_results[probe_name]
            else:
                probe_scenario = scenarios_mod.load_all(BENCH_ROOT / "scenarios", [probe_name])[0]
                target = engine.run_scenario(probe_scenario, sessions=1, turn_limit=0)
            run_probes(recorder, root=target["root"], manifest=target["manifest"], scenario=probe_name, limit=config.get("probe_limit", 5))
        if config["phases"].get("long_run") and config.get("long_run"):
            long_config = config["long_run"]
            long_scenario = scenarios_mod.load_all(BENCH_ROOT / "scenarios", [long_config["scenario"]])[0]
            long_scenario = {**long_scenario, "name": f"longrun_{long_scenario['name']}"}
            engine.run_scenario(long_scenario, sessions=int(long_config["sessions"]), turn_limit=config.get("turn_limit"))
    finally:
        recorder.close()
        engine.cleanup()

    journal = read_journal(journal_path)
    computed = metrics.compute(journal, price_per_million=args.price_per_million)
    result = {
        "meta": {
            "bench_schema_version": BENCH_SCHEMA_VERSION,
            "mode": config["mode"],
            "seed": config["seed"],
            "recall_version": recall_version(),
            "scenarios": config["scenarios"],
            "sessions_per_scenario": config.get("sessions_per_scenario", 1),
            "emission_hash": _emission_hash(journal),
            "journal": str(journal_path),
        },
        "metrics": computed,
    }
    if args.baseline:
        comparison = baseline_mod.compare(result, baseline_mod.load(Path(args.baseline)))
        result["baseline_comparison"] = comparison
    if config.get("judge", {}).get("emit"):
        emitted = judge.emit_tasks(journal, out_dir / "judge_tasks.jsonl", seed=config["seed"], max_per_rubric=config["judge"].get("max_per_rubric", 10))
        result["meta"]["judge_tasks"] = {**emitted, "path": str(out_dir / "judge_tasks.jsonl")}

    (out_dir / "report.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "report.md").write_text(report_mod.render_markdown(result), encoding="utf-8")
    if args.save_baseline:
        baseline_mod.save(result, Path(args.save_baseline))
    print(json.dumps({
        "status": "pass" if result.get("baseline_comparison", {}).get("pass", True) else "fail",
        "report": str(out_dir / "report.json"),
        "markdown": str(out_dir / "report.md"),
        "fixed_overhead_est_tokens": computed["tokens"]["fixed_overhead_per_session_est_tokens"],
        "marginal_per_turn_est_tokens": computed["tokens"]["marginal_per_turn_est_tokens"],
        "secret_leaks": computed["secret_leaks"]["leaks_found"],
        "emission_hash": result["meta"]["emission_hash"],
    }, indent=2))
    if result.get("baseline_comparison") and not result["baseline_comparison"]["pass"] and args.strict:
        return 1
    return 0


def _emission_hash(journal: list[dict]) -> str:
    import hashlib
    import json as json_mod

    from recall_bench.recorder import normalize_for_hash

    digest = hashlib.sha256()
    for entry in journal:
        if entry.get("kind") == "emission":
            digest.update(json_mod.dumps(
                {
                    "channel": entry.get("channel"),
                    "scenario": entry.get("scenario"),
                    "session": entry.get("session"),
                    "turn": entry.get("turn"),
                    "text": normalize_for_hash(entry.get("text", "")),
                },
                sort_keys=True,
            ).encode("utf-8"))
    return digest.hexdigest()


def cmd_judge_aggregate(args: argparse.Namespace) -> int:
    summary = judge.aggregate(Path(args.tasks), Path(args.scores))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def cmd_compliance_setup(args: argparse.Namespace) -> int:
    out_dir = Path(args.out) if args.out else BENCH_ROOT / "runs" / "compliance"
    result = compliance.setup(BENCH_ROOT / "compliance_tasks" / "tasks.json", out_dir, seed=args.seed or 1337)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_compliance_grade(args: argparse.Namespace) -> int:
    result = compliance.grade(Path(args.workdir), BENCH_ROOT / "compliance_tasks" / "tasks.json")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="RECALL benchmark harness (deterministic, no LLM calls).")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run")
    run.add_argument("--mode", choices=["light", "normal", "complete"], default="light")
    run.add_argument("--config", help="Custom config JSON (overrides --mode preset).")
    run.add_argument("--seed", type=int)
    run.add_argument("--sessions", type=int, help="Override sessions per scenario.")
    run.add_argument("--turn-limit", type=int, help="Cap turns per scenario script.")
    run.add_argument("--price-per-million", type=float, help="USD per million input tokens for cost projection.")
    run.add_argument("--baseline", help="Baseline report.json to compare against.")
    run.add_argument("--save-baseline", help="Write this run's report as a baseline file.")
    run.add_argument("--out", help="Output directory (default bench/runs/<mode>-<seed>).")
    run.add_argument("--strict", action="store_true", help="Exit 1 when baseline comparison fails.")
    run.add_argument("--keep-dirs", action="store_true", help="Keep temp project dirs for inspection.")
    run.set_defaults(handler=cmd_run)

    judge_parser = sub.add_parser("judge-aggregate")
    judge_parser.add_argument("--tasks", required=True)
    judge_parser.add_argument("--scores", required=True)
    judge_parser.set_defaults(handler=cmd_judge_aggregate)

    setup_parser = sub.add_parser("compliance-setup")
    setup_parser.add_argument("--out")
    setup_parser.add_argument("--seed", type=int)
    setup_parser.set_defaults(handler=cmd_compliance_setup)

    grade_parser = sub.add_parser("compliance-grade")
    grade_parser.add_argument("--workdir", required=True)
    grade_parser.set_defaults(handler=cmd_compliance_grade)

    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
