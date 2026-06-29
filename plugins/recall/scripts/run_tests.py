#!/usr/bin/env python3
"""Run the RECALL unittest suite with per-file process isolation."""

from __future__ import annotations

import argparse
import concurrent.futures
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import time


@dataclass(frozen=True)
class TestResult:
    path: str
    seconds: float
    returncode: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.returncode == 0


def default_workers(test_count: int) -> int:
    if test_count <= 1:
        return 1
    cpu_count = os.cpu_count() or 2
    return max(1, min(4, cpu_count, test_count))


def discover_tests(tests_dir: Path, pattern: str, *, exclude_smoke: bool) -> list[Path]:
    paths = sorted(tests_dir.glob(pattern))
    if exclude_smoke:
        paths = [path for path in paths if path.name != "test_smoke_recall.py"]
    return [path for path in paths if path.is_file()]


def run_test_file(plugin_root: Path, python: str, path: Path) -> TestResult:
    module = f"tests.{path.stem}"
    start = time.perf_counter()
    completed = subprocess.run(
        [python, "-m", "unittest", module],
        cwd=plugin_root,
        text=True,
        capture_output=True,
    )
    return TestResult(
        path=path.name,
        seconds=time.perf_counter() - start,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def run_all(plugin_root: Path, python: str, tests: list[Path], workers: int) -> list[TestResult]:
    if workers <= 1:
        return [run_test_file(plugin_root, python, path) for path in tests]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(run_test_file, plugin_root, python, path) for path in tests]
        return [future.result() for future in concurrent.futures.as_completed(futures)]


def result_payload(results: list[TestResult], elapsed: float, workers: int) -> dict[str, object]:
    failures = [result for result in results if not result.passed]
    return {
        "status": "pass" if not failures else "fail",
        "elapsed_seconds": round(elapsed, 3),
        "workers": workers,
        "files": len(results),
        "failures": [result.path for result in failures],
        "results": [
            {
                "path": result.path,
                "seconds": round(result.seconds, 3),
                "returncode": result.returncode,
            }
            for result in sorted(results, key=lambda item: item.seconds, reverse=True)
        ],
    }


def print_text_report(results: list[TestResult], elapsed: float, workers: int) -> None:
    payload = result_payload(results, elapsed, workers)
    print(f"RECALL tests {payload['status']} in {elapsed:.2f}s with {workers} worker(s).")
    for result in sorted(results, key=lambda item: item.seconds, reverse=True):
        status = "OK" if result.passed else f"FAIL {result.returncode}"
        print(f"{result.seconds:7.2f}s  {status:7}  {result.path}")
    for result in sorted(results, key=lambda item: item.path):
        if result.passed:
            continue
        print(f"\n=== {result.path} stdout ===")
        print(result.stdout.rstrip())
        print(f"\n=== {result.path} stderr ===")
        print(result.stderr.rstrip())


def main() -> None:
    default_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Run RECALL unittest files in parallel.")
    parser.add_argument("--plugin-root", default=str(default_root))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--pattern", default="test_*.py")
    parser.add_argument("--workers", type=int)
    parser.add_argument("--sequential", action="store_true")
    parser.add_argument("--exclude-smoke", action="store_true", help="Skip test_smoke_recall.py when a caller runs the smoke gate separately.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    plugin_root = Path(args.plugin_root).resolve()
    tests = discover_tests(plugin_root / "tests", args.pattern, exclude_smoke=args.exclude_smoke)
    if not tests:
        raise SystemExit(f"No tests matched {args.pattern!r} under {plugin_root / 'tests'}")

    workers = 1 if args.sequential else (args.workers or default_workers(len(tests)))
    workers = max(1, min(workers, len(tests)))
    start = time.perf_counter()
    results = run_all(plugin_root, args.python, tests, workers)
    elapsed = time.perf_counter() - start

    if args.json:
        print(json.dumps(result_payload(results, elapsed, workers), indent=2, sort_keys=True))
    else:
        print_text_report(results, elapsed, workers)

    if any(not result.passed for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
