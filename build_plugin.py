#!/usr/bin/env python3
"""Repo-root wrapper for the RECALL plugin builder."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Build the RECALL plugin from the repository root.")
    parser.add_argument("--output-dir", default=str(root / "dist"))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--skip-validator", action="store_true")
    args = parser.parse_args()

    command = [
        args.python,
        str(root / "plugins" / "recall" / "scripts" / "build_plugin.py"),
        "--plugin-root",
        str(root / "plugins" / "recall"),
        "--output-dir",
        args.output_dir,
        "--python",
        args.python,
    ]
    if args.skip_validator:
        command.append("--skip-validator")
    completed = subprocess.run(command, cwd=root)
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
