#!/usr/bin/env python3
"""End-to-end smoke test for a RECALL plugin checkout or installed copy."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_RECORDS = [
    (
        "project_state",
        "RECALL smoke project is verifying startup recall across a project boundary.",
        {"tags": ["smoke", "startup"], "source": "smoke_recall"},
    ),
    (
        "requirements",
        "RECALL must keep all runtime memory inside the active project .codex_memory directory.",
        {"tags": ["smoke", "local-first"], "source": "smoke_recall"},
    ),
    (
        "commands",
        "Verified smoke command: python scripts/smoke_recall.py --json",
        {"tags": ["smoke", "command"], "source": "smoke_recall"},
    ),
    (
        "risks",
        "Hook payload drift can break live Codex recall even when unit tests pass.",
        {"tags": ["smoke", "hooks"], "source": "smoke_recall"},
    ),
]


class SmokeFailure(RuntimeError):
    pass


def run_command(
    args: list[str],
    *,
    cwd: Path,
    input_text: str | None = None,
) -> tuple[int, str, str]:
    completed = subprocess.run(
        args,
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def run_json(args: list[str], *, cwd: Path, input_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    input_text = json.dumps(input_payload) if input_payload is not None else None
    code, stdout, stderr = run_command(args, cwd=cwd, input_text=input_text)
    if code != 0:
        raise SmokeFailure(f"Command failed ({code}): {' '.join(args)}\nSTDERR: {stderr}")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise SmokeFailure(f"Command did not return JSON: {' '.join(args)}\nSTDOUT: {stdout}") from exc


def plugin_root_from_args(raw_root: str | None) -> Path:
    if raw_root:
        return Path(raw_root).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def prepare_project(raw_project_root: str | None) -> tuple[Path, bool]:
    if raw_project_root:
        project_root = Path(raw_project_root).expanduser().resolve()
        project_root.mkdir(parents=True, exist_ok=True)
        return project_root, False
    return Path(tempfile.mkdtemp(prefix="recall-smoke-")).resolve(), True


def memory_command(plugin_root: Path, project_root: Path, *args: str) -> list[str]:
    return [
        sys.executable,
        str(plugin_root / "scripts" / "memory_manager.py"),
        "--root",
        str(project_root),
        *args,
    ]


def skill_command(plugin_root: Path, project_root: Path, *args: str) -> list[str]:
    return [
        sys.executable,
        str(plugin_root / "scripts" / "recall_skill.py"),
        "--root",
        str(project_root),
        *args,
    ]


def hook_command(plugin_root: Path, hook_name: str) -> list[str]:
    return [sys.executable, str(plugin_root / "hooks" / "scripts" / hook_name)]


def assert_plugin_shape(plugin_root: Path) -> None:
    required_paths = [
        plugin_root / ".codex-plugin" / "plugin.json",
        plugin_root / "hooks" / "hooks.json",
        plugin_root / "hooks" / "scripts" / "session_start.py",
        plugin_root / "scripts" / "recall_skill.py",
        plugin_root / "scripts" / "memory_manager.py",
        plugin_root / "skills" / "save-insight" / "SKILL.md",
        plugin_root / "skills" / "retrieve-memory" / "SKILL.md",
    ]
    missing = [str(path) for path in required_paths if not path.exists()]
    require(not missing, f"Plugin root is missing required files: {missing}")


def run_smoke(plugin_root: Path, project_root: Path) -> dict[str, Any]:
    assert_plugin_shape(plugin_root)
    checks: list[str] = []

    gitignore = project_root / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(".codex_memory/\n", encoding="utf-8")
    elif ".codex_memory/" not in gitignore.read_text(encoding="utf-8"):
        gitignore.write_text(gitignore.read_text(encoding="utf-8").rstrip() + "\n.codex_memory/\n", encoding="utf-8")
    checks.append("project gitignore covers .codex_memory")

    init_output = run_command(memory_command(plugin_root, project_root, "init"), cwd=plugin_root)
    require(init_output[0] == 0, f"init failed: {init_output[2]}")
    memory_dir = project_root / ".codex_memory"
    require(memory_dir.exists(), ".codex_memory was not created in the project root")
    require(memory_dir.resolve().is_relative_to(project_root.resolve()), ".codex_memory escaped project root")
    checks.append("memory initialized inside project root")

    for category, content, metadata in DEFAULT_RECORDS:
        payload = run_json(
            memory_command(plugin_root, project_root, "add", category, content, "--metadata", json.dumps(metadata)),
            cwd=plugin_root,
        )
        require(payload["category"] == category, f"saved category mismatch for {category}")
    checks.append("seed records saved")

    query = run_json(
        memory_command(plugin_root, project_root, "query", "startup recall local-first hooks", "--summary"),
        cwd=plugin_root,
    )
    require(len(query["results"]) >= 3, "query did not return enough smoke records")
    require("summary" in query and "RECALL" in query["summary"], "query summary did not contain expected context")
    checks.append("manual retrieval returns summarized context")

    skill_save = run_json(
        skill_command(
            plugin_root,
            project_root,
            "save-insight",
            "requirements",
            "Skill adapter smoke path must work from the installed plugin bundle.",
            "--summary",
            "Skill adapter smoke path works.",
            "--details",
            "The smoke harness verifies recall_skill.py against the same plugin root used by hooks.",
            "--tag",
            "skill-adapter",
            "--source",
            "skill",
            "--status",
            "active",
        ),
        cwd=plugin_root,
    )
    require(skill_save["category"] == "requirements", "skill adapter save used the wrong category")
    skill_query = run_json(
        skill_command(plugin_root, project_root, "retrieve-memory", "skill adapter smoke path", "--summary"),
        cwd=plugin_root,
    )
    require("Skill adapter smoke path" in skill_query.get("summary", ""), "skill adapter retrieval failed")
    checks.append("skill adapter save and retrieval pass")

    review = run_json(
        skill_command(plugin_root, project_root, "review-memory", "--category", "requirements", "--limit", "5"),
        cwd=plugin_root,
    )
    require(review["review"]["shown"] >= 1, "review-memory did not show seeded requirements")
    confirmed = run_json(
        skill_command(plugin_root, project_root, "confirm-memory", str(skill_save["id"]), "--source-session", "smoke"),
        cwd=plugin_root,
    )
    require(confirmed["metadata"].get("source_session") == "smoke", "confirm-memory did not mark source_session")
    resolved = run_json(
        skill_command(plugin_root, project_root, "resolve-memory", str(skill_save["id"]), "--note", "smoke lifecycle check"),
        cwd=plugin_root,
    )
    require(resolved["metadata"].get("status") == "resolved", "resolve-memory did not resolve the memory")
    checks.append("review and lifecycle adapter actions pass")

    rebuild = run_json(memory_command(plugin_root, project_root, "rebuild-index"), cwd=plugin_root)
    require(rebuild["indexed_records"] >= 4, "rebuild-index did not index seeded records")
    doctor = run_json(memory_command(plugin_root, project_root, "doctor"), cwd=plugin_root)
    require(doctor["index_complete"] is True, "doctor reports incomplete index")
    require(doctor["records"] >= 4, "doctor reports missing records")
    checks.append("index rebuild and doctor pass")

    prompt_hook = run_json(
        hook_command(plugin_root, "prompt_inspector.py"),
        cwd=plugin_root,
        input_payload={
            "cwd": str(project_root),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "remember this: RECALL smoke prefers structured memory cards.",
        },
    )
    require(prompt_hook["continue"] is True, "UserPromptSubmit hook did not continue")
    checks.append("UserPromptSubmit saves explicit memory cue")

    tool_hook = run_json(
        hook_command(plugin_root, "post_tool_use.py"),
        cwd=plugin_root,
        input_payload={
            "cwd": str(project_root),
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "python scripts/smoke_recall.py --json"},
            "tool_response": {"exit_code": 0, "stdout": "Ran RECALL smoke harness successfully\nOK", "stderr": ""},
        },
    )
    require(tool_hook["continue"] is True, "PostToolUse hook did not continue")
    checks.append("PostToolUse captures compact command memory")

    pre_compact = run_json(
        hook_command(plugin_root, "pre_compact.py"),
        cwd=plugin_root,
        input_payload={
            "cwd": str(project_root),
            "hook_event_name": "PreCompact",
            "trigger": "manual",
            "transcript": "RECALL smoke compaction should preserve project state, requirements, and risks.",
        },
    )
    require(pre_compact["continue"] is True, "PreCompact hook did not continue")
    checks.append("PreCompact hook exits cleanly")

    stop = run_json(
        hook_command(plugin_root, "stop.py"),
        cwd=plugin_root,
        input_payload={
            "cwd": str(project_root),
            "hook_event_name": "Stop",
            "last_assistant_message": "RECALL smoke stop checkpoint should be available next session.",
        },
    )
    require(stop["continue"] is True, "Stop hook did not continue")
    checks.append("Stop hook exits cleanly")

    session_start = run_json(
        hook_command(plugin_root, "session_start.py"),
        cwd=plugin_root,
        input_payload={"cwd": str(project_root), "hook_event_name": "SessionStart", "source": "startup"},
    )
    require(session_start["continue"] is True, "SessionStart hook did not continue")
    context = session_start.get("hookSpecificOutput", {}).get("additionalContext", "")
    require("RECALL project memory" in context and "smoke" in context.lower(), "SessionStart did not inject smoke context")
    checks.append("SessionStart injects recalled project context")

    final_doctor = run_json(memory_command(plugin_root, project_root, "doctor"), cwd=plugin_root)
    require(final_doctor["index_complete"] is True, "final doctor reports incomplete index")
    checks.append("final backend health is clean")

    return {
        "status": "pass",
        "plugin_root": str(plugin_root),
        "project_root": str(project_root),
        "checks": checks,
        "records": final_doctor["records"],
        "index_records": final_doctor["index_records"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an end-to-end RECALL smoke test.")
    parser.add_argument("--installed-plugin-root", help="Plugin root to test. Defaults to this checkout.")
    parser.add_argument("--project-root", help="Project root to use. Defaults to a temporary project.")
    parser.add_argument("--keep", action="store_true", help="Keep the generated temporary project.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    plugin_root = plugin_root_from_args(args.installed_plugin_root)
    project_root, should_cleanup = prepare_project(args.project_root)
    try:
        result = run_smoke(plugin_root, project_root)
    except Exception as exc:
        result = {
            "status": "fail",
            "plugin_root": str(plugin_root),
            "project_root": str(project_root),
            "error": str(exc),
        }
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"RECALL smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
    finally:
        if should_cleanup and not args.keep:
            shutil.rmtree(project_root, ignore_errors=True)

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("RECALL smoke passed")
        for check in result["checks"]:
            print(f"- {check}")
        if should_cleanup and not args.keep:
            print("Temporary project cleaned up.")
        else:
            print(f"Project root: {project_root}")


if __name__ == "__main__":
    main()
