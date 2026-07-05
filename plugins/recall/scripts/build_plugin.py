#!/usr/bin/env python3
"""Cross-platform RECALL plugin build and package script."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path


INCLUDE = [
    ".codex-plugin",
    ".claude-plugin",
    "assets",
    "skills",
    "hooks",
    "scripts",
    "docs",
    "examples",
    "memory_config.template.json",
    "kimi.plugin.json",
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
]


def run_checked(name: str, args: list[str], cwd: Path, timeout: int) -> None:
    started = time.perf_counter()
    print(f"[build] {name}: start")
    try:
        completed = subprocess.run(args, cwd=cwd, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - started
        raise SystemExit(f"[build] {name}: timed out after {elapsed:.2f}s: {' '.join(args)}") from exc
    elapsed = time.perf_counter() - started
    if completed.returncode != 0:
        raise SystemExit(f"[build] {name}: failed after {elapsed:.2f}s with exit code {completed.returncode}: {' '.join(args)}")
    print(f"[build] {name}: pass in {elapsed:.2f}s")


def remove_cache_artifacts(root: Path) -> None:
    for path in sorted(root.rglob("__pycache__"), reverse=True):
        if path.is_dir():
            shutil.rmtree(path)
    for suffix in ("*.pyc", "*.pyo"):
        for path in root.rglob(suffix):
            path.unlink()


def copy_package_tree(plugin_root: Path, package_root: Path) -> None:
    if package_root.exists():
        shutil.rmtree(package_root)
    package_root.mkdir(parents=True)
    for item in INCLUDE:
        source = plugin_root / item
        if not source.exists():
            continue
        destination = package_root / item
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    remove_cache_artifacts(package_root)


def zip_tree(source: Path, archive: Path) -> None:
    if archive.exists():
        archive.unlink()
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(source).as_posix())


def default_validator() -> Path:
    return Path.home() / ".codex" / "skills" / ".system" / "plugin-creator" / "scripts" / "validate_plugin.py"


def build(
    plugin_root: Path,
    output_dir: Path,
    python: str,
    skip_validator: bool,
    skip_tests: bool,
    skip_smoke: bool,
    step_timeout: int,
) -> Path:
    plugin_root = plugin_root.resolve()
    if not output_dir.is_absolute():
        output_dir = plugin_root / output_dir
    output_dir = output_dir.resolve()
    archive = output_dir / "recall.zip"
    package_root = output_dir / "_package"

    if not skip_tests:
        run_checked("unit tests", [python, str(plugin_root / "scripts" / "run_tests.py"), "--exclude-smoke"], plugin_root, step_timeout)

    validator = default_validator()
    if validator.is_file() and not skip_validator:
        run_checked("plugin validator", [python, str(validator), str(plugin_root)], plugin_root, step_timeout)
    elif not skip_validator:
        print(f"Warning: plugin validator not found at {validator}; skipping validator gate.", file=sys.stderr)

    if not skip_smoke:
        run_checked("smoke harness", [python, str(plugin_root / "scripts" / "smoke_recall.py"), "--json"], plugin_root, step_timeout)

    started = time.perf_counter()
    print("[build] package zip: start")
    copy_package_tree(plugin_root, package_root)
    try:
        zip_tree(package_root, archive)
    finally:
        if package_root.exists():
            shutil.rmtree(package_root)
    print(f"[build] package zip: pass in {time.perf_counter() - started:.2f}s")

    run_checked("package inspection", [python, str(plugin_root / "scripts" / "inspect_package.py"), str(archive)], plugin_root, step_timeout)
    print(f"Built {archive}")
    return archive


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the RECALL plugin zip package.")
    parser.add_argument("--plugin-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output-dir", default="dist")
    parser.add_argument("--python", default=os.environ.get("PYTHON", sys.executable))
    parser.add_argument("--skip-validator", action="store_true")
    parser.add_argument("--skip-tests", action="store_true", help="Skip unit tests. Intended only for CI package jobs that depend on the unit job.")
    parser.add_argument("--skip-smoke", action="store_true", help="Skip smoke harness. Intended only for CI package jobs that depend on the smoke job.")
    parser.add_argument("--step-timeout", type=int, default=600, help="Seconds before an individual build gate times out.")
    args = parser.parse_args()

    build(
        Path(args.plugin_root),
        Path(args.output_dir),
        args.python,
        args.skip_validator,
        args.skip_tests,
        args.skip_smoke,
        args.step_timeout,
    )


if __name__ == "__main__":
    main()
