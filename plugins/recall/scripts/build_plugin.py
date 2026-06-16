#!/usr/bin/env python3
"""Cross-platform RECALL plugin build and package script."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


INCLUDE = [
    ".codex-plugin",
    "assets",
    "skills",
    "hooks",
    "scripts",
    "docs",
    "examples",
    "memory_config.template.json",
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
]


def run_checked(args: list[str], cwd: Path) -> None:
    completed = subprocess.run(args, cwd=cwd)
    if completed.returncode != 0:
        raise SystemExit(f"Command failed with exit code {completed.returncode}: {' '.join(args)}")


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


def build(plugin_root: Path, output_dir: Path, python: str, skip_validator: bool) -> Path:
    plugin_root = plugin_root.resolve()
    if not output_dir.is_absolute():
        output_dir = plugin_root / output_dir
    output_dir = output_dir.resolve()
    archive = output_dir / "recall.zip"
    package_root = output_dir / "_package"

    run_checked([python, "-m", "unittest", "discover", "-s", "tests"], plugin_root)

    validator = default_validator()
    if validator.is_file() and not skip_validator:
        run_checked([python, str(validator), str(plugin_root)], plugin_root)
    elif not skip_validator:
        print(f"Warning: plugin validator not found at {validator}; skipping validator gate.", file=sys.stderr)

    run_checked([python, str(plugin_root / "scripts" / "smoke_recall.py"), "--json"], plugin_root)

    copy_package_tree(plugin_root, package_root)
    try:
        zip_tree(package_root, archive)
    finally:
        if package_root.exists():
            shutil.rmtree(package_root)

    run_checked([python, str(plugin_root / "scripts" / "inspect_package.py"), str(archive)], plugin_root)
    print(f"Built {archive}")
    return archive


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the RECALL plugin zip package.")
    parser.add_argument("--plugin-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output-dir", default="dist")
    parser.add_argument("--python", default=os.environ.get("PYTHON", sys.executable))
    parser.add_argument("--skip-validator", action="store_true")
    args = parser.parse_args()

    build(Path(args.plugin_root), Path(args.output_dir), args.python, args.skip_validator)


if __name__ == "__main__":
    main()
