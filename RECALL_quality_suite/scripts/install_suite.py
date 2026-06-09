#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy recall_quality_suite into a RECALL repository.")
    parser.add_argument("repo_root", help="Path to the RECALL repository root")
    parser.add_argument("--with-ci", action="store_true", help="Also copy the GitHub Actions workflow template")
    args = parser.parse_args()

    src = Path(__file__).resolve().parents[1]
    repo = Path(args.repo_root).expanduser().resolve()
    dst = repo / "recall_quality_suite"

    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("*.zip", "quality_results", "__pycache__"))

    if args.with_ci:
        workflow_dst = repo / ".github" / "workflows" / "recall-quality.yml"
        workflow_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / "ci" / "recall-quality.yml", workflow_dst)

    print(f"Installed quality suite to {dst}")


if __name__ == "__main__":
    main()
