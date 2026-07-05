from __future__ import annotations

import unittest

from _harness import active_memory_dir, assert_memory_inside_project, memory_cmd, run_json, skill_cmd, temp_project


class SkillCliContractTests(unittest.TestCase):
    def test_list_categories_exposes_expected_memory_categories(self) -> None:
        with temp_project() as project:
            result = run_json(skill_cmd(project, "list-categories"))
            names = {item["name"] for item in result["categories"]}
            expected = {
                "decisions",
                "constraints",
                "debug_history",
                "preferences",
                "tasks",
                "session_summaries",
                "project_state",
                "architecture",
                "commands",
                "lessons_learned",
                "requirements",
                "risks",
            }
            self.assertTrue(expected.issubset(names))

    def test_save_retrieve_doctor_and_project_local_storage(self) -> None:
        with temp_project() as project:
            saved = run_json(skill_cmd(
                project,
                "save-insight",
                "requirements",
                "RECALL must keep memory under the active project RECALL memory directory.",
                "--summary",
                "Memory is project-local.",
                "--details",
                "The public skill adapter should store durable context without touching global state.",
                "--tag",
                "local-first",
                "--source",
                "quality-suite",
                "--status",
                "active",
                "--importance",
                "1.0",
                "--confidence",
                "0.95",
            ))
            self.assertEqual(saved["action"], "save-insight")
            self.assertEqual(saved["category"], "requirements")
            assert_memory_inside_project(project)

            memory_dir = active_memory_dir(project)
            self.assertTrue((memory_dir / "memory_config.json").exists())
            self.assertTrue((memory_dir / "memory.sqlite").exists())
            self.assertTrue((memory_dir / "vector_index.bin").exists())

            retrieved = run_json(skill_cmd(project, "retrieve-memory", "project local memory", "--summary"))
            self.assertGreaterEqual(len(retrieved["results"]), 1)
            top_result = retrieved["results"][0]
            self.assertIn("RECALL memory directory", top_result["content"])
            self.assertEqual(top_result["category"], "requirements")

            doctor = run_json(skill_cmd(project, "doctor"))
            self.assertTrue(doctor["report"]["index_complete"])
            self.assertEqual(doctor["report"]["warnings"], [])

    def test_secret_like_content_is_rejected_through_public_adapter(self) -> None:
        with temp_project() as project:
            saved = run_json(skill_cmd(project, "save-insight", "debug_history", "Deployment failed with api_key=dummy-secret-value", "--source", "quality-suite"))
            self.assertEqual(saved["result"], "rejected")
            self.assertIn("secret", saved["reason"])
            result = run_json(skill_cmd(project, "retrieve-memory", "deployment api key", "--category", "debug_history"))
            self.assertEqual(result["results"], [])

    def test_secret_like_content_in_legacy_store_is_redacted_on_read(self) -> None:
        with temp_project() as project:
            run_json(memory_cmd(
                project,
                "add",
                "debug_history",
                "Deployment failed with api_key=dummy-secret-value",
                "--source",
                "quality-suite",
                "--status",
                "active",
            ))
            result = run_json(skill_cmd(project, "retrieve-memory", "deployment failed", "--category", "debug_history"))
            self.assertGreaterEqual(len(result["results"]), 1)
            self.assertNotIn("dummy-secret-value", result["results"][0]["content"])

    def test_status_filter_selects_current_memory(self) -> None:
        with temp_project() as project:
            run_json(skill_cmd(project, "save-insight", "requirements", "Old CLI contract used raw output.", "--status", "superseded", "--tag", "cli-contract"))
            run_json(skill_cmd(project, "save-insight", "requirements", "Current CLI contract uses compact JSON summaries.", "--status", "active", "--tag", "cli-contract"))

            active = run_json(skill_cmd(project, "retrieve-memory", "CLI contract", "--status", "active"))
            superseded = run_json(skill_cmd(project, "retrieve-memory", "CLI contract", "--status", "superseded"))

            self.assertEqual(len(active["results"]), 1)
            self.assertIn("Current", active["results"][0]["content"])
            self.assertEqual(len(superseded["results"]), 1)
            self.assertIn("Old", superseded["results"][0]["content"])

    def test_review_and_audit_surface_memory_quality_signals(self) -> None:
        with temp_project() as project:
            # Seed noise through the trusted manager path: skill saves that
            # declare hook sources are gated by the auto-capture policy now.
            noisy = run_json(memory_cmd(
                project,
                "add",
                "commands",
                "Tool: Bash Command: Get-Content README.md Result: completed",
                "--summary",
                "Bash result captured.",
                "--source",
                "post_tool_use",
                "--status",
                "active",
            ))
            run_json(skill_cmd(
                project,
                "save-insight",
                "project_state",
                "RECALL should surface noise candidates before archive cleanup.",
                "--summary",
                "Surface noise candidates before cleanup.",
                "--source",
                "finalizer",
                "--status",
                "active",
            ))

            review = run_json(skill_cmd(project, "review-memory", "--limit", "10"))
            audit = run_json(skill_cmd(project, "audit-memory", "--limit", "10"))

            self.assertEqual(review["review"]["quality"]["active_noise_candidates"], 1)
            self.assertEqual(review["review"]["quality"]["generic_summary_count"], 1)
            self.assertEqual(review["review"]["quality"]["top_noisy_commands"][0]["pattern"], "Get-Content")
            self.assertIn("post_tool_use", review["review"]["source_counts"])
            self.assertEqual(audit["audit"]["shown"], 1)
            self.assertEqual(audit["audit"]["noise_candidates"][0]["id"], noisy["id"])
            self.assertIn("archive-noise", audit["audit"]["quality"]["recommended_cleanup_command"])

    def test_repair_recovers_missing_vector_index(self) -> None:
        with temp_project() as project:
            run_json(skill_cmd(project, "save-insight", "architecture", "Storage is the source of truth for RECALL memory."))
            index_path = active_memory_dir(project) / "vector_index.bin"
            index_path.write_text("", encoding="utf-8")

            doctor_before = run_json(skill_cmd(project, "doctor"))
            self.assertFalse(doctor_before["report"]["index_complete"])

            repair = run_json(skill_cmd(project, "repair"))
            self.assertTrue(repair["report"]["doctor"]["index_complete"])
            self.assertEqual(repair["report"]["doctor"]["warnings"], [])


if __name__ == "__main__":
    unittest.main()
