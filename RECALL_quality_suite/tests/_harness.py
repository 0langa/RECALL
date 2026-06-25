from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


def plugin_root() -> Path:
    env = os.environ.get("RECALL_PLUGIN_ROOT")
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env))
    cwd = Path.cwd()
    candidates.extend([
        cwd,
        cwd / "plugins" / "recall",
        cwd.parent / "plugins" / "recall",
        Path(__file__).resolve().parents[2] / "plugins" / "recall",
    ])
    for candidate in candidates:
        candidate = candidate.expanduser().resolve()
        if (candidate / "scripts" / "recall_skill.py").exists() and (candidate / ".codex-plugin" / "plugin.json").exists():
            return candidate
    raise RuntimeError(
        "Could not locate RECALL plugin root. Set RECALL_PLUGIN_ROOT or run from repo root/plugin root."
    )


@contextmanager
def temp_project() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="recall-quality-") as tmp:
        root = Path(tmp).resolve()
        yield root


def run_text(args: list[str], *, cwd: Path | None = None, input_payload: dict[str, Any] | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    text = json.dumps(input_payload) if input_payload is not None else None
    completed = subprocess.run(
        args,
        cwd=str(cwd or plugin_root()),
        input=text,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and completed.returncode != 0:
        raise AssertionError(
            f"Command failed with exit {completed.returncode}: {' '.join(args)}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return completed


def run_json(args: list[str], *, cwd: Path | None = None, input_payload: dict[str, Any] | None = None, check: bool = True) -> dict[str, Any]:
    completed = run_text(args, cwd=cwd, input_payload=input_payload, check=check)
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"Command did not emit valid JSON: {' '.join(args)}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        ) from exc


def skill_cmd(project: Path, *args: str) -> list[str]:
    root = plugin_root()
    return [sys.executable, str(root / "scripts" / "recall_skill.py"), "--root", str(project), *args]


def memory_cmd(project: Path, *args: str) -> list[str]:
    root = plugin_root()
    return [sys.executable, str(root / "scripts" / "memory_manager.py"), "--root", str(project), *args]


def hook_cmd(script_name: str) -> list[str]:
    root = plugin_root()
    return [sys.executable, str(root / "hooks" / "scripts" / script_name)]


def active_memory_dir(project: Path) -> Path:
    candidates = [project / ".recall", project / ".codex_memory"]
    return next((candidate.resolve() for candidate in candidates if candidate.exists()), candidates[0].resolve())


def assert_memory_inside_project(project: Path) -> None:
    memory = active_memory_dir(project)
    assert memory.exists(), "RECALL memory directory was not created"
    try:
        memory.relative_to(project.resolve())
    except ValueError as exc:
        raise AssertionError("RECALL memory escaped the project root") from exc
