from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "scripts" / "recall_skill.py"


def run_skill(root: str, *args: str) -> dict:
    completed = subprocess.run(
        [sys.executable, str(ADAPTER), "--root", root, *args],
        text=True,
        capture_output=True,
        check=True,
        cwd=ROOT,
    )
    return json.loads(completed.stdout)


class RecallSkillAdapterTests(unittest.TestCase):
    def test_save_retrieve_and_define_use_public_skill_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            category = run_skill(
                tmp,
                "define-category",
                "api_contracts",
                "--description",
                "Stable API shapes and compatibility promises.",
                "--weight",
                "1.4",
            )
            self.assertEqual(category["action"], "define-category")
            self.assertEqual(category["details"]["weight"], 1.4)

            saved = run_skill(
                tmp,
                "save-insight",
                "api_contracts",
                "Callbacks must keep their webhook payload shape stable.",
                "--summary",
                "Webhook payload shape is stable.",
                "--details",
                "Consumers depend on callback field names staying compatible.",
                "--tag",
                "webhooks",
                "--source",
                "skill",
                "--status",
                "active",
                "--importance",
                "0.8",
                "--confidence",
                "0.9",
            )
            self.assertEqual(saved["action"], "save-insight")
            self.assertEqual(saved["category"], "api_contracts")

            result = run_skill(
                tmp,
                "retrieve-memory",
                "stable webhook payload",
                "--category",
                "api_contracts",
                "--summary",
            )
            self.assertIn("webhook payload shape", result["summary"])
            self.assertEqual(result["results"][0]["metadata"]["source"], "skill")

    def test_support_actions_return_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_skill(
                tmp,
                "define-category",
                "api_contracts",
                "--description",
                "Stable API shapes and compatibility promises.",
                "--weight",
                "1.4",
            )
            categories = run_skill(tmp, "list-categories")
            category_names = [item["name"] for item in categories["categories"]]
            doctor = run_skill(tmp, "doctor")

            self.assertEqual(categories["action"], "list-categories")
            self.assertIn("requirements", category_names)
            self.assertIn("api_contracts", category_names)
            self.assertEqual(doctor["action"], "doctor")
            self.assertTrue(doctor["report"]["index_complete"])

    def test_repair_restores_broken_index_through_public_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_skill(
                tmp,
                "save-insight",
                "requirements",
                "Repair must rebuild a broken index.",
                "--summary",
                "Repair rebuilds indexes.",
                "--status",
                "active",
            )
            index_path = Path(tmp) / ".codex_memory" / "vector_index.bin"
            index_path.write_text("", encoding="utf-8")

            repair = run_skill(tmp, "repair")

            self.assertEqual(repair["action"], "repair")
            self.assertTrue(repair["report"]["doctor"]["index_complete"])

    def test_review_and_lifecycle_actions_use_public_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = run_skill(
                tmp,
                "save-insight",
                "decisions",
                "Use raw transcript memories.",
                "--summary",
                "Raw transcript memories.",
                "--status",
                "active",
            )
            new = run_skill(
                tmp,
                "save-insight",
                "decisions",
                "Use structured memory cards.",
                "--summary",
                "Structured memory cards.",
                "--status",
                "active",
            )
            supersede = run_skill(tmp, "supersede-memory", str(old["id"]), str(new["id"]), "--note", "Corrected.")
            confirm = run_skill(tmp, "confirm-memory", str(new["id"]), "--source-session", "session-1")
            review = run_skill(tmp, "review-memory", "--category", "decisions", "--limit", "5")
            prune = run_skill(tmp, "prune-memory", str(old["id"]), "--note", "Reviewed as obsolete.")

            self.assertEqual(supersede["old"]["metadata"]["status"], "superseded")
            self.assertIn(old["id"], supersede["new"]["metadata"]["supersedes"])
            self.assertEqual(confirm["metadata"]["source_session"], "session-1")
            self.assertEqual(review["review"]["category_counts"]["decisions"], 2)
            self.assertEqual(prune["metadata"]["status"], "archived")


if __name__ == "__main__":
    unittest.main()
