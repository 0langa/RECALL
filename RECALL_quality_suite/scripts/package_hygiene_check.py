#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
from typing import Any


SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*['\"]?[^'\"\s]+"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
]

FORBIDDEN_PATH_PARTS = [
    ".codex_memory",
    "memory.sqlite",
    "vector_index.bin",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".git/",
    "dist/recall.zip",
]

REQUIRED_FILES = [
    ".codex-plugin/plugin.json",
    "README.md",
    "hooks/hooks.json",
    "scripts/recall_skill.py",
    "skills/save-insight/SKILL.md",
    "skills/retrieve-memory/SKILL.md",
    "skills/define-category/SKILL.md",
]


def inspect_zip(zip_path: Path) -> dict[str, Any]:
    failures: list[str] = []
    names: list[str] = []
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        normalized = [name.replace("\\", "/").lstrip("/") for name in names]

        for forbidden in FORBIDDEN_PATH_PARTS:
            hits = [name for name in normalized if forbidden in name]
            if hits:
                failures.append(f"forbidden path/content marker {forbidden!r}: {hits[:5]}")

        for required in REQUIRED_FILES:
            if not any(name.endswith(required) or name == required for name in normalized):
                failures.append(f"required plugin file missing from package: {required}")

        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            if info.is_dir():
                continue
            if info.file_size > 1_500_000:
                # Avoid reading huge binaries; RECALL package should be small.
                continue
            suffix = Path(name).suffix.lower()
            if suffix not in {".py", ".md", ".json", ".txt", ".toml", ".yml", ".yaml", ".ps1", ".sh"}:
                continue
            try:
                text = archive.read(info).decode("utf-8", errors="ignore")
            except Exception:
                continue
            for pattern in SECRET_PATTERNS:
                if pattern.search(text):
                    failures.append(f"secret-like string found in packaged text file: {name}")
                    break

    return {
        "status": "fail" if failures else "pass",
        "zip": str(zip_path),
        "file_count": len(names),
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Check RECALL release ZIP hygiene.")
    parser.add_argument("--plugin-root", default=".", help="Path to plugins/recall")
    parser.add_argument("--zip", dest="zip_path", help="Path to recall.zip. Defaults to <plugin-root>/dist/recall.zip")
    args = parser.parse_args()

    plugin_root = Path(args.plugin_root).expanduser().resolve()
    zip_path = Path(args.zip_path).expanduser().resolve() if args.zip_path else plugin_root / "dist" / "recall.zip"
    if not zip_path.exists():
        report = {"status": "skip", "reason": f"ZIP does not exist: {zip_path}", "zip": str(zip_path)}
        print(json.dumps(report, indent=2, sort_keys=True))
        return

    report = inspect_zip(zip_path)
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
