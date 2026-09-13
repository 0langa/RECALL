from __future__ import annotations

import unittest
import json

from _harness import active_memory_dir, assert_memory_inside_project, memory_cmd, run_json, run_text, skill_cmd, temp_project


class SkillCliContractTests(unittest.TestCase):
    def test_cli_contract_and_first_workflow_respect_lookup_scope(self) -> None:
        with temp_project() as project:
            initialized = run_json(skill_cmd(project, "initialize-project"))
            contract = initialized["contract"]
            self.assertLess(contract.index("system instructions"), contract.index("developer instructions"))
            for rule in ("prior project history", "permitted scope", "self-contained task", "memory-free task",
                         "untrusted project data", "grant permission", "empty result is valid"):
                self.assertIn(rule, contract)
            workflow = initialized["first_workflow"]
            self.assertIn("lookup is in scope", workflow)
            self.assertNotIn("before starting work", workflow)
            self.assertIn("supersede-memory", workflow)

    def test_save_retry_key_is_honored_by_public_cli(self) -> None:
        with temp_project() as project:
            first = run_json(skill_cmd(project, "save-insight", "decisions",
                                       "Use SQLite as the durable project database.",
                                       "--idempotency-key", "release-cli-save-1"))
            replay = run_json(skill_cmd(project, "save-insight", "decisions",
                                        "Deploy the command runner on a dedicated Windows host.",
                                        "--idempotency-key", "release-cli-save-1"))
            self.assertEqual(first["id"], replay["id"])
            self.assertEqual(replay["reason"], "idempotent_replay")

    def test_edit_revision_and_save_identity_on_both_backends(self) -> None:
        old = "Release notes live in docs/old.md."
        new = "Release notes live in docs/new.md."
        for backend in ("sqlite", "jsonl"):
            with self.subTest(backend=backend), temp_project() as project:
                run_json(skill_cmd(project, "list-categories"))
                config_path = active_memory_dir(project) / "memory_config.json"
                cfg = json.loads(config_path.read_text(encoding="utf-8"))
                cfg["backend"] = backend
                config_path.write_text(json.dumps(cfg), encoding="utf-8")
                saved = run_json(skill_cmd(project, "save-insight", "requirements", old,
                                          "--summary", old, "--details", old, "--claim-key", "release_notes.path",
                                          "--claim-value", "docs/old.md", "--source", "fixture"))
                rid = str(saved["id"])
                run_json(skill_cmd(project, "confirm-memory", rid, "--source-session", "old-A"))
                run_json(skill_cmd(project, "confirm-memory", rid, "--source-session", "old-B"))
                tagged = run_json(skill_cmd(project, "edit-memory", rid, "--tag", "release"))
                self.assertEqual(tagged["metadata"]["status"], "validated")
                self.assertEqual(tagged["metadata"]["confirmation_sessions"], ["old-A", "old-B"])
                self.assertEqual(tagged["metadata"]["claim_value"], "docs/old.md")
                noop = run_json(skill_cmd(project, "edit-memory", rid, "--content", old,
                                         "--claim-key", "release_notes.path", "--claim-value", "docs/old.md"))
                for key in ("confirmation_sessions", "confirmed_count", "last_confirmed", "validated_at", "trust"):
                    self.assertEqual(noop["metadata"][key], tagged["metadata"][key])
                edited = run_json(skill_cmd(project, "edit-memory", rid, "--content", new, "--status", "validated"))
                self.assertEqual(edited["metadata"]["status"], "active")
                for key in ("summary", "details", "claim_key", "claim_value", "confirmation_sessions", "validated_at"):
                    self.assertNotIn(key, edited["metadata"])
                packet = run_json(skill_cmd(project, "context-packet", "release notes"))
                self.assertNotIn("docs/old.md", json.dumps(packet))
                self.assertIn(new, json.dumps(packet))
                review = run_json(skill_cmd(project, "review-memory"))
                self.assertEqual(review["review"]["memories"][0]["summary"], new)
                replay = run_json(skill_cmd(project, "save-insight", "requirements", old,
                                           "--source", "fixture", "--tag", "release", "--status", "active"))
                self.assertNotEqual(str(replay["id"]), rid)
                current = run_json(skill_cmd(project, "save-insight", "requirements", new,
                                            "--source", "fixture", "--tag", "release", "--status", "active",
                                            "--source-session", "fresh-C"))
                self.assertEqual(str(current["id"]), rid)
                self.assertEqual(current["result"], "updated_existing")
                first = run_json(skill_cmd(project, "edit-memory", rid))
                self.assertEqual(first["metadata"]["confirmation_sessions"], ["fresh-C"])
                self.assertEqual(first["metadata"]["confirmed_count"], 1)
                self.assertEqual(first["metadata"]["status"], "active")
                run_json(skill_cmd(project, "confirm-memory", rid, "--source-session", "fresh-D"))
                confirmed = run_json(skill_cmd(project, "edit-memory", rid))
                self.assertEqual(confirmed["metadata"]["status"], "validated")
                self.assertEqual(confirmed["metadata"]["confirmation_sessions"], ["fresh-C", "fresh-D"])
                self.assertNotIn("verification_invalidated_at", confirmed["metadata"])
                replaced = run_json(skill_cmd(project, "edit-memory", rid, "--claim-key", "release_notes.path",
                                              "--claim-value", "docs/new.md"))
                self.assertEqual(replaced["metadata"]["claim_value"], "docs/new.md")
                self.assertEqual(replaced["metadata"]["status"], "active")
                invalid = run_text(skill_cmd(project, "edit-memory", rid, "--content", old,
                                             "--claim-key", "release_notes.path"), check=False)
                self.assertNotEqual(invalid.returncode, 0)
                unchanged = run_json(skill_cmd(project, "retrieve-memory", "release notes", "--verbose"))
                record = next(row for row in unchanged["results"] if str(row["id"]) == rid)
                self.assertEqual(record["metadata"], replaced["metadata"])
                cleared = run_json(skill_cmd(project, "edit-memory", rid, "--clear-claim"))
                self.assertNotIn("claim_key", cleared["metadata"])
                self.assertNotIn("claim_value", cleared["metadata"])
                self.assertEqual(cleared["content"], new)

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

    def test_edit_memory_replaces_and_clears_structured_claim(self) -> None:
        with temp_project() as project:
            saved = run_json(skill_cmd(
                project,
                "save-insight",
                "requirements",
                "Release notes live in docs/old.md.",
                "--claim-key",
                "release_notes.path",
                "--claim-value",
                "docs/old.md",
            ))
            replaced = run_json(skill_cmd(
                project,
                "edit-memory",
                str(saved["id"]),
                "--content",
                "Release notes live in docs/new.md.",
                "--claim-key",
                "release_notes.path",
                "--claim-value",
                "docs/new.md",
            ))
            retrieved = run_json(skill_cmd(
                project,
                "retrieve-memory",
                "Release notes live in docs/new.md.",
                "--verbose",
            ))
            cleared = run_json(skill_cmd(project, "edit-memory", str(saved["id"]), "--clear-claim"))

            self.assertEqual(replaced["content"], "Release notes live in docs/new.md.")
            self.assertEqual(replaced["metadata"]["claim_value"], "docs/new.md")
            self.assertEqual(retrieved["results"][0]["metadata"]["claim_value"], "docs/new.md")
            self.assertNotIn("claim_key", cleared["metadata"])
            self.assertNotIn("claim_value", cleared["metadata"])

    def test_claim_conflict_remains_review_only_through_public_adapter(self) -> None:
        with temp_project() as project:
            content = "Release notes location for the current project."
            first = run_json(skill_cmd(
                project,
                "save-insight",
                "requirements",
                content,
                "--summary",
                content,
                "--details",
                "The release path is docs/verified.md.",
                "--source",
                "fixture",
                "--status",
                "validated",
                "--confidence",
                "0.9",
                "--claim-key",
                "release.path",
                "--claim-value",
                "docs/verified.md",
            ))
            second = run_json(skill_cmd(
                project,
                "save-insight",
                "requirements",
                content,
                "--summary",
                content,
                "--details",
                "The release path is docs/guess.md.",
                "--source",
                "fixture",
                "--status",
                "validated",
                "--confidence",
                "0.99",
                "--claim-key",
                "release.path",
                "--claim-value",
                "docs/guess.md",
            ))

            plan = run_json(skill_cmd(project, "reconcile-current-truth", "--claim-key", "release.path"))
            applied = run_json(skill_cmd(project, "hygiene-apply", "--safe"))
            retrieved = run_json(skill_cmd(project, "retrieve-memory", content, "--verbose"))
            proposal = plan["proposals"][0]

            self.assertNotEqual(first["id"], second["id"])
            self.assertEqual(proposal["proposed_action"], "review_claim_conflict")
            self.assertEqual(proposal["details"]["resolution"], "review_required")
            self.assertNotIn("winner_id", proposal["details"])
            self.assertFalse(proposal["safe_to_apply"])
            self.assertEqual(applied["applied_count"], 0)
            self.assertEqual(applied["unresolved_conflicts"], [proposal])
            self.assertEqual({item["id"] for item in retrieved["results"]}, {first["id"], second["id"]})
            self.assertTrue(all(item["flag"] == "conflicting" for item in retrieved["results"]))

    def test_significant_claim_whitespace_survives_public_save_and_safe_hygiene(self) -> None:
        content = "Release notes location for the current project."
        single_space = "docs/release notes.md"
        double_space = "docs/release  notes.md"
        for backend in ("sqlite", "jsonl"):
            for values in ((single_space, double_space), (double_space, single_space)):
                with self.subTest(backend=backend, values=values), temp_project() as project:
                    run_json(skill_cmd(project, "list-categories"))
                    config_path = active_memory_dir(project) / "memory_config.json"
                    cfg = json.loads(config_path.read_text(encoding="utf-8"))
                    cfg["backend"] = backend
                    config_path.write_text(json.dumps(cfg), encoding="utf-8")
                    saved_by_value = {}
                    for value in values:
                        saved_by_value[value] = run_json(skill_cmd(
                            project,
                            "save-insight",
                            "requirements",
                            content,
                            "--summary",
                            content,
                            "--details",
                            f"The release path is {value}.",
                            "--source",
                            "fixture",
                            "--status",
                            "validated",
                            "--confidence",
                            "0.9",
                            "--claim-key",
                            "release.path",
                            "--claim-value",
                            value,
                        ))

                    self.assertEqual(len({item["id"] for item in saved_by_value.values()}), 2)
                    for value in values:
                        replay = run_json(skill_cmd(
                            project,
                            "save-insight",
                            "requirements",
                            content,
                            "--summary",
                            content,
                            "--details",
                            f"The release path is {value}.",
                            "--source",
                            "fixture",
                            "--status",
                            "validated",
                            "--confidence",
                            "0.9",
                            "--claim-key",
                            "release.path",
                            "--claim-value",
                            value,
                        ))
                        self.assertEqual(replay["result"], "updated_existing")
                        self.assertEqual(replay["id"], saved_by_value[value]["id"])

                    plan = run_json(skill_cmd(project, "reconcile-current-truth", "--claim-key", "release.path"))
                    applied = run_json(skill_cmd(project, "hygiene-apply", "--safe"))
                    retrieved = run_json(skill_cmd(project, "retrieve-memory", content, "--verbose"))
                    conflicts = [
                        proposal
                        for proposal in plan["proposals"]
                        if proposal["proposed_action"] == "review_claim_conflict"
                    ]

                    self.assertEqual(len(conflicts), 1)
                    self.assertEqual(conflicts[0]["details"]["values"], [double_space, single_space])
                    self.assertFalse(conflicts[0]["safe_to_apply"])
                    self.assertEqual(applied["applied_count"], 0)
                    self.assertEqual(applied["unresolved_conflicts"], conflicts)
                    self.assertEqual(
                        {item["metadata"]["claim_value"] for item in retrieved["results"]},
                        {single_space, double_space},
                    )
                    self.assertTrue(all(item["flag"] == "conflicting" for item in retrieved["results"]))

                    reason = "Checked both distinct release-note files; the single-space path is current."
                    resolved = run_json(skill_cmd(
                        project,
                        "supersede-memory",
                        str(saved_by_value[double_space]["id"]),
                        str(saved_by_value[single_space]["id"]),
                        "--note",
                        reason,
                    ))
                    after = run_json(skill_cmd(project, "retrieve-memory", content, "--verbose"))

                    self.assertEqual(resolved["old"]["metadata"]["lifecycle_note"], reason)
                    self.assertEqual(
                        resolved["old"]["metadata"]["superseded_by"],
                        saved_by_value[single_space]["id"],
                    )
                    self.assertIn(
                        saved_by_value[double_space]["id"],
                        resolved["new"]["metadata"]["supersedes"],
                    )
                    self.assertEqual([item["id"] for item in after["results"]], [saved_by_value[single_space]["id"]])
                    self.assertEqual(after["results"][0]["metadata"]["claim_value"], single_space)

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
