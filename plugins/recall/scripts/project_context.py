"""Resolve RECALL project roots without creating files."""

from __future__ import annotations

import subprocess
from pathlib import Path

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


def resolve_project_root(start: str | Path) -> Path | None:
    """Return an existing-memory, Git, or manifest root without mutating disk."""

    return existing_memory_root(start) or git_root(start) or manifest_root(start)
