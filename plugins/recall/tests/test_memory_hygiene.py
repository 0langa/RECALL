from __future__ import annotations

import tempfile
import unittest
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import memory_hygiene  # noqa: E402
import memory_manager  # noqa: E402
import config as recall_config  # noqa: E402
import storage  # noqa: E402
from services import provenance_service  # noqa: E402


class MemoryHygieneTests(unittest.TestCase):
    def test_refresh_plan_does_not_depend_on_scan_clock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "truth.md").write_text("Current release truth.", encoding="utf-8")
            memory_manager.add_record("requirements", "The release follows the source document.",
                {"status": "active", **provenance_service.describe_file(tmp, "truth.md")}, tmp)
            with patch.object(provenance_service, "utc_now", side_effect=["2026-01-01", "2026-01-02"]):
                first = memory_hygiene.hygiene_plan(tmp)
                second = memory_hygiene.hygiene_plan(tmp)
            self.assertEqual(first, second)
            with patch.object(provenance_service, "describe_file", side_effect=AssertionError("new descriptor")):
                result = memory_hygiene.hygiene_apply(tmp, safe=True, plan=first)
            self.assertEqual(result["applied_count"], 1)

    def test_case_distinct_opaque_claim_values_remain_a_review_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for value in ("docs/Release.md", "docs/release.md"):
                memory_manager.add_record("requirements", "Release notes live at the configured path.",
                    {"status": "active", "source": "fixture", "claim_key": "Release.Path", "claim_value": value}, tmp)
            result = memory_hygiene.reconcile_current_truth(tmp, claim_key="Release.Path")
            self.assertEqual(result["proposals"][0]["details"]["values"], ["docs/Release.md", "docs/release.md"])
            self.assertFalse(result["proposals"][0]["safe_to_apply"])

    def test_claim_reconciliation_keeps_legacy_projection_and_saved_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for value in ("docs/Release.md", "docs/release.md"):
                memory_manager.add_record(
                    "requirements",
                    "Release notes live at the configured path.",
                    {"status": "active", "source": "fixture", "claim_key": "Release.Path", "claim_value": value},
                    tmp,
                )
            result = memory_hygiene.reconcile_current_truth(
                tmp,
                claim_key="Release.Path",
                scan_limit=2,
                output_limit=1,
                action_limit=0,
            )
            plan = result["plan"]
            self.assertEqual(result["action"], "reconcile-current-truth")
            self.assertEqual(plan["action"], "hygiene-plan")
            self.assertEqual(plan["claim_key"], "Release.Path")
            self.assertEqual(plan["limits"], {"scan_limit": 2, "output_limit": 1, "action_limit": 0})
            with patch.object(memory_hygiene, "hygiene_plan", side_effect=AssertionError("replanned")):
                applied = memory_hygiene.hygiene_apply(tmp, safe=True, plan=json.loads(json.dumps(plan)))
            self.assertEqual(applied["plan_id"], plan["plan_id"])
            self.assertEqual(applied["applied_count"], 0)

    def test_precondition_and_mutation_exclude_a_competing_writer(self) -> None:
        for backend in ("sqlite", "jsonl"):
            with self.subTest(backend=backend), tempfile.TemporaryDirectory() as tmp:
                cfg = recall_config.default_config()
                cfg["backend"] = backend
                recall_config.save_config(cfg, tmp)
                record = memory_manager.add_record("preferences", "Project layout preference requires evidence.",
                                                   {"status": "active", "source": "fixture"}, tmp)
                plan = memory_hygiene.hygiene_plan(tmp)
                reached = threading.Event()
                attempted = threading.Event()
                completed = threading.Event()
                original = memory_hygiene._apply_proposal

                def competing_writer(*, reached=reached, attempted=attempted, record=record, completed=completed):
                    self.assertTrue(reached.wait(10))
                    attempted.set()
                    storage.update_record_metadata(record.id, {"status": "resolved"}, tmp)
                    completed.set()

                def applying(operation, root, *, reached=reached, attempted=attempted,
                             completed=completed, original=original):
                    reached.set()
                    self.assertTrue(attempted.wait(10))
                    self.assertFalse(completed.wait(0.15), "writer entered between precondition and mutation")
                    return original(operation, root)

                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(competing_writer)
                    with patch.object(memory_hygiene, "_apply_proposal", side_effect=applying):
                        result = memory_hygiene.hygiene_apply(tmp, safe=True, plan=plan)
                    future.result(timeout=10)
                self.assertEqual(result["applied_count"], 1)
                self.assertEqual(storage.get_record(record.id, tmp).metadata["status"], "resolved")

    def test_source_change_after_review_skips_exact_saved_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = memory_manager.add_record("requirements", "Release truth uses the source document.",
                {"source": "fixture", "status": "active", "source_kind": "file", "source_path": "truth.md"}, tmp)
            plan = memory_hygiene.hygiene_plan(tmp)
            (Path(tmp) / "truth.md").write_text("The missing source is restored.", encoding="utf-8")
            result = memory_hygiene.hygiene_apply(tmp, safe=True, plan=plan)
            self.assertEqual(result["applied_count"], 0)
            self.assertEqual(result["applied"][0]["reason"], "source_state_changed")
            self.assertEqual(storage.get_record(record.id, tmp).metadata["status"], "active")

    def test_source_change_before_operation_keeps_old_observation_and_skips_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "truth.md"
            source.write_text("Truth A.", encoding="utf-8")
            initial = provenance_service.describe_file(tmp, "truth.md")
            record = memory_manager.add_record(
                "requirements",
                "Release truth uses the source document.",
                {"source": "fixture", "status": "active", **initial},
                tmp,
            )
            original_operation = memory_hygiene._operation

            def source_changes_before_operation(proposal, records, observations):
                source.write_text("Truth B.", encoding="utf-8")
                return original_operation(proposal, records, observations)

            with patch.object(memory_hygiene, "_operation", side_effect=source_changes_before_operation):
                plan = memory_hygiene.hygiene_plan(tmp)
            operation = next(item for item in plan["operations"] if item["id"] == record.id)
            self.assertEqual(operation["proposed_action"], "refresh_source")
            self.assertEqual(operation["source_preconditions"][0]["sha256"], initial["source_hash"])
            self.assertEqual(operation["source_descriptor"]["source_hash"], initial["source_hash"])

            result = memory_hygiene.hygiene_apply(tmp, safe=True, plan=plan)
            refreshed = storage.get_record(record.id, tmp)
            self.assertEqual(result["applied_count"], 0)
            self.assertEqual(result["applied"][0]["reason"], "source_state_changed")
            self.assertEqual(refreshed.metadata["source_hash"], initial["source_hash"])
            self.assertNotIn("last_confirmed", refreshed.metadata)

    def test_refresh_plan_uses_one_observation_for_precondition_and_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "truth.md"
            source.write_text("Truth A.", encoding="utf-8")
            source_hash = provenance_service.hash_file(source)
            record = memory_manager.add_record(
                "requirements",
                "Release truth uses the source document.",
                {
                    "source": "fixture",
                    "status": "active",
                    "source_kind": "file",
                    "source_path": "truth.md",
                    "source_hash": source_hash,
                },
                tmp,
            )
            original_describe = provenance_service.describe_file
            with (
                patch.object(provenance_service, "describe_file", wraps=original_describe) as describe,
                patch.object(memory_hygiene, "_source_state", side_effect=AssertionError("source was re-read")),
            ):
                plan = memory_hygiene.hygiene_plan(tmp)
            operation = next(item for item in plan["operations"] if item["id"] == record.id)
            self.assertEqual(describe.call_count, 1)
            self.assertEqual(operation["source_preconditions"], [{
                "source_path": "truth.md", "state": "file", "sha256": source_hash,
            }])
            self.assertEqual(operation["source_descriptor"]["source_path"], "truth.md")
            self.assertEqual(operation["source_descriptor"]["source_hash"], source_hash)

    def test_apply_rejects_missing_reviewed_plan_before_planning_or_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = memory_manager.add_record(
                "preferences",
                "Project layout preference requires evidence.",
                {"status": "active", "source": "fixture"},
                tmp,
            )
            before = memory_hygiene._record_state(storage.get_record(record.id, tmp))
            with patch.object(memory_hygiene, "hygiene_plan", side_effect=AssertionError("planned")):
                with self.assertRaisesRegex(ValueError, "explicit reviewed plan"):
                    memory_hygiene.hygiene_apply(tmp, safe=True)
            self.assertEqual(memory_hygiene._record_state(storage.get_record(record.id, tmp)), before)

    def test_saved_plan_is_stable_and_skips_changed_records_without_replanning(self) -> None:
        for backend in ("sqlite", "jsonl"):
            with self.subTest(backend=backend), tempfile.TemporaryDirectory() as tmp:
                cfg = recall_config.default_config()
                cfg["backend"] = backend
                recall_config.save_config(cfg, tmp)
                records = [memory_manager.add_record(
                    "preferences", f"Preference candidate number {i} for project layout.",
                    {"source": "fixture", "status": "active"}, tmp,
                ) for i in range(3)]
                plan = memory_hygiene.hygiene_plan(tmp, scan_limit=2, output_limit=2, action_limit=1)
                repeated = memory_hygiene.hygiene_plan(tmp, scan_limit=2, output_limit=2, action_limit=1)
                self.assertEqual(plan, repeated)
                self.assertEqual(plan["plan_version"], 1)
                self.assertEqual(len(plan["operations"]), 1)
                self.assertEqual(plan["omissions"]["unscanned_record_ids"], [records[2].id])
                self.assertTrue(plan["truncated"])
                operation = plan["operations"][0]
                self.assertTrue(operation["operation_id"])
                self.assertTrue(operation["preconditions"])
                memory_manager.update_record_metadata(operation["id"], {"status": "resolved"}, tmp)
                with patch.object(memory_hygiene, "hygiene_plan", side_effect=AssertionError("replanned")):
                    result = memory_hygiene.hygiene_apply(tmp, safe=True, plan=json.loads(json.dumps(plan)))
                self.assertEqual(result["applied_count"], 0)
                self.assertEqual(result["applied"][0]["reason"], "record_state_changed")
                self.assertEqual(storage.get_record(records[1].id, tmp).metadata["status"], "active")

    def test_saved_plan_never_includes_new_records_or_reselects_after_action_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(3):
                memory_manager.add_record("preferences", f"Layout preference candidate {i}.",
                                          {"status": "active", "source": "fixture"}, tmp)
            plan = memory_hygiene.hygiene_plan(tmp, action_limit=2)
            new = memory_manager.add_record("preferences", "New layout preference candidate.",
                                            {"status": "active", "source": "fixture"}, tmp)
            with patch.object(memory_hygiene, "hygiene_plan", side_effect=AssertionError("replanned")):
                result = memory_hygiene.hygiene_apply(tmp, safe=True, plan=plan, action_limit=1)
            self.assertEqual(result["applied_count"], 1)
            self.assertEqual(result["applied"][0]["operation_id"], plan["operations"][0]["operation_id"])
            self.assertEqual(storage.get_record(new.id, tmp).metadata["status"], "active")

    def test_scan_output_limit_is_reflected_in_saved_plan_omissions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(3):
                memory_manager.add_record(
                    "preferences",
                    f"Layout preference candidate {i} needs review.",
                    {"status": "active", "source": "fixture"},
                    tmp,
                )
            scan = memory_hygiene.hygiene_scan(tmp, scan_limit=3, output_limit=1, action_limit=0)
            self.assertEqual(len(scan["proposals"]), 1)
            self.assertTrue(scan["omissions"]["output_operation_ids"])
            self.assertTrue(scan["truncated"])
            self.assertGreater(scan["omitted_proposals"], 0)

    def test_merge_and_stale_cannot_change_the_same_card_in_one_plan(self) -> None:
        for backend in ("sqlite", "jsonl"):
            with self.subTest(backend=backend), tempfile.TemporaryDirectory() as tmp:
                cfg = recall_config.default_config()
                cfg["backend"] = backend
                recall_config.save_config(cfg, tmp)
                metadata = {"status": "active", "source": "fixture", "source_kind": "file",
                            "source_path": "missing.md", "source_hash": "missing"}
                primary = memory_manager.add_record("requirements", "Release checks use the local source file.", metadata, tmp)
                secondary = memory_manager.add_record("requirements", primary.content, metadata, tmp)
                plan = memory_hygiene.hygiene_plan(tmp)
                touched = [key for op in plan["operations"] for key in op["preconditions"]]
                self.assertEqual(len(touched), len(set(touched)))
                self.assertTrue(plan["omissions"]["conflicting_operations"])
                result = memory_hygiene.hygiene_apply(tmp, safe=True, plan=plan)
                self.assertTrue(result["applied_count"])
                self.assertEqual(storage.get_record(secondary.id, tmp).metadata["status"], "superseded")

    def test_plan_rejects_wrong_store_and_modified_operations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as other:
            memory_manager.add_record("preferences", "Project layout preference candidate.", root=tmp)
            plan = memory_hygiene.hygiene_plan(tmp)
            with self.assertRaisesRegex(ValueError, "store"):
                memory_hygiene.hygiene_apply(other, safe=True, plan=plan)
            plan["operations"][0]["id"] = 999
            with self.assertRaisesRegex(ValueError, "integrity"):
                memory_hygiene.hygiene_apply(tmp, safe=True, plan=plan)

    def test_exact_automatic_duplicate_updates_existing_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            metadata = memory_manager.build_card_metadata(
                source="post_tool_use",
                status="active",
                tags=["tool-use", "bash"],
                base={
                    "tool_name": "Bash",
                    "command": "python -m unittest",
                    "auto_capture_policy": "test_result",
                },
            )
            first = memory_manager.add_record_if_useful("commands", "Command: python -m unittest\nOK", metadata, tmp)
            second = memory_manager.add_record_if_useful("commands", "Command: python -m unittest\nOK", metadata, tmp)
            result = memory_manager.query("python unittest", categories=["commands"], root=tmp)

            self.assertEqual(first["action"], "saved")
            self.assertEqual(second["action"], "updated_existing")
            self.assertEqual(second["duplicate_id"], first["record"].id)
            self.assertEqual(len(result["results"]), 1)
            self.assertIn("last_confirmed", result["results"][0]["metadata"])

    def test_existing_fingerprint_does_not_make_conflicting_claim_exact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            content = "Release notes location for the current project."
            existing_metadata = memory_manager.build_card_metadata(
                source="fixture",
                status="validated",
                base={"claim_key": "release.path", "claim_value": "docs/guess.md"},
            )
            existing_metadata["recall_fingerprint"] = memory_hygiene.content_fingerprint(
                "requirements",
                content,
                existing_metadata,
            )
            existing = memory_manager.add_record("requirements", content, existing_metadata, tmp)
            candidate_metadata = memory_manager.build_card_metadata(
                source="fixture",
                status="validated",
                base={"claim_key": "release.path", "claim_value": "docs/verified.md"},
            )

            outcome = memory_manager.add_record_if_useful(
                "requirements",
                content,
                candidate_metadata,
                tmp,
            )

            self.assertEqual(outcome["action"], "saved_related")
            self.assertNotEqual(outcome["record"].id, existing.id)
            self.assertEqual(outcome["record"].metadata["related_memory_id"], existing.id)
            self.assertEqual(
                {
                    memory_manager.get_record(existing.id, tmp).metadata["claim_value"],
                    outcome["record"].metadata["claim_value"],
                },
                {"docs/guess.md", "docs/verified.md"},
            )

    def test_save_time_exact_claim_comparison_preserves_internal_whitespace(self) -> None:
        cases = (
            ("single versus double space", "docs/release notes.md", "docs/release  notes.md"),
            ("space versus tab", "docs/release notes.md", "docs/release\tnotes.md"),
        )
        for label, first_value, second_value in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                content = "Release notes location for the current project."
                first_metadata = memory_manager.build_card_metadata(
                    source="fixture",
                    status="validated",
                    base={"claim_key": "release.path", "claim_value": first_value},
                )
                second_metadata = memory_manager.build_card_metadata(
                    source="fixture",
                    status="validated",
                    base={"claim_key": "release.path", "claim_value": second_value},
                )

                self.assertEqual(
                    memory_hygiene.content_fingerprint("requirements", content, first_metadata),
                    memory_hygiene.content_fingerprint("requirements", content, second_metadata),
                )

                first = memory_manager.add_record_if_useful("requirements", content, first_metadata, tmp)
                second = memory_manager.add_record_if_useful("requirements", content, second_metadata, tmp)
                repeated = memory_manager.add_record_if_useful("requirements", content, second_metadata, tmp)

                self.assertEqual(first["action"], "saved")
                self.assertEqual(second["action"], "saved_related")
                self.assertNotEqual(second["record"].id, first["record"].id)
                self.assertEqual(second["record"].metadata["related_memory_id"], first["record"].id)
                self.assertEqual(repeated["action"], "updated_existing")
                self.assertEqual(repeated["duplicate_id"], second["record"].id)

    def test_near_duplicate_is_saved_with_related_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            metadata = memory_manager.build_card_metadata(
                source="post_tool_use",
                status="active",
                tags=["tool-use", "bash"],
                base={
                    "tool_name": "Bash",
                    "command": "python -m unittest",
                    "auto_capture_policy": "test_result",
                },
            )
            first = memory_manager.add_record_if_useful(
                "commands",
                "Tool: Bash\nCommand: python -m unittest discover -s tests\nOK",
                metadata,
                tmp,
            )
            second = memory_manager.add_record_if_useful(
                "commands",
                "Tool: Bash\nCommand: python -m unittest discover -s tests\nRan 49 tests\nOK",
                metadata,
                tmp,
            )

            self.assertEqual(second["action"], "saved_related")
            self.assertEqual(second["record"].metadata["related_memory_id"], first["record"].id)
            self.assertGreaterEqual(
                second["record"].metadata["related_similarity"],
                memory_hygiene.NEAR_DUPLICATE_THRESHOLD,
            )

    def test_explicit_add_record_keeps_duplicate_user_memories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_manager.add_record("requirements", "The user explicitly repeated this requirement.", root=tmp)
            memory_manager.add_record("requirements", "The user explicitly repeated this requirement.", root=tmp)
            result = memory_manager.query("explicitly repeated requirement", categories=["requirements"], root=tmp)

            self.assertEqual(len(result["results"]), 2)

    def test_route_memory_selects_non_recall_surfaces(self) -> None:
        self.assertEqual(
            memory_hygiene.route_memory("Release notes must stay in docs/manual-release-notes.md.")["route"],
            "repo_docs",
        )
        self.assertEqual(
            memory_hygiene.route_memory("Update skills/memory-hygiene/SKILL.md with this routing policy.")["route"],
            "skill_or_plugin_instructions",
        )
        self.assertEqual(
            memory_hygiene.route_memory("This is temporary scratch for this chat only.")["route"],
            "current_chat_only",
        )
        self.assertEqual(
            memory_hygiene.route_memory("api_key=secret-value")["route"],
            "reject",
        )

    def test_hygiene_plan_detects_exact_and_near_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = memory_manager.add_record("requirements", "Release checks must pass before tagging.", root=tmp)
            duplicate = memory_manager.add_record("requirements", "Release checks must pass before tagging.", root=tmp)
            memory_manager.add_record("requirements", "Release checks must pass before tagging and publishing.", root=tmp)

            plan = memory_hygiene.hygiene_plan(tmp)
            proposals = plan["proposals"]
            exact = [item for item in proposals if item["id"] == duplicate.id and item["proposed_action"] == "merge"]
            near_items = [item for item in proposals if item["proposed_action"] == "review_near_duplicate"]

            self.assertEqual(plan["action"], "hygiene-plan")
            self.assertEqual(exact[0]["related_ids"], [first.id])
            self.assertTrue(exact[0]["safe_to_apply"])
            self.assertFalse(near_items[0]["safe_to_apply"])
            self.assertEqual(near_items[0]["details"]["similarity"], 0.75)
            self.assertIn(near_items[0]["id"], plan["requires_confirmation"])

    def test_hygiene_plan_marks_missing_source_stale_and_apply_is_non_destructive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "docs" / "truth.md"
            source.parent.mkdir()
            source.write_text("Current truth.", encoding="utf-8")
            metadata = memory_manager.build_card_metadata(
                source="skill",
                status="active",
                base=provenance_service.describe_file(tmp, "docs/truth.md"),
            )
            record = memory_manager.add_record("architecture", "Architecture follows docs/truth.md.", metadata, tmp)
            source.unlink()

            plan = memory_hygiene.hygiene_plan(tmp)
            stale = [item for item in plan["proposals"] if item["id"] == record.id and item["proposed_action"] == "stale"]
            applied = memory_hygiene.hygiene_apply(tmp, safe=True, plan=plan)
            result = memory_manager.query("Architecture follows docs truth", categories=["architecture"], statuses=["stale"], root=tmp)

            self.assertEqual(stale[0]["reason"], "source_path no longer exists")
            self.assertTrue(stale[0]["safe_to_apply"])
            self.assertNotIn("delete", json.dumps(applied))
            self.assertEqual(result["results"][0]["metadata"]["status"], "stale")

    def test_reconcile_current_truth_keeps_unsupported_conflicts_review_only(self) -> None:
        cases = (
            (
                "equal evidence",
                (("docs/verified.md", "validated", 0.9), ("docs/guess.md", "validated", 0.9)),
            ),
            (
                "swapped insertion order",
                (("docs/guess.md", "validated", 0.9), ("docs/verified.md", "validated", 0.9)),
            ),
            (
                "self-reported metadata advantage",
                (("docs/verified.md", "active", 0.2), ("docs/guess.md", "validated", 0.99)),
            ),
        )
        for label, records in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                created = [
                    memory_manager.add_record(
                        "requirements",
                        f"Primary release path is {value}.",
                        memory_manager.build_card_metadata(
                            status=status,
                            confidence=confidence,
                            base={
                                "claim_key": "release.path",
                                "claim_value": value,
                                "trust": confidence,
                            },
                        ),
                        tmp,
                    )
                    for value, status, confidence in records
                ]

                report = memory_hygiene.reconcile_current_truth(tmp, claim_key="release.path")
                applied = memory_hygiene.hygiene_apply(tmp, safe=True, plan=report["plan"])
                proposal = report["proposals"][0]

                self.assertEqual(report["action"], "reconcile-current-truth")
                self.assertEqual(proposal["proposed_action"], "review_claim_conflict")
                self.assertFalse(proposal["safe_to_apply"])
                self.assertEqual(proposal["details"]["resolution"], "review_required")
                self.assertEqual(proposal["details"]["record_ids"], [record.id for record in created])
                self.assertNotIn("winner_id", proposal["details"])
                self.assertEqual(report["requires_confirmation"], [created[0].id])
                self.assertEqual(applied["applied_count"], 0)
                self.assertEqual(applied["unresolved_conflicts"], [proposal])
                self.assertEqual(applied["skipped_confirmation_ids"].count(created[0].id), 1)
                self.assertEqual(
                    [memory_manager.get_record(record.id, tmp).metadata["status"] for record in created],
                    [status for _value, status, _confidence in records],
                )

    def test_safe_hygiene_still_merges_duplicates_without_changing_single_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            claim = memory_manager.add_record(
                "requirements",
                "Primary release path is docs/verified.md.",
                memory_manager.build_card_metadata(
                    status="validated",
                    base={"claim_key": "release.path", "claim_value": "docs/verified.md"},
                ),
                tmp,
            )
            primary = memory_manager.add_record("architecture", "Workers use an event queue.", root=tmp)
            duplicate = memory_manager.add_record("architecture", "Workers use an event queue.", root=tmp)

            plan = memory_hygiene.hygiene_plan(tmp)
            applied = memory_hygiene.hygiene_apply(tmp, safe=True, plan=plan)

            self.assertFalse(any(item["proposed_action"] == "review_claim_conflict" for item in plan["proposals"]))
            self.assertTrue(
                any(
                    item["id"] == duplicate.id
                    and item["action"] == "merge"
                    and item["applied"]
                    for item in applied["applied"]
                )
            )
            self.assertEqual(memory_manager.get_record(primary.id, tmp).metadata.get("status", "active"), "active")
            self.assertEqual(memory_manager.get_record(duplicate.id, tmp).metadata["status"], "superseded")
            self.assertEqual(memory_manager.get_record(claim.id, tmp).metadata["status"], "validated")

    def test_command_failure_and_weak_preference_get_safe_hygiene_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            command = memory_manager.add_record(
                "commands",
                "Verified command: pytest tests. Validation failed on 2026-07-02.",
                memory_manager.build_card_metadata(status="active", source="skill", base={"validation_status": "failed"}),
                tmp,
            )
            preference = memory_manager.add_record(
                "preferences",
                "User prefers extra verbose release notes.",
                memory_manager.build_card_metadata(status="active", source="skill"),
                tmp,
            )

            plan = memory_hygiene.hygiene_plan(tmp)
            applied = memory_hygiene.hygiene_apply(tmp, safe=True, plan=plan)
            command_after = memory_manager.query("pytest tests validation", categories=["commands"], statuses=["stale"], root=tmp)
            preference_after = memory_manager.query("verbose release notes", categories=["preferences"], statuses=["needs_confirmation"], root=tmp)

            actions_by_id = {item["id"]: item["proposed_action"] for item in plan["proposals"] if item["id"] in {command.id, preference.id}}
            self.assertEqual(actions_by_id[command.id], "stale")
            self.assertEqual(actions_by_id[preference.id], "needs_confirmation")
            self.assertEqual(command_after["results"][0]["id"], command.id)
            self.assertEqual(preference_after["results"][0]["id"], preference.id)
            self.assertEqual(applied["action"], "hygiene-apply")


if __name__ == "__main__":
    unittest.main()
