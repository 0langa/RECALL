#!/usr/bin/env python3
"""Smoke-test a built RECALL zip through a temporary Codex marketplace."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


class ZipMarketplaceSmokeFailure(RuntimeError):
    pass


def run(args: list[str], *, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)
    if check and completed.returncode != 0:
        raise ZipMarketplaceSmokeFailure(
            f"Command failed ({completed.returncode}): {' '.join(args)}\n"
            f"STDOUT: {completed.stdout}\n"
            f"STDERR: {completed.stderr}"
        )
    return completed


def plugin_version(plugin_root: Path) -> str:
    manifest = json.loads((plugin_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    return str(manifest.get("version") or "0.1.0")


def marketplace_payload(marketplace_name: str) -> dict[str, Any]:
    return {
        "name": marketplace_name,
        "interface": {"displayName": "RECALL Zip Smoke"},
        "plugins": [
            {
                "name": "recall",
                "source": {"source": "local", "path": "./plugins/recall"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                "category": "Productivity",
            }
        ],
    }


def run_smoke(zip_path: Path) -> dict[str, Any]:
    if not zip_path.is_file():
        raise ZipMarketplaceSmokeFailure(f"Zip archive does not exist: {zip_path}")

    marketplace_name = f"recall-zip-test-{uuid.uuid4().hex[:8]}"
    temp_root = Path(tempfile.mkdtemp(prefix="recall-zip-marketplace-")).resolve()
    plugin_root = temp_root / "plugins" / "recall"
    marketplace_dir = temp_root / ".agents" / "plugins"
    plugin_root.mkdir(parents=True, exist_ok=True)
    marketplace_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(plugin_root)
        (marketplace_dir / "marketplace.json").write_text(
            json.dumps(marketplace_payload(marketplace_name), indent=2),
            encoding="utf-8",
        )

        version = plugin_version(plugin_root)
        run(["codex", "plugin", "marketplace", "add", str(temp_root)])
        run(["codex", "plugin", "add", f"recall@{marketplace_name}"])
        installed_root = Path.home() / ".codex" / "plugins" / "cache" / marketplace_name / "recall" / version
        smoke = run(
            [
                sys.executable,
                str(ROOT / "scripts" / "smoke_recall.py"),
                "--installed-plugin-root",
                str(installed_root),
                "--json",
            ]
        )
        smoke_report = json.loads(smoke.stdout)
        if smoke_report.get("status") != "pass":
            raise ZipMarketplaceSmokeFailure(f"Installed-cache smoke failed: {smoke.stdout}")
        return {
            "status": "pass",
            "archive": str(zip_path),
            "marketplace": marketplace_name,
            "installed_plugin_root": str(installed_root),
            "smoke": smoke_report,
        }
    finally:
        run(["codex", "plugin", "remove", f"recall@{marketplace_name}"], check=False)
        run(["codex", "plugin", "marketplace", "remove", marketplace_name], check=False)
        shutil.rmtree(temp_root, ignore_errors=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test dist/recall.zip through a temporary Codex marketplace.")
    parser.add_argument("archive", nargs="?", default=str(ROOT / "dist" / "recall.zip"))
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        report = run_smoke(Path(args.archive).expanduser().resolve())
    except Exception as exc:
        report = {"status": "fail", "archive": args.archive, "error": str(exc)}
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(f"RECALL zip marketplace smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("RECALL zip marketplace smoke passed")
        print(f"Archive: {report['archive']}")
        print(f"Installed plugin root: {report['installed_plugin_root']}")


if __name__ == "__main__":
    main()
