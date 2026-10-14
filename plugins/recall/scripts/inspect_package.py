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


FORBIDDEN_PARTS = {".git", ".recall", ".codex_memory", "__pycache__", "dist"}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo"}
WINDOWS_USER_MARKER = "C:" + "\\" + "Users" + "\\"
POSIX_USER_MARKER = "/" + "Users" + "/"
REQUIRED_PATHS = {
    ".mcp.json",
    ".codex-plugin/plugin.json",
    ".claude-plugin/plugin.json",
    "hooks/hooks.json",
    "kimi.plugin.json",
    "scripts/contract.py",
    "skills/save-insight/SKILL.md",
    "skills/retrieve-memory/SKILL.md",
    "skills/using-recall/SKILL.md",
    "skills/define-category/SKILL.md",
    "scripts/kimi_mcp_server.py",
    "scripts/hook_events.py",
    "scripts/recall_skill.py",
    "scripts/memory_manager.py",
}
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*['\"]?[^'\"\s]+"),
]
# Values that make the keyword=value pattern match source code (type
# annotations) rather than a real secret literal.
_NOT_A_SECRET_VALUE = {
    "str", "int", "float", "bool", "bytes", "list", "dict", "set", "tuple",
    "any", "none", "object", "optional", "callable",
}
# An unquoted right-hand side that is a Python name, attribute access, call or
# subscript (``marker.group(0)``, ``event.session_id``, ``raw[:8]``) is code.
_PYTHON_EXPRESSION = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?:\s*[(\[].*)?")


def _is_plausible_secret(match: "re.Match[str]", name: str = "") -> bool:
    """Filter keyword=value false positives out of the keyword pattern.

    Structural patterns (no capture group, e.g. the ``sk-`` key prefix) are
    trusted outright. For the keyword pattern, a quoted literal assigned to a
    secret-named key counts as a secret. In Python files an unquoted value that
    is an ordinary expression, or that sits on a full-line comment, does not:
    ``token = marker.group(0)`` and ``session_token = event.session_id`` are
    code. An unquoted non-expression such as ``token=dummy-secret-value`` still
    fails.
    """
    if match.lastindex is None:
        return True
    keyword = match.group(1)
    remainder = match.group(0)[match.end(1) - match.start(0):].lstrip(" \t:=")
    quoted = remainder[:1] in {"'", '"'}
    value = re.split(r"[,);\s]", remainder.strip("'\""), maxsplit=1)[0]
    if not value:
        return False
    if value.lower() in _NOT_A_SECRET_VALUE:
        return False
    if value.lower().startswith(keyword.lower()):
        return False
    if quoted or not name.lower().endswith(".py"):
        return True
    text = match.string
    line_start = text.rfind("\n", 0, match.start()) + 1
    if text[line_start:match.start()].lstrip().startswith("#"):
        return False
    return not _PYTHON_EXPRESSION.fullmatch(value)


def find_secret_lines(name: str, text: str, patterns: "list[re.Pattern[str]]") -> list[int]:
    """Return the 1-based line numbers of every plausible secret in ``text``."""
    lines: set[int] = set()
    for pattern in patterns:
        for match in pattern.finditer(text):
            if _is_plausible_secret(match, name):
                lines.add(text.count("\n", 0, match.start()) + 1)
    return sorted(lines)


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
            secret_lines = find_secret_lines(name, text, SECRET_PATTERNS)
            if secret_lines:
                errors.append(f"Secret-like string found in: {name} (line {', '.join(map(str, secret_lines))})")

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
            interface = payload.get("interface") if isinstance(payload.get("interface"), dict) else {}
            for field in ("composerIcon", "logo"):
                asset = str(interface.get(field) or "").lstrip("./")
                if asset and asset not in names:
                    errors.append(f"Manifest {field} points to missing package asset: {asset}")
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
