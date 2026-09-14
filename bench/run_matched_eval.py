#!/usr/bin/env python3
"""Prepare and audit offline evidence for the five-family, four-arm matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from recall_bench import matched


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--repo", required=True, type=Path)
    prepare.add_argument("--commit", required=True)
    prepare.add_argument("--zip", type=Path)
    prepare.add_argument("--fixture", type=Path, default=Path(__file__).parent / "matched_tasks" / "tasks.json")
    prepare.add_argument("--evidence", required=True, type=Path)
    prepare.add_argument("--subjects", required=True, type=Path)
    prepare.add_argument("--host", required=True, type=Path, help="JSON with actual host name/version")
    prepare.add_argument("--models", required=True, type=Path, help="JSON mapping four arms to model names")
    begin = sub.add_parser("begin")
    begin.add_argument("--family", required=True, choices=matched.FAMILIES)
    begin.add_argument("--arm", required=True, choices=matched.ARMS)
    payload = sub.add_parser("subject-input")
    payload.add_argument("--phase", required=True)
    seal = sub.add_parser("seal")
    for name in ("trace", "raw", "observation", "assessment"):
        seal.add_argument("--" + name, type=Path)
    report = sub.add_parser("report")
    for command in (begin, payload, seal, report):
        command.add_argument("--evidence", required=True, type=Path)
    for command in (payload, seal):
        command.add_argument("--attempt", required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            value = matched.prepare(args.repo, args.commit, args.fixture, args.evidence, args.subjects,
                                    matched.read_json(args.host), matched.read_json(args.models), args.zip)
        elif args.command == "begin":
            value = matched.begin(args.evidence, args.family, args.arm)
        elif args.command == "subject-input":
            value = matched.subject_input(args.evidence, args.attempt, args.phase)
        elif args.command == "seal":
            value = matched.seal(args.evidence, args.attempt, args.trace, args.raw, args.observation, args.assessment)
        else:
            value = matched.summarize(args.evidence)
        print(json.dumps(value, indent=2, sort_keys=True, allow_nan=False))
        # Unknown proof must not look like a passing gate to a shell caller.
        return {"pass": 0, "fail": 1, "blocked": 1, "unknown": 2}.get(value.get("status"), 0)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
