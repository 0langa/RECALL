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


def run_skill_with_input(
    root: str,
    input_text: str,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ADAPTER), "--root", root, *args],
        input=input_text,
        text=True,
        capture_output=True,
        check=check,
        cwd=ROOT,
    )


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

    def test_edit_and_delete_memory_use_public_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            saved = run_skill(
                tmp,
                "save-insight",
                "requirements",
                "Recall should keep raw transcript logs forever.",
                "--summary",
                "Raw logs are required.",
                "--status",
                "active",
            )

            edited = run_skill(
                tmp,
                "edit-memory",
                str(saved["id"]),
                "--category",
                "decisions",
                "--content",
                "RECALL should prefer structured memory cards over raw transcript logs.",
                "--summary",
                "Structured cards are preferred.",
                "--tag",
                "memory-quality",
            )
            old_query = run_skill(tmp, "retrieve-memory", "raw transcript logs forever", "--category", "requirements")
            new_query = run_skill(tmp, "retrieve-memory", "structured memory cards", "--category", "decisions")

            self.assertEqual(edited["action"], "edit-memory")
            self.assertEqual(edited["category"], "decisions")
            self.assertIn("edited_at", edited["metadata"])
            self.assertEqual(old_query["results"], [])
            self.assertEqual(new_query["results"][0]["id"], saved["id"])

            rejected = run_skill_with_input(
                tmp,
                "",
                "delete-memory",
                str(saved["id"]),
                "--confirm",
                "DELETE",
                check=False,
            )
            self.assertNotEqual(rejected.returncode, 0)

            deleted = run_skill(tmp, "delete-memory", str(saved["id"]), "--confirm", f"DELETE-{saved['id']}")
            after_delete = run_skill(tmp, "retrieve-memory", "structured memory cards", "--category", "decisions")

            self.assertEqual(deleted["action"], "delete-memory")
            self.assertEqual(deleted["id"], saved["id"])
            self.assertEqual(after_delete["results"], [])

    def test_save_turn_card_validates_and_stores_finalizer_card(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            card_path = Path(tmp) / "turn-card.json"
            card_path.write_text(
                json.dumps(
                    {
                        "category": "decisions",
                        "content": "Use Stop finalizer continuation for RECALL turn memory.",
                        "summary": "Stop finalizer continuation is the memory write boundary.",
                        "details": "PostToolUse buffers evidence; Stop creates one finalizer request.",
                        "tags": ["finalizer", "hooks"],
                        "source": "finalizer",
                        "status": "active",
                        "importance": 0.9,
                        "confidence": 0.85,
                        "capture_reason": "durable_project_state",
                        "session_id": "session-1",
                        "turn_id": "turn-1",
                        "evidence_ids": ["event-1"],
                    }
                ),
                encoding="utf-8",
            )

            saved = run_skill(tmp, "save-turn-card", "--file", str(card_path))
            result = run_skill(tmp, "retrieve-memory", "Stop finalizer continuation", "--category", "decisions")

            self.assertEqual(saved["action"], "save-turn-card")
            self.assertEqual(saved["result"], "saved")
            self.assertEqual(saved["category"], "decisions")
            metadata = result["results"][0]["metadata"]
            self.assertEqual(metadata["source"], "finalizer")
            self.assertEqual(metadata["schema"], "recall.turn_card.v1")
            self.assertEqual(metadata["turn_id"], "turn-1")
            self.assertIn("finalizer", metadata["tags"])

    def test_save_turn_card_accepts_stdin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            card = {
                "category": "requirements",
                "content": "Finalizer cards must be schema validated.",
                "summary": "Finalizer cards are validated.",
                "tags": ["finalizer"],
            }
            completed = run_skill_with_input(tmp, json.dumps(card), "save-turn-card", "--stdin")
            saved = json.loads(completed.stdout)

            self.assertEqual(saved["action"], "save-turn-card")
            self.assertEqual(saved["result"], "saved")

    def test_save_turn_card_rejects_secret_like_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            card = {
                "category": "risks",
                "content": "Do not store token=dummy-secret-value in memory.",
                "summary": "Secret-like content rejected.",
            }
            completed = run_skill_with_input(tmp, json.dumps(card), "save-turn-card", "--stdin", check=False)
            result = run_skill(tmp, "retrieve-memory", "dummy-secret-value", "--category", "risks")

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("secret-like", completed.stderr)
            self.assertEqual(result["results"], [])


if __name__ == "__main__":
    unittest.main()
