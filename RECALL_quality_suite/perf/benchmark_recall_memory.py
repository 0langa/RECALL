#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


def resolve_plugin_root(raw: str | None) -> Path:
    if raw:
        root = Path(raw).expanduser().resolve()
    else:
        cwd = Path.cwd().resolve()
        candidates = [cwd, cwd / "plugins" / "recall", cwd.parent / "plugins" / "recall"]
        for candidate in candidates:
            if (candidate / "scripts" / "memory_manager.py").exists():
                return candidate
        raise SystemExit("Could not locate plugin root. Pass --plugin-root.")
    if not (root / "scripts" / "memory_manager.py").exists():
        raise SystemExit(f"Invalid plugin root: {root}")
    return root


def load_thresholds(path: Path) -> dict[str, float]:
    return json.loads(path.read_text(encoding="utf-8"))


def select_threshold_profile(thresholds: dict[str, Any], records: int, queries: int) -> tuple[str, dict[str, float]]:
    quick_records = int(thresholds.get("quick_records", 0))
    quick_queries = int(thresholds.get("quick_queries", 0))
    if quick_records and quick_queries and records <= quick_records and queries <= quick_queries:
        return "quick", {
            "max_seed_seconds": float(thresholds.get("quick_max_seed_seconds", thresholds["max_seed_seconds"])),
            "max_rebuild_seconds": float(thresholds.get("quick_max_rebuild_seconds", thresholds["max_rebuild_seconds"])),
            "max_doctor_seconds": float(thresholds.get("quick_max_doctor_seconds", thresholds["max_doctor_seconds"])),
            "max_query_p95_ms": float(thresholds.get("quick_max_query_p95_ms", thresholds["max_query_p95_ms"])),
            "max_query_average_ms": float(thresholds.get("quick_max_query_average_ms", thresholds["max_query_average_ms"])),
        }
    return "full", {
        "max_seed_seconds": float(thresholds["max_seed_seconds"]),
        "max_rebuild_seconds": float(thresholds["max_rebuild_seconds"]),
        "max_doctor_seconds": float(thresholds["max_doctor_seconds"]),
        "max_query_p95_ms": float(thresholds["max_query_p95_ms"]),
        "max_query_average_ms": float(thresholds["max_query_average_ms"]),
    }


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((p / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark RECALL storage/retrieval performance.")
    parser.add_argument("--plugin-root", help="Path to plugins/recall")
    parser.add_argument("--records", type=int)
    parser.add_argument("--queries", type=int)
    parser.add_argument("--thresholds", default=str(Path(__file__).with_name("perf_thresholds.json")))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    plugin_root = resolve_plugin_root(args.plugin_root)
    thresholds = load_thresholds(Path(args.thresholds))
    records = args.records or int(thresholds["records"])
    queries = args.queries or int(thresholds["queries"])
    threshold_profile, active_thresholds = select_threshold_profile(thresholds, records, queries)

    sys.path.insert(0, str(plugin_root / "scripts"))
    import memory_manager  # type: ignore  # noqa: E402

    categories = ["architecture", "requirements", "risks", "commands", "debug_history", "tasks", "decisions"]
    query_texts = [
        "architecture hooks memory storage",
        "requirements local first codex_memory",
        "risks hook payload drift",
        "commands unittest smoke recall",
        "debug history failure assertion",
        "decisions sqlite jsonl local backend",
    ]

    with tempfile.TemporaryDirectory(prefix="recall-perf-") as tmp:
        start = time.perf_counter()
        for i in range(records):
            category = categories[i % len(categories)]
            memory_manager.add_record(
                category,
                f"Benchmark memory {i}: {category} validates RECALL local-first retrieval, hooks, storage, and release quality gates.",
                memory_manager.build_card_metadata(
                    summary=f"Benchmark {category} card {i}",
                    tags=["benchmark", category, f"batch-{i % 10}"],
                    source="quality-benchmark",
                    status="active" if i % 11 else "open",
                    importance=(i % 10) / 10.0,
                    confidence=0.9,
                ),
                root=tmp,
            )
        seed_seconds = time.perf_counter() - start

        start = time.perf_counter()
        rebuild = memory_manager.rebuild_index(tmp)
        rebuild_seconds = time.perf_counter() - start

        start = time.perf_counter()
        doctor = memory_manager.doctor(tmp)
        doctor_seconds = time.perf_counter() - start

        latencies_ms: list[float] = []
        for i in range(queries):
            q = query_texts[i % len(query_texts)]
            t0 = time.perf_counter()
            result = memory_manager.query(q, root=tmp, summarize=True, limit=8)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            latencies_ms.append(elapsed_ms)
            if not result["results"]:
                raise AssertionError(f"Query returned no results: {q}")

    report: dict[str, Any] = {
        "status": "pass",
        "plugin_root": str(plugin_root),
        "records": records,
        "queries": queries,
        "threshold_profile": threshold_profile,
        "seed_seconds": round(seed_seconds, 4),
        "rebuild_seconds": round(rebuild_seconds, 4),
        "doctor_seconds": round(doctor_seconds, 4),
        "query_average_ms": round(statistics.mean(latencies_ms), 4),
        "query_p50_ms": round(percentile(latencies_ms, 50), 4),
        "query_p95_ms": round(percentile(latencies_ms, 95), 4),
        "doctor_index_complete": bool(doctor["index_complete"]),
        "indexed_records": rebuild["indexed_records"],
        "thresholds": active_thresholds,
        "failures": [],
    }

    checks = [
        ("seed_seconds", report["seed_seconds"], active_thresholds["max_seed_seconds"]),
        ("rebuild_seconds", report["rebuild_seconds"], active_thresholds["max_rebuild_seconds"]),
        ("doctor_seconds", report["doctor_seconds"], active_thresholds["max_doctor_seconds"]),
        ("query_average_ms", report["query_average_ms"], active_thresholds["max_query_average_ms"]),
        ("query_p95_ms", report["query_p95_ms"], active_thresholds["max_query_p95_ms"]),
    ]
    for name, value, limit in checks:
        if value > limit:
            report["failures"].append(f"{name}={value} exceeded {limit}")
    if not report["doctor_index_complete"]:
        report["failures"].append("doctor reported incomplete index")
    if report["indexed_records"] != records:
        report["failures"].append(f"indexed_records={report['indexed_records']} expected {records}")

    if report["failures"]:
        report["status"] = "fail"

    print(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
