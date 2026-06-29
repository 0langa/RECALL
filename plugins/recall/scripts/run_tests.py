#!/usr/bin/env python3
"""Run the RECALL unittest suite with per-file process isolation."""

from __future__ import annotations

import argparse
import concurrent.futures
from dataclasses import dataclass
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest


DEFAULT_SPLIT_METHOD_FILES: set[str] = set()


@dataclass(frozen=True)
class TestResult:
    target: str
    seconds: float
    returncode: int
    stdout: str
    stderr: str
    path: str | None = None

    @property
    def passed(self) -> bool:
        return self.returncode == 0


def default_workers(test_count: int) -> int:
    if test_count <= 1:
        return 1
    cpu_count = os.cpu_count() or 2
    return max(1, min(3, cpu_count, test_count))


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
        target=path.name,
        seconds=time.perf_counter() - start,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        path=path.name,
    )


def run_all(plugin_root: Path, python: str, tests: list[Path], workers: int) -> list[TestResult]:
    if workers <= 1:
        return [run_test_file(plugin_root, python, path) for path in tests]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(run_test_file, plugin_root, python, path) for path in tests]
        return [future.result() for future in concurrent.futures.as_completed(futures)]


def run_mixed(plugin_root: Path, python: str, files: list[Path], methods: list[tuple[str, str]], workers: int) -> list[TestResult]:
    if workers <= 1:
        return [run_test_file(plugin_root, python, path) for path in files] + [
            run_test_method(plugin_root, python, path_name, method_id)
            for path_name, method_id in methods
        ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(run_test_file, plugin_root, python, path) for path in files]
        futures.extend(
            executor.submit(run_test_method, plugin_root, python, path_name, method_id)
            for path_name, method_id in methods
        )
        return [future.result() for future in concurrent.futures.as_completed(futures)]


def iter_suite_tests(suite) -> list[unittest.case.TestCase]:
    tests = []
    for item in suite:
        if hasattr(item, "__iter__") and not isinstance(item, unittest.case.TestCase):
            tests.extend(iter_suite_tests(item))
        else:
            tests.append(item)
    return tests


def discover_methods(plugin_root: Path, tests: list[Path]) -> list[tuple[str, str]]:
    plugin_root_text = str(plugin_root)
    inserted_path = False
    if plugin_root_text not in sys.path:
        sys.path.insert(0, plugin_root_text)
        inserted_path = True
    try:
        loader = unittest.TestLoader()
        methods: list[tuple[str, str]] = []
        for path in tests:
            module_name = f"tests.{path.stem}"
            module = importlib.import_module(module_name)
            suite = loader.loadTestsFromModule(module)
            for test in iter_suite_tests(suite):
                methods.append((path.name, test.id()))
        return methods
    finally:
        if inserted_path:
            try:
                sys.path.remove(plugin_root_text)
            except ValueError:
                pass


def run_test_method(plugin_root: Path, python: str, path_name: str, method_id: str) -> TestResult:
    start = time.perf_counter()
    completed = subprocess.run(
        [python, "-m", "unittest", method_id],
        cwd=plugin_root,
        text=True,
        capture_output=True,
    )
    return TestResult(
        target=method_id,
        seconds=time.perf_counter() - start,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        path=path_name,
    )


def run_methods(plugin_root: Path, python: str, methods: list[tuple[str, str]], workers: int) -> list[TestResult]:
    if workers <= 1:
        return [run_test_method(plugin_root, python, path_name, method_id) for path_name, method_id in methods]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(run_test_method, plugin_root, python, path_name, method_id)
            for path_name, method_id in methods
        ]
        return [future.result() for future in concurrent.futures.as_completed(futures)]


def result_payload(
    results: list[TestResult],
    elapsed: float,
    workers: int,
    *,
    profile_methods: bool = False,
    split_method_files: list[str] | None = None,
) -> dict[str, object]:
    failures = [result for result in results if not result.passed]
    payload: dict[str, object] = {
        "status": "pass" if not failures else "fail",
        "elapsed_seconds": round(elapsed, 3),
        "workers": workers,
        "failures": [result.target for result in failures],
        "results": [
            {
                "target": result.target,
                "path": result.path,
                "seconds": round(result.seconds, 3),
                "returncode": result.returncode,
            }
            for result in sorted(results, key=lambda item: item.seconds, reverse=True)
        ],
    }
    if profile_methods:
        payload["methods"] = [
            {
                "id": result.target,
                "path": result.path,
                "seconds": round(result.seconds, 3),
                "returncode": result.returncode,
            }
            for result in sorted(results, key=lambda item: item.seconds, reverse=True)
        ]
        payload["method_count"] = len(results)
    else:
        payload["files"] = len({result.path or result.target for result in results})
        payload["targets"] = len(results)
        payload["split_method_files"] = split_method_files or []
    return payload


def print_text_report(results: list[TestResult], elapsed: float, workers: int, *, profile_methods: bool = False) -> None:
    payload = result_payload(results, elapsed, workers, profile_methods=profile_methods)
    noun = "methods" if profile_methods else "tests"
    print(f"RECALL {noun} {payload['status']} in {elapsed:.2f}s with {workers} worker(s).")
    for result in sorted(results, key=lambda item: item.seconds, reverse=True):
        status = "OK" if result.passed else f"FAIL {result.returncode}"
        print(f"{result.seconds:7.2f}s  {status:7}  {result.target}")
    for result in sorted(results, key=lambda item: item.target):
        if result.passed:
            continue
        print(f"\n=== {result.target} stdout ===")
        print(result.stdout.rstrip())
        print(f"\n=== {result.target} stderr ===")
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
    parser.add_argument("--no-split-methods", action="store_true", help="Run every test file as one unittest process.")
    parser.add_argument("--split-method-file", action="append", default=[], help="Test filename to split into method targets during normal parallel runs.")
    parser.add_argument("--profile-methods", action="store_true", help="Run selected test files one test method per process and report slow methods.")
    parser.add_argument("--profile-target", action="append", default=[], help="Test filename to profile by method. Repeatable. Defaults to every matched test file.")
    parser.add_argument("--method-workers", type=int, help="Parallel workers for --profile-methods. Defaults like --workers.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    plugin_root = Path(args.plugin_root).resolve()
    tests = discover_tests(plugin_root / "tests", args.pattern, exclude_smoke=args.exclude_smoke)
    if args.profile_target:
        target_names = {Path(target).name for target in args.profile_target}
        tests = [path for path in tests if path.name in target_names]
    if not tests:
        raise SystemExit(f"No tests matched {args.pattern!r} under {plugin_root / 'tests'}")

    start = time.perf_counter()
    if args.profile_methods:
        methods = discover_methods(plugin_root, tests)
        workers = 1 if args.sequential else (args.method_workers or args.workers or default_workers(len(methods)))
        workers = max(1, min(workers, len(methods)))
        results = run_methods(plugin_root, args.python, methods, workers)
        split_method_files: list[str] = []
    else:
        split_names = set(args.split_method_file)
        if not args.no_split_methods:
            split_names |= DEFAULT_SPLIT_METHOD_FILES
        split_tests = [path for path in tests if path.name in split_names]
        file_tests = [path for path in tests if path.name not in split_names]
        methods = discover_methods(plugin_root, split_tests) if split_tests else []
        target_count = len(file_tests) + len(methods)
        workers = 1 if args.sequential else (args.workers or default_workers(target_count))
        workers = max(1, min(workers, target_count))
        results = run_mixed(plugin_root, args.python, file_tests, methods, workers)
        split_method_files = [path.name for path in split_tests]
    elapsed = time.perf_counter() - start

    if args.json:
        print(json.dumps(
            result_payload(
                results,
                elapsed,
                workers,
                profile_methods=args.profile_methods,
                split_method_files=split_method_files,
            ),
            indent=2,
            sort_keys=True,
        ))
    else:
        print_text_report(results, elapsed, workers, profile_methods=args.profile_methods)

    if any(not result.passed for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
