"""Layer 2: agent-compliance evaluation.

The calling agent is the test subject. `setup` fabricates one sandbox project
per task and writes the agent-facing prompts; a human (or automation) runs
each prompt in a FRESH agent session whose working directory is that sandbox,
with the RECALL plugin installed normally. `grade` then scores each task from
artifacts only: store diff, debug traces, and store content. Task prompts
NEVER reveal what RECALL behavior is expected.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "plugins" / "recall" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from . import store_fabricator  # noqa: E402 - engine path inserted above


def _store_rows(root: Path) -> dict[int, dict[str, Any]]:
    db = root / ".recall" / "memory.sqlite"
    if not db.exists():
        return {}
    connection = sqlite3.connect(db)
    try:
        rows = connection.execute("SELECT id, category, content, metadata FROM memories").fetchall()
    finally:
        connection.close()
    return {row[0]: {"category": row[1], "content": row[2], "metadata": json.loads(row[3] or "{}")} for row in rows}


def _debug_events(root: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    debug_dir = root / ".recall" / "debug"
    if not debug_dir.exists():
        return events
    for path in sorted(debug_dir.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
    return events


def setup(tasks_path: Path, out_dir: Path, *, seed: int) -> dict[str, Any]:
    import config as recall_config

    tasks = json.loads(tasks_path.read_text(encoding="utf-8"))["tasks"]
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"seed": seed, "tasks": []}
    instructions = [
        "# RECALL agent-compliance run",
        "",
        "For EACH task below: open a FRESH agent session (any provider with the",
        "RECALL plugin installed), set its working directory to the task's",
        "workspace, paste the task prompt verbatim, and let the agent work with",
        "no extra guidance. Do not mention RECALL or memory unless the prompt",
        "does. When all tasks are done, run:",
        "",
        "    python bench/run_bench.py compliance-grade --workdir <this directory>",
        "",
    ]
    for task in tasks:
        workspace = out_dir / task["id"]
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "pyproject.toml").write_text("[project]\nname='compliance-fixture'\nversion='0.0.1'\n", encoding="utf-8")
        for rel_path, content in (task.get("files") or {}).items():
            target = workspace / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        store_manifest = store_fabricator.fabricate(
            workspace, tier=task.get("store_tier", "working"), seed=seed,
            golden=True, flagged=False, conflicts=False, bad_pack=False,
        )
        cfg = recall_config.load_config(workspace)
        cfg["observability_mode"] = "debug"
        recall_config.save_config(cfg, workspace)
        baseline_ids = sorted(_store_rows(workspace))
        manifest["tasks"].append({
            "id": task["id"],
            "workspace": str(workspace),
            "rubric": task["rubric"],
            "baseline_ids": baseline_ids,
            "golden": store_manifest["golden"],
        })
        instructions += [f"## Task {task['id']}", f"Workspace: `{workspace}`", "Prompt:", "", "```", task["prompt"], "```", ""]
    (out_dir / "compliance_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "INSTRUCTIONS.md").write_text("\n".join(instructions) + "\n", encoding="utf-8")
    return {"tasks": len(manifest["tasks"]), "instructions": str(out_dir / "INSTRUCTIONS.md")}


def grade(workdir: Path, tasks_path: Path) -> dict[str, Any]:
    manifest = json.loads((workdir / "compliance_manifest.json").read_text(encoding="utf-8"))
    task_definitions = {task["id"]: task for task in json.loads(tasks_path.read_text(encoding="utf-8"))["tasks"]}
    results: list[dict[str, Any]] = []
    for entry in manifest["tasks"]:
        definition = task_definitions[entry["id"]]
        rubric = definition["rubric"]
        workspace = Path(entry["workspace"])
        rows = _store_rows(workspace)
        new_rows = {record_id: row for record_id, row in rows.items() if record_id not in set(entry["baseline_ids"])}
        events = _debug_events(workspace)
        checks: dict[str, Any] = {}

        if "should_save" in rubric:
            saved = bool(new_rows)
            checks["saved"] = saved
            checks["save_expected"] = rubric["should_save"]
            checks["save_ok"] = saved == rubric["should_save"]
        if rubric.get("expected_category") and new_rows:
            categories = {row["category"] for row in new_rows.values()}
            checks["categories"] = sorted(categories)
            checks["category_ok"] = rubric["expected_category"] in categories
        if rubric.get("must_reject_secret"):
            leaked = any(rubric["secret_marker"] in row["content"] for row in rows.values())
            checks["secret_in_store"] = leaked
            checks["secret_ok"] = not leaked
        if rubric.get("should_update_not_duplicate"):
            target_id = next((golden["id"] for golden in entry["golden"] if golden["category"] == rubric.get("target_category")), None)
            signature = rubric.get("duplicate_signature")
            duplicated = bool(signature) and any(signature in row["content"] for row in new_rows.values())
            updated = target_id is not None and target_id in rows and (
                rows[target_id]["metadata"].get("edited_at")
                or rows[target_id]["metadata"].get("last_confirmed")
                or rows[target_id]["metadata"].get("superseded_by")
            )
            checks["updated_existing"] = bool(updated)
            checks["appended_duplicate"] = duplicated
            checks["update_ok"] = bool(updated) and not duplicated
        if "should_retrieve" in rubric:
            gate_events = [event for event in events if event.get("event") in {"retrieval_gate", "prompt_activation"}]
            checks["retrieval_evidence_events"] = len(gate_events)
            checks["retrieve_evidence"] = bool(gate_events)
            checks["retrieve_note"] = (
                "hook-path evidence only; direct MCP retrieval is not observable from artifacts"
            )

        ok_flags = [value for key, value in checks.items() if key.endswith("_ok")]
        results.append({
            "task": entry["id"],
            "checks": checks,
            "pass": all(ok_flags) if ok_flags else None,
        })
    graded = [result for result in results if result["pass"] is not None]
    return {
        "tasks": results,
        "graded": len(graded),
        "passed": sum(1 for result in graded if result["pass"]),
        "pass_rate": round(sum(1 for result in graded if result["pass"]) / len(graded), 4) if graded else None,
    }
