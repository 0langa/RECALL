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
# Keep this filter identical to plugins/recall/scripts/inspect_package.py;
# test_package_hygiene_contract.py checks that the two agree.
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
    is an ordinary expression (a name, attribute access, call or subscript), or
    that sits on a full-line comment, is code and does not count. An unquoted
    value that is not an expression, such as a dash-joined word, still fails.
    """
    if match.lastindex is None:
        return True
    keyword = match.group(1)
    remainder = match.group(0)[match.end(1) - match.start(0):].lstrip(" \t:=")
    quoted = remainder[:1] in {"'", '"'}
    value = re.split(r"[,);\s]", remainder.strip("'\""), maxsplit=1)[0].strip("`")
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

FORBIDDEN_PATH_PARTS = [
    ".recall",
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
    ".mcp.json",
    ".codex-plugin/plugin.json",
    "kimi.plugin.json",
    "README.md",
    "hooks/hooks.json",
    "scripts/recall_skill.py",
    "scripts/kimi_mcp_server.py",
    "scripts/hook_events.py",
    "skills/save-insight/SKILL.md",
    "skills/retrieve-memory/SKILL.md",
    "skills/define-category/SKILL.md",
    "skills/using-recall/SKILL.md",
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
            secret_lines = find_secret_lines(name, text, SECRET_PATTERNS)
            if secret_lines:
                failures.append(
                    f"secret-like string found in packaged text file: {name} (line {', '.join(map(str, secret_lines))})"
                )

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
