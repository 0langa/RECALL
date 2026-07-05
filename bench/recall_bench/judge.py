"""Optional LLM judging — two-phase, never executes a model itself.

Phase A (`emit`): sample artifacts from a recorded run journal into
judge_tasks.jsonl with fixed rubrics. Phase B is performed by ANY agent (the
cheaper the better): it reads the tasks, writes judge_scores.jsonl. Phase C
(`aggregate`): validate scores and fold them into the report.

The harness makes zero API calls; the calling agent is the model.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any


RUBRICS = {
    "card_quality": (
        "Score 1-5 how good this memory card is as durable project memory. "
        "5 = specific, actionable, verifiable, future-useful. 1 = vague, transient, or restating obvious/documented facts. "
        "Also answer contains_noise (true/false): raw logs, filler, or chat fragments present."
    ),
    "injection_usefulness": (
        "Given the user prompt and the memory context RECALL injected, score 1-5 how useful the injected context is "
        "for that prompt. 5 = directly needed facts. 1 = irrelevant noise that wastes context tokens. "
        "Also answer would_mislead (true/false): could this context push the agent toward a wrong action?"
    ),
    "summary_faithfulness": (
        "Score 1-5 whether this stored summary faithfully represents its full content without inventing or losing "
        "critical facts. 5 = faithful and complete. 1 = misleading."
    ),
}

SCORE_SCHEMA_HINT = {
    "task_id": "<copy from task>",
    "score": "<integer 1-5>",
    "flags": {"contains_noise": "<bool, only for card_quality>", "would_mislead": "<bool, only for injection_usefulness>"},
    "justification": "<one sentence>",
}


def emit_tasks(journal: list[dict[str, Any]], out_path: Path, *, seed: int, max_per_rubric: int = 10) -> dict[str, int]:
    rng = random.Random(seed)
    tasks: list[dict[str, Any]] = []

    injections = [entry for entry in journal if entry.get("kind") == "emission" and entry["channel"] == "prompt_injection"]
    for entry in rng.sample(injections, min(max_per_rubric, len(injections))):
        tasks.append({
            "task_id": f"inject-{entry['scenario']}-{entry['session']}-{entry['turn']}",
            "rubric": "injection_usefulness",
            "instructions": RUBRICS["injection_usefulness"],
            "artifact": {"injected_context": entry["text"]},
        })

    saves = [
        entry for entry in journal
        if entry.get("kind") == "emission" and entry["channel"] == "tool_result_save" and '"result": "saved"' in entry["text"]
    ]
    for index, entry in enumerate(rng.sample(saves, min(max_per_rubric, len(saves)))):
        tasks.append({
            "task_id": f"card-{index}",
            "rubric": "card_quality",
            "instructions": RUBRICS["card_quality"],
            "artifact": {"save_result": entry["text"]},
        })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"kind": "judge_header", "score_schema": SCORE_SCHEMA_HINT, "task_count": len(tasks)}) + "\n")
        for task in tasks:
            handle.write(json.dumps(task, sort_keys=True) + "\n")
    return {"tasks_emitted": len(tasks)}


def aggregate(tasks_path: Path, scores_path: Path) -> dict[str, Any]:
    tasks = {
        entry["task_id"]: entry
        for entry in (json.loads(line) for line in tasks_path.read_text(encoding="utf-8").splitlines() if line.strip())
        if entry.get("task_id")
    }
    scores: dict[str, list[int]] = {}
    flags: dict[str, int] = {"contains_noise": 0, "would_mislead": 0}
    invalid: list[str] = []
    seen = 0
    for line in scores_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        task = tasks.get(str(entry.get("task_id")))
        score = entry.get("score")
        if task is None or not isinstance(score, int) or not 1 <= score <= 5:
            invalid.append(str(entry.get("task_id")))
            continue
        seen += 1
        scores.setdefault(task["rubric"], []).append(score)
        for flag_name in flags:
            if (entry.get("flags") or {}).get(flag_name) is True:
                flags[flag_name] += 1
    summary = {
        "scored": seen,
        "of_tasks": len(tasks),
        "invalid": invalid,
        "mean_by_rubric": {rubric: round(sum(values) / len(values), 2) for rubric, values in scores.items()},
        "flag_counts": flags,
    }
    return summary
