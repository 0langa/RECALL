#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def resolve_paths(repo_root: str | None, plugin_root: str | None) -> tuple[Path | None, Path]:
    if plugin_root:
        plugin = Path(plugin_root).expanduser().resolve()
        repo = Path(repo_root).expanduser().resolve() if repo_root else None
    else:
        repo = Path(repo_root).expanduser().resolve() if repo_root else Path.cwd().resolve()
        if (repo / "plugins" / "recall" / "scripts" / "recall_skill.py").exists():
            plugin = repo / "plugins" / "recall"
        elif (repo / "scripts" / "recall_skill.py").exists():
            plugin = repo
        else:
            raise SystemExit("Could not locate plugin root. Pass --repo-root or --plugin-root.")
    if not (plugin / "scripts" / "recall_skill.py").exists():
        raise SystemExit(f"Invalid plugin root: {plugin}")
    return repo, plugin


def run_gate(name: str, cmd: list[str], cwd: Path, env: dict[str, str], optional: bool = False) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True, check=False)
    elapsed = time.perf_counter() - started
    status = "pass" if completed.returncode == 0 else ("skip" if optional else "fail")
    return {
        "name": name,
        "status": status,
        "returncode": completed.returncode,
        "seconds": round(elapsed, 4),
        "command": cmd,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


def parse_json_stdout(gate: dict[str, Any]) -> dict[str, Any] | None:
    try:
        return json.loads(gate.get("stdout_tail", ""))
    except Exception:
        return None


def write_reports(out_dir: Path, report: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "recall_quality_report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    lines = [
        "# RECALL Quality Report",
        "",
        f"Overall status: **{report['status'].upper()}**",
        f"Plugin root: `{report['plugin_root']}`",
        "",
        "| Gate | Status | Seconds |",
        "|---|---:|---:|",
    ]
    for gate in report["gates"]:
        lines.append(f"| {gate['name']} | {gate['status']} | {gate['seconds']} |")
    lines.extend(["", "## Failures", ""])
    failures = [gate for gate in report["gates"] if gate["status"] == "fail"]
    if not failures:
        lines.append("None.")
    else:
        for gate in failures:
            lines.append(f"### {gate['name']}")
            lines.append("")
            lines.append("```text")
            lines.append(gate.get("stderr_tail") or gate.get("stdout_tail") or "No output")
            lines.append("```")
    (out_dir / "recall_quality_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the RECALL comprehensive quality suite.")
    parser.add_argument("--repo-root")
    parser.add_argument("--plugin-root")
    parser.add_argument("--out-dir", default="quality_results")
    parser.add_argument("--quick", action="store_true", help="Use a smaller performance benchmark.")
    parser.add_argument("--skip-existing-unit", action="store_true")
    parser.add_argument("--skip-smoke", action="store_true")
    parser.add_argument("--skip-performance", action="store_true")
    parser.add_argument("--require-package", action="store_true", help="Fail if dist/recall.zip is missing.")
    parser.add_argument("--package-zip", help="Explicit release ZIP path.")
    args = parser.parse_args()

    repo_root, plugin_root = resolve_paths(args.repo_root, args.plugin_root)
    suite_root = Path(__file__).resolve().parents[1]
    out_dir = Path(args.out_dir).expanduser().resolve()

    env = os.environ.copy()
    env["RECALL_PLUGIN_ROOT"] = str(plugin_root)

    gates: list[dict[str, Any]] = []

    if not args.skip_existing_unit:
        gates.append(run_gate(
            "existing_unit_tests",
            [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
            cwd=plugin_root,
            env=env,
        ))

    gates.append(run_gate(
        "quality_suite_contract_tests",
        [sys.executable, "-m", "unittest", "discover", "-s", str(suite_root / "tests"), "-p", "test_*.py"],
        cwd=plugin_root,
        env=env,
    ))

    if not args.skip_smoke:
        smoke = plugin_root / "scripts" / "smoke_recall.py"
        if smoke.exists():
            gates.append(run_gate(
                "existing_smoke_harness",
                [sys.executable, str(smoke), "--json"],
                cwd=plugin_root,
                env=env,
            ))
        else:
            gates.append({"name": "existing_smoke_harness", "status": "fail", "seconds": 0, "returncode": 1, "command": [], "stdout_tail": "", "stderr_tail": "scripts/smoke_recall.py missing"})

    if not args.skip_performance:
        records = "120" if args.quick else "500"
        queries = "10" if args.quick else "30"
        gates.append(run_gate(
            "performance_benchmark",
            [sys.executable, str(suite_root / "perf" / "benchmark_recall_memory.py"), "--plugin-root", str(plugin_root), "--records", records, "--queries", queries],
            cwd=plugin_root,
            env=env,
        ))

    package_cmd = [sys.executable, str(suite_root / "scripts" / "package_hygiene_check.py"), "--plugin-root", str(plugin_root)]
    if args.package_zip:
        package_cmd.extend(["--zip", args.package_zip])
    package_gate = run_gate("package_hygiene", package_cmd, cwd=plugin_root, env=env, optional=not args.require_package)
    parsed_package = parse_json_stdout(package_gate)
    if parsed_package and parsed_package.get("status") == "skip" and args.require_package:
        package_gate["status"] = "fail"
        package_gate["stderr_tail"] = parsed_package.get("reason", "Package missing")
    gates.append(package_gate)

    status = "pass" if all(gate["status"] in {"pass", "skip"} for gate in gates) else "fail"
    report = {
        "status": status,
        "repo_root": str(repo_root) if repo_root else None,
        "plugin_root": str(plugin_root),
        "suite_root": str(suite_root),
        "gates": gates,
    }
    write_reports(out_dir, report)

    print(json.dumps({
        "status": status,
        "report_json": str(out_dir / "recall_quality_report.json"),
        "report_md": str(out_dir / "recall_quality_report.md"),
        "gates": [{"name": gate["name"], "status": gate["status"], "seconds": gate["seconds"]} for gate in gates],
    }, indent=2))

    if status != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
