"""Resolve RECALL project roots without creating files."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import config as recall_config


MANIFEST_NAMES = {
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "package.json",
    "pnpm-workspace.yaml",
    "yarn.lock",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
    "Directory.Build.props",
    "global.json",
    "CMakeLists.txt",
    "Makefile",
}
MANIFEST_GLOBS = ("*.sln", "*.csproj", "*.fsproj", "*.vbproj")


def ancestors(start: str | Path) -> list[Path]:
    path = Path(start).expanduser().resolve()
    if path.is_file():
        path = path.parent
    return [path, *path.parents]


def existing_memory_root(start: str | Path) -> Path | None:
    home = Path.home().resolve()
    for candidate in ancestors(start):
        if candidate == home or candidate.parent == candidate:
            continue
        if (candidate / recall_config.MEMORY_DIR_NAME).is_dir() or (candidate / recall_config.LEGACY_MEMORY_DIR_NAME).is_dir():
            return candidate
    return None


def git_root(start: str | Path) -> Path | None:
    cwd = Path(start).expanduser().resolve()
    if cwd.is_file():
        cwd = cwd.parent
    try:
        completed = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    resolved = Path(completed.stdout.strip()).resolve()
    if resolved == Path.home().resolve() or resolved.parent == resolved:
        return None
    return resolved


def has_project_manifest(path: Path) -> bool:
    if any((path / name).is_file() for name in MANIFEST_NAMES):
        return True
    return any(any(path.glob(pattern)) for pattern in MANIFEST_GLOBS)


def manifest_root(start: str | Path) -> Path | None:
    home = Path.home().resolve()
    for candidate in ancestors(start):
        if candidate == home or candidate.parent == candidate:
            continue
        if has_project_manifest(candidate):
            return candidate
    return None


def project_root_decision(start: str | Path) -> dict[str, Any]:
    """Stop at the nearest project boundary, before an ancestor memory store.

    Git worktrees use a .git file; checking the marker handles both forms
    without a subprocess or canonical-store read. A nested manifest defines
    a child scope even if the parent already has RECALL enabled.
    """
    if not str(start).strip():
        return {"status": "unresolved", "root": None, "reason": "blank_root", "candidates": []}
    home = Path.home().resolve()
    for candidate in ancestors(start):
        if candidate == home or candidate.parent == candidate:
            break
        markers = []
        if (candidate / ".git").exists():
            markers.append("git")
        if has_project_manifest(candidate):
            markers.append("manifest")
        if (candidate / recall_config.MEMORY_DIR_NAME).is_dir() or (candidate / recall_config.LEGACY_MEMORY_DIR_NAME).is_dir():
            markers.append("existing_memory")
        if markers:
            return {
                "status": "resolved", "root": str(candidate), "reason": "nearest_project_boundary",
                "candidates": [{"root": str(candidate), "source": marker} for marker in markers],
            }
    return {"status": "unresolved", "root": None, "reason": "no_project_boundary", "candidates": []}


def resolve_project_root(start: str | Path) -> Path | None:
    """Return the nearest clear project boundary without mutating disk."""
    decision = project_root_decision(start)
    return Path(decision["root"]) if decision["status"] == "resolved" else None
