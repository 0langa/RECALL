from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "scripts" / "recall_skill.py"
sys.path.insert(0, str(ROOT / "scripts"))

import config as recall_config  # noqa: E402


def run_skill(root: str, *args: str) -> dict:
    completed = subprocess.run(
        [sys.executable, str(ADAPTER), "--root", root, *args],
        text=True,
        capture_output=True,
        check=True,
        cwd=ROOT,
    )
    return json.loads(completed.stdout)


MANAGER = ROOT / "scripts" / "memory_manager.py"


def run_manager(root: str, *args: str) -> dict:
    completed = subprocess.run(
        [sys.executable, str(MANAGER), "--root", root, *args],
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
            self.assertEqual(result["results"][0]["source"], "skill")

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
            index_path = recall_config.memory_dir(tmp) / "vector_index.bin"
            index_path.write_text("", encoding="utf-8")

            repair = run_skill(tmp, "repair")

            self.assertEqual(repair["action"], "repair")
            self.assertTrue(repair["report"]["doctor"]["index_complete"])

    def test_save_insight_accepts_provider_provenance_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            saved = run_skill(
                tmp,
                "save-insight",
                "decisions",
                "Kimi and Codex share provider-neutral RECALL memory.",
                "--summary",
                "Shared provider-neutral memory.",
                "--origin-provider",
                "kimi",
                "--origin-agent",
                "kimi-code",
                "--source-session",
                "session-42",
                "--source-turn",
                "turn-7",
                "--capture-channel",
                "mcp",
                "--applies-to-provider",
                "all",
            )
            retrieved = run_skill(tmp, "retrieve-memory", "provider-neutral memory", "--category", "decisions", "--verbose")
            metadata = retrieved["results"][0]["metadata"]

            compact = run_skill(tmp, "retrieve-memory", "provider-neutral memory", "--category", "decisions")
            self.assertNotIn("metadata", compact["results"][0])
            self.assertIn("flag", compact["results"][0])

            self.assertEqual(saved["category"], "decisions")
            self.assertEqual(metadata["origin_provider"], "kimi")
            self.assertEqual(metadata["origin_agent"], "kimi-code")
            self.assertEqual(metadata["source_session"], "session-42")
            self.assertEqual(metadata["source_turn"], "turn-7")
            self.assertEqual(metadata["capture_channel"], "mcp")
            self.assertEqual(metadata["applies_to_provider"], "all")

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
            self.assertIn("quality", review["review"])
            self.assertEqual(prune["metadata"]["status"], "archived")

    def test_archive_noise_is_dry_run_until_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Seed via the trusted manager path: skill saves declaring hook
            # sources are gated by the auto-capture policy by design.
            noisy = run_manager(
                tmp,
                "add",
                "commands",
                "Tool: Bash Command: git status --short Result: completed",
                "--summary",
                "Bash result captured.",
                "--source",
                "post_tool_use",
                "--status",
                "active",
            )

            dry_run = run_skill(tmp, "archive-noise")
            still_active = run_skill(tmp, "review-memory", "--category", "commands", "--status", "active")
            applied = run_skill(tmp, "archive-noise", "--apply")
            archived = run_skill(tmp, "review-memory", "--category", "commands", "--status", "archived")

            self.assertEqual(dry_run["mode"], "dry-run")
            self.assertEqual(dry_run["matched"], 1)
            self.assertEqual(still_active["review"]["memories"][0]["id"], noisy["id"])
            self.assertEqual(applied["mode"], "apply")
            self.assertEqual(applied["archived"], 1)
            self.assertEqual(archived["review"]["memories"][0]["id"], noisy["id"])

    def test_memory_hygiene_commands_return_stable_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = run_skill(
                tmp,
                "save-insight",
                "requirements",
                "Release checks must pass before tagging.",
                "--summary",
                "Release checks gate tags.",
                "--status",
                "active",
            )
            # Duplicate-shaped skill saves are deduplicated at write time now:
            # the existing card is confirmed instead of appended.
            duplicate_save = run_skill(
                tmp,
                "save-insight",
                "requirements",
                "Release checks must pass before tagging.",
                "--summary",
                "Release checks gate tags.",
                "--status",
                "active",
            )
            self.assertEqual(duplicate_save["result"], "updated_existing")
            self.assertEqual(duplicate_save["id"], first["id"])

            # Pre-existing duplicates (e.g. legacy stores) still surface as
            # merge proposals through hygiene; seed one via the trusted path.
            duplicate = run_manager(
                tmp,
                "add",
                "requirements",
                "Release checks must pass before tagging.",
                "--summary",
                "Release checks gate tags.",
                "--source",
                "skill",
                "--status",
                "active",
            )

            routed = run_skill(tmp, "route-memory", "Release notes must stay in docs/manual-release-notes.md.")
            scan = run_skill(tmp, "hygiene-scan", "--limit", "20")
            plan = run_skill(tmp, "hygiene-plan", "--scope", "project")
            applied = run_skill(tmp, "hygiene-apply", "--safe")

            self.assertEqual(routed["route"], "repo_docs")
            self.assertEqual(scan["action"], "hygiene-scan")
            self.assertEqual(plan["action"], "hygiene-plan")
            self.assertIn("proposals", plan)
            self.assertTrue(any(item["id"] == duplicate["id"] and item["proposed_action"] == "merge" for item in plan["proposals"]))
            self.assertEqual(applied["action"], "hygiene-apply")
            self.assertTrue(any(item.get("id") == duplicate["id"] and item.get("applied") for item in applied["applied"]))
            self.assertNotEqual(first["id"], duplicate["id"])

    def test_reconcile_current_truth_command_plans_claim_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = run_skill(
                tmp,
                "save-insight",
                "project_state",
                "Latest Kimi score is 90.12.",
                "--summary",
                "Kimi score was 90.12.",
                "--status",
                "active",
                "--confidence",
                "0.7",
                "--claim-key",
                "recall.kimi.standard_average",
                "--claim-value",
                "90.12",
            )
            new = run_skill(
                tmp,
                "save-insight",
                "project_state",
                "Latest Kimi score is 95.91.",
                "--summary",
                "Kimi score is 95.91.",
                "--status",
                "validated",
                "--confidence",
                "0.95",
                "--importance",
                "0.95",
                "--trust",
                "0.95",
                "--claim-key",
                "recall.kimi.standard_average",
                "--claim-value",
                "95.91",
            )

            report = run_skill(tmp, "reconcile-current-truth", "--claim-key", "recall.kimi.standard_average")

            self.assertEqual(report["action"], "reconcile-current-truth")
            self.assertEqual(report["proposals"][0]["id"], old["id"])
            self.assertEqual(report["proposals"][0]["details"]["winner_id"], new["id"])
            self.assertTrue(report["proposals"][0]["safe_to_apply"])

    def test_audit_memory_surfaces_noise_candidates_and_quality_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            noisy = run_manager(
                tmp,
                "add",
                "commands",
                "Tool: Bash Command: Get-Content README.md Result: completed",
                "--summary",
                "Bash result captured.",
                "--source",
                "post_tool_use",
                "--status",
                "active",
            )
            run_skill(
                tmp,
                "save-insight",
                "decisions",
                "Use review-memory plus audit-memory to police store quality.",
                "--summary",
                "Use review plus audit for memory quality.",
                "--source",
                "finalizer",
                "--status",
                "active",
            )

            audit = run_skill(tmp, "audit-memory", "--limit", "10")
            review = run_skill(tmp, "review-memory", "--limit", "10")

            self.assertEqual(audit["action"], "audit-memory")
            self.assertEqual(audit["audit"]["shown"], 1)
            self.assertEqual(audit["audit"]["noise_candidates"][0]["id"], noisy["id"])
            self.assertEqual(review["review"]["quality"]["active_noise_candidates"], 1)
            self.assertEqual(review["review"]["quality"]["top_noisy_commands"][0]["pattern"], "Get-Content")
            self.assertIn("post_tool_use", review["review"]["source_counts"])

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
            result = run_skill(tmp, "retrieve-memory", "Stop finalizer continuation", "--category", "decisions", "--verbose")

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

    def test_save_insight_rejects_secret_like_content(self) -> None:
        payloads = [
            "AWS access key AKIAIOSFODNN7EXAMPLE with secret wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "Database password is HardCap@2026SuperSecret to unlock the build cache.",
            "Auth token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.4pcPyMD09olPSyXnrXCjTwXyr4BsezdI1AVTmud2fU4",
            "Use api_key=sk-proj-abc123xyz789supersecret for the build service.",
            "GitHub token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            for content in payloads:
                result = run_skill(
                    tmp,
                    "save-insight",
                    "decisions",
                    content,
                    "--summary",
                    "should be rejected",
                    "--source",
                    "skill",
                )
                self.assertEqual(result["result"], "rejected", content)
                self.assertEqual(result["category"], None, content)
                self.assertIn("secret", result["reason"])
            retrieval = run_skill(tmp, "retrieve-memory", "AKIA AWS token password")
            self.assertEqual(retrieval["results"], [])

    def test_save_insight_accepts_clean_content_after_secret_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rejected = run_skill(
                tmp,
                "save-insight",
                "decisions",
                "AWS access key AKIAIOSFODNN7EXAMPLE.",
                "--summary",
                "should be rejected",
                "--source",
                "skill",
            )
            self.assertEqual(rejected["result"], "rejected")
            saved = run_skill(
                tmp,
                "save-insight",
                "decisions",
                "Use CMake presets for build config.",
                "--summary",
                "CMake presets",
                "--source",
                "skill",
            )
            self.assertEqual(saved["action"], "save-insight")
            self.assertEqual(saved["category"], "decisions")

    def test_route_memory_rejects_broader_secret_shapes(self) -> None:
        secrets = [
            "AWS access key AKIAIOSFODNN7EXAMPLE should be kept safe.",
            "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.4pcPyMD09olPSyXnrXCjTwXyr4BsezdI1AVTmud2fU4 issued.",
            "GitHub token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 rotate soon.",
            "Password is HardCap@2026SuperSecret rotate quarterly.",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            for text in secrets:
                result = run_skill(tmp, "route-memory", text)
                self.assertEqual(result["route"], "reject", text)
                self.assertEqual(result["confidence"], 1.0, text)


if __name__ == "__main__":
    unittest.main()
