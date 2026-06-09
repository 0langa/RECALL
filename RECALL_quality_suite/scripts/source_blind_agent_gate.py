#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


QUESTIONS = """# Source-Blind RECALL Agent Questions

Give the tested agent access only to the generated `codex_memory` folder. Block source/repo access.

## 1. Current architecture and responsibility map

Based only on `codex_memory`, reconstruct the current architecture of the project. Include main components, responsibilities, interactions, owned data/artifacts, the memory workflow, boundaries, invariants, non-goals, and uncertainties.

## 2. Historical decisions, reversals, and regression risks

Using only `codex_memory`, identify the most important technical decisions so far. For each, explain decision, rationale, rejected alternatives, current/deprecated status, refinements, regression risks, and what future agents must not undo.

## 3. Source-free implementation planning

Based only on `codex_memory`, propose a concrete implementation plan for the next high-priority feature/fix. Include affected areas, expected behavior, dependencies, steps, risks, conventions, validation, avoid-list, and what cannot be known without source access.
"""


def build_inventory(cards: list[dict[str, object]]) -> dict[str, object]:
    normalized = []
    for card in cards:
        tags = [str(tag) for tag in card.get("tags", [])]
        normalized.append(
            {
                "category": str(card["category"]),
                "summary": str(card["summary"]),
                "status": str(card["status"]),
                "source": str(card.get("source", "source-blind-eval-pack")),
                "tags": tags,
            }
        )
    return {
        "counts": {
            "total_cards": len(normalized),
            "project_history_cards": sum(1 for card in normalized if "project-history" in card["tags"]),
            "synthetic_baseline_cards": sum(1 for card in normalized if "synthetic-baseline" in card["tags"]),
        },
        "cards": normalized,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a source-blind RECALL evaluation pack.")
    parser.add_argument("--plugin-root", required=True, help="Path to plugins/recall")
    parser.add_argument("--out-dir", default="source_blind_eval_pack")
    parser.add_argument("--fixture", default=str(Path(__file__).resolve().parents[1] / "fixtures" / "source_blind_memory_cards.json"))
    args = parser.parse_args()

    plugin_root = Path(args.plugin_root).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    project = out_dir / "agent_workspace"
    project.mkdir()

    cards = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    skill = plugin_root / "scripts" / "recall_skill.py"
    for card in cards:
        cmd = [
            sys.executable,
            str(skill),
            "--root",
            str(project),
            "save-insight",
            card["category"],
            card["content"],
            "--summary",
            card["summary"],
            "--details",
            card["details"],
            "--source",
            card.get("source", "source-blind-eval-pack"),
            "--status",
            card["status"],
            "--importance",
            str(card["importance"]),
            "--confidence",
            str(card["confidence"]),
        ]
        for tag in card["tags"]:
            cmd.extend(["--tag", tag])
        subprocess.run(cmd, check=True, cwd=plugin_root, capture_output=True, text=True)

    # Rename for the desired agent-facing folder name while preserving actual runtime layout.
    (out_dir / "codex_memory").mkdir()
    for item in (project / ".codex_memory").iterdir():
        target = out_dir / "codex_memory" / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)

    (out_dir / "agent_questions.md").write_text(QUESTIONS, encoding="utf-8")
    (out_dir / "evaluator_scorecard.md").write_text((Path(__file__).resolve().parents[1] / "rubrics" / "scoring_template.md").read_text(encoding="utf-8"), encoding="utf-8")
    (out_dir / "fixture_inventory.json").write_text(json.dumps(build_inventory(cards), indent=2), encoding="utf-8")
    (out_dir / "README.md").write_text(
        "Give the tested agent only `codex_memory/` and `agent_questions.md`. Keep source, repo, `evaluator_scorecard.md`, and `fixture_inventory.json` hidden.\n",
        encoding="utf-8",
    )

    print(json.dumps({"status": "pass", "out_dir": str(out_dir), "cards": len(cards)}, indent=2))


if __name__ == "__main__":
    main()
