#!/usr/bin/env python3
"""Inspect a RECALL package directory or zip before release."""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Iterable


FORBIDDEN_PARTS = {".git", ".codex_memory", "__pycache__", "dist"}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo"}
WINDOWS_USER_MARKER = "C:" + "\\" + "Users" + "\\"
POSIX_USER_MARKER = "/" + "Users" + "/"
REQUIRED_PATHS = {
    ".codex-plugin/plugin.json",
    "hooks/hooks.json",
    "skills/save_insight/SKILL.md",
    "skills/retrieve_memory/SKILL.md",
    "skills/define_category/SKILL.md",
    "scripts/recall_skill.py",
    "scripts/memory_manager.py",
}
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*['\"]?[^'\"\s]+"),
]


def normalize(path: str) -> str:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")


def iter_zip(path: Path) -> Iterable[tuple[str, bytes]]:
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.endswith("/"):
                yield normalize(name), b""
                continue
            yield normalize(name), archive.read(name)


def iter_dir(path: Path) -> Iterable[tuple[str, bytes]]:
    for item in path.rglob("*"):
        rel = normalize(str(item.relative_to(path)))
        if item.is_dir():
            yield rel + "/", b""
        else:
            yield rel, item.read_bytes()


def inspect_package(path: Path) -> dict[str, object]:
    if path.is_file() and path.suffix.lower() == ".zip":
        entries = list(iter_zip(path))
    elif path.is_dir():
        entries = list(iter_dir(path))
    else:
        raise ValueError(f"Package must be a directory or .zip archive: {path}")

    names = {name.rstrip("/") for name, _ in entries}
    errors: list[str] = []
    warnings: list[str] = []

    for required in sorted(REQUIRED_PATHS):
        if required not in names:
            errors.append(f"Missing required package path: {required}")

    for name, data in entries:
        parts = set(Path(name).parts)
        normalized_parts = set(normalize(part) for part in name.split("/"))
        if parts & FORBIDDEN_PARTS or normalized_parts & FORBIDDEN_PARTS:
            errors.append(f"Forbidden package path: {name}")
        if Path(name).suffix.lower() in FORBIDDEN_SUFFIXES:
            errors.append(f"Forbidden compiled Python file: {name}")
        text = ""
        if data and len(data) <= 1_000_000:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = ""
        if text:
            if WINDOWS_USER_MARKER in text or POSIX_USER_MARKER in text:
                errors.append(f"Personal absolute path found in: {name}")
            for pattern in SECRET_PATTERNS:
                if pattern.search(text):
                    errors.append(f"Secret-like string found in: {name}")
                    break

    manifest = ".codex-plugin/plugin.json"
    if manifest in names:
        manifest_data = next(data for name, data in entries if name.rstrip("/") == manifest)
        try:
            payload = json.loads(manifest_data.decode("utf-8"))
            if payload.get("name") != "recall":
                errors.append("Manifest name must be `recall`.")
            if "skills" not in payload:
                errors.append("Manifest must declare bundled skills.")
            if "hooks" in payload:
                errors.append("Manifest must not declare unsupported `hooks`; use hooks/hooks.json.")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"Manifest is not valid JSON: {exc}")

    return {
        "package": str(path),
        "entries": len(entries),
        "status": "fail" if errors else "pass",
        "errors": errors,
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a RECALL package directory or zip.")
    parser.add_argument("package")
    args = parser.parse_args()

    try:
        report = inspect_package(Path(args.package))
    except ValueError as exc:
        report = {"package": args.package, "status": "fail", "errors": [str(exc)], "warnings": []}
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] != "pass":
        sys.exit(1)


if __name__ == "__main__":
    main()
