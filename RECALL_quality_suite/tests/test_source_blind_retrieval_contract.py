from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from _harness import memory_cmd, plugin_root, run_json, skill_cmd, temp_project


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "source_blind_memory_cards.json"
MIXED_HISTORY_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "mixed_history_memory_cards.json"
GROUND_TRUTH_PATH = Path(__file__).resolve().parents[1] / "rubrics" / "source_blind_ground_truth.json"
RELEASE_SCORECARD_PATH = Path(__file__).resolve().parents[1] / "rubrics" / "release_scorecard.json"


def load_cards() -> list[dict[str, object]]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def seed_cards(project: Path) -> None:
    for card in load_cards():
        args = [
            "save-insight",
            card["category"],
            card["content"],
            "--summary",
            card["summary"],
            "--details",
            card["details"],
            "--source",
            str(card.get("source", "source-blind-fixture")),
            "--status",
            card["status"],
            "--importance",
            str(card["importance"]),
            "--confidence",
            str(card["confidence"]),
        ]
        for tag in card["tags"]:
            args.extend(["--tag", tag])
        run_json(skill_cmd(project, *args))


class SourceBlindRetrievalReadinessTests(unittest.TestCase):
    def test_release_scorecard_defines_required_machine_metrics(self) -> None:
        scorecard = json.loads(RELEASE_SCORECARD_PATH.read_text(encoding="utf-8"))
        required = {
            "factual_precision",
            "stale_current_accuracy",
            "contradiction_recall",
            "missing_information_honesty",
            "cross_agent_agreement",
            "signal_to_noise",
            "token_budget_violations",
            "concurrency_record_loss",
            "retrieval_p95_ms",
            "plugin_eval_standard_minimum",
        }
        self.assertTrue(required.issubset(scorecard["metrics"]))
        self.assertEqual(scorecard["metrics"]["stale_current_accuracy"]["minimum"], 1.0)
        self.assertEqual(scorecard["metrics"]["token_budget_violations"]["maximum"], 0)

    def test_mixed_history_fixture_covers_release_failure_modes(self) -> None:
        cards = json.loads(MIXED_HISTORY_PATH.read_text(encoding="utf-8"))
        scenarios = {str(card["scenario"]) for card in cards}
        self.assertTrue(
            {
                "duplicate",
                "correction",
                "contradiction",
                "superseded",
                "deleted_source",
                "renamed_source",
                "incomplete_knowledge",
            }.issubset(scenarios)
        )
        self.assertTrue(all("expected" in card for card in cards))

    def test_hidden_ground_truth_is_machine_readable_and_not_agent_facing(self) -> None:
        truth = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(truth["questions"]), 3)
        self.assertTrue(all(item["required_facts"] for item in truth["questions"]))

        script = Path(__file__).resolve().parents[1] / "scripts" / "source_blind_agent_gate.py"
        with tempfile.TemporaryDirectory(prefix="recall-source-blind-pack-") as tmp:
            out_dir = Path(tmp) / "pack"
            run_json([
                sys.executable,
                str(script),
                "--plugin-root",
                str(plugin_root()),
                "--out-dir",
                str(out_dir),
            ], cwd=plugin_root())
            self.assertFalse((out_dir / GROUND_TRUTH_PATH.name).exists())
            self.assertFalse((out_dir / RELEASE_SCORECARD_PATH.name).exists())

    def test_fixture_contains_verified_project_history_cards(self) -> None:
        cards = load_cards()
        project_history_cards = [
            card for card in cards
            if "project-history" in card.get("tags", [])
        ]
        self.assertTrue(project_history_cards, "Expected project-history-backed source-blind cards.")
        self.assertTrue(
            any(str(card.get("source", "")).startswith("plugins/recall/") for card in project_history_cards),
            "Expected project-history cards to preserve their repo doc source.",
        )

    def test_architecture_gate_query_surfaces_memory_layer_and_hooks(self) -> None:
        with temp_project() as project:
            seed_cards(project)
            result = run_json(skill_cmd(
                project,
                "retrieve-memory",
                "current architecture runtime components hooks storage codex_memory",
                "--summary",
                "--limit",
                "6",
            ))
            categories = {item["category"] for item in result["results"][:4]}
            summary = result["summary"].lower()
            self.assertIn("architecture", categories)
            self.assertTrue(".codex_memory" in summary or "codex_memory" in summary)
            self.assertIn("hooks", summary)

    def test_decision_history_gate_distinguishes_active_from_superseded(self) -> None:
        with temp_project() as project:
            seed_cards(project)
            active = run_json(skill_cmd(
                project,
                "retrieve-memory",
                "retrieval embeddings v1 network transformer default decision",
                "--status",
                "active",
                "--summary",
                "--limit",
                "5",
            ))
            superseded = run_json(skill_cmd(
                project,
                "retrieve-memory",
                "transformer retrieval default v1",
                "--status",
                "superseded",
                "--summary",
                "--limit",
                "5",
            ))

            self.assertTrue(any(item["category"] == "decisions" for item in active["results"]))
            self.assertNotIn("transformer-grade semantic retrieval should be the default", active["summary"])
            self.assertEqual(len(superseded["results"]), 1)
            self.assertIn("superseded", superseded["results"][0]["status"])

    def test_source_free_implementation_plan_query_surfaces_tasks_risks_and_commands(self) -> None:
        with temp_project() as project:
            seed_cards(project)
            result = run_json(skill_cmd(
                project,
                "retrieve-memory",
                "next high priority release implementation plan validation risks commands",
                "--summary",
                "--limit",
                "8",
            ))
            categories = {item["category"] for item in result["results"]}
            self.assertIn("tasks", categories)
            self.assertIn("risks", categories)
            self.assertIn("commands", categories)
            self.assertIn("release", result["summary"].lower())

    def test_project_history_query_surfaces_public_surface_and_install_truth(self) -> None:
        with temp_project() as project:
            seed_cards(project)
            result = run_json(skill_cmd(
                project,
                "retrieve-memory",
                "public adapter backend cli built zip install hook trust recall_skill",
                "--summary",
                "--limit",
                "8",
            ))
            contents = "\n".join(item["content"] for item in result["results"])
            self.assertIn("recall_skill.py", contents)
            self.assertTrue(
                "hook trust" in contents.lower() or "trust review" in contents.lower(),
                "Expected install truth about hook trust in source-blind memory.",
            )
            self.assertTrue(
                "built zip" in contents.lower() or "recall.zip" in contents.lower(),
                "Expected built-zip/install lifecycle evidence in source-blind memory.",
            )

    def test_missing_exact_source_details_should_not_be_present_in_fixture_memory(self) -> None:
        with temp_project() as project:
            seed_cards(project)
            result = run_json(skill_cmd(
                project,
                "retrieve-memory",
                "exact internal function implementation line numbers private algorithm",
                "--summary",
                "--limit",
                "5",
            ))
            summary = result.get("summary", "").lower()
            # The retrieval layer may return broad architecture cards, but the fixture memory must not contain fake exact code claims.
            forbidden = ["line 123", "exact function body", "private algorithm uses"]
            self.assertFalse(any(token in summary for token in forbidden))

    def test_source_blind_eval_pack_preserves_project_history_sources(self) -> None:
        script = Path(__file__).resolve().parents[1] / "scripts" / "source_blind_agent_gate.py"
        with tempfile.TemporaryDirectory(prefix="recall-source-blind-pack-") as tmp:
            out_dir = Path(tmp) / "pack"
            run_json([
                sys.executable,
                str(script),
                "--plugin-root",
                str(plugin_root()),
                "--out-dir",
                str(out_dir),
            ], cwd=plugin_root())
            result = run_json(memory_cmd(out_dir / "agent_workspace", "query", "recall_skill hook trust recall.zip", "--limit", "10"))
            sources = {str(item["metadata"].get("source", "")) for item in result["results"]}
            self.assertTrue(any(source.startswith("plugins/recall/") for source in sources))

    def test_source_blind_eval_pack_writes_hidden_fixture_inventory(self) -> None:
        script = Path(__file__).resolve().parents[1] / "scripts" / "source_blind_agent_gate.py"
        with tempfile.TemporaryDirectory(prefix="recall-source-blind-pack-") as tmp:
            out_dir = Path(tmp) / "pack"
            run_json([
                sys.executable,
                str(script),
                "--plugin-root",
                str(plugin_root()),
                "--out-dir",
                str(out_dir),
            ], cwd=plugin_root())
            inventory_path = out_dir / "fixture_inventory.json"
            self.assertTrue(inventory_path.exists(), "Expected hidden fixture inventory for evaluator provenance.")
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            self.assertGreater(inventory["counts"]["total_cards"], 0)
            self.assertGreater(inventory["counts"]["project_history_cards"], 0)
            self.assertTrue(any(entry["source"].startswith("plugins/recall/") for entry in inventory["cards"]))


if __name__ == "__main__":
    unittest.main()
