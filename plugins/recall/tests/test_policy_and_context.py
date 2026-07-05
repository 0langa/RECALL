from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import memory_manager  # noqa: E402
import capture_policy  # noqa: E402
from models import ContextPacketRequest  # noqa: E402
from services.context_service import build_context_packet  # noqa: E402


class PolicyAndContextTests(unittest.TestCase):
    def test_prompt_memory_text_strips_plugin_mentions_and_activation_lead_in(self) -> None:
        prompt = (
            "Use [@recall](plugin://recall@recall-local) for this project. "
            "We must keep generated release notes under docs/manual-release-notes.md."
        )
        self.assertEqual(
            capture_policy.normalize_prompt_memory_text(prompt),
            "We must keep generated release notes under docs/manual-release-notes.md",
        )
        event = capture_policy.classify_prompt_event(prompt)
        self.assertIsNotNone(event)
        self.assertEqual(event["category_hint"], "requirements")
        self.assertNotIn("[](-local)", event["summary"])
        self.assertNotIn("Use RECALL", event["summary"])

    def test_transient_command_prompt_is_not_project_requirement(self) -> None:
        prompt = (
            "@recall Run exactly this shell command: uv run pytest -q --tb=short . "
            "Use shell/Bash only for that command. Do not call RECALL MCP save tools. "
            "After the command, reply with a one-line summary."
        )
        self.assertIsNone(capture_policy.classify_prompt_event(prompt))

    def test_execution_only_prompts_suppress_auto_retrieval(self) -> None:
        self.assertTrue(capture_policy.suppress_auto_retrieval("Run the integration suite."))
        self.assertTrue(capture_policy.suppress_auto_retrieval("Run the unit tests for the footer."))
        self.assertTrue(capture_policy.suppress_auto_retrieval("Ok apply the jitter fix and rerun."))

    def test_questions_and_release_prompts_do_not_suppress_auto_retrieval(self) -> None:
        self.assertFalse(
            capture_policy.suppress_auto_retrieval(
                "Start implementing the report footer; check what requirements exist for report generation output."
            )
        )
        self.assertFalse(capture_policy.suppress_auto_retrieval("Run the release build."))
        self.assertFalse(capture_policy.suppress_auto_retrieval("What was the accepted compression default?"))

    def test_replayed_idempotency_key_does_not_create_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            metadata = memory_manager.build_card_metadata(
                source="post_tool_use",
                base={"auto_capture_policy": "test_result", "idempotency_key": "event-123"},
            )
            first = memory_manager.add_record_if_useful("commands", "pytest passed", metadata, tmp)
            second = memory_manager.add_record_if_useful("commands", "different delivery text", metadata, tmp)
            self.assertEqual(first["action"], "saved")
            self.assertEqual(second["action"], "ignored")
            self.assertEqual(second["reason"], "idempotent_replay")
            self.assertEqual(len(list(memory_manager.iter_records(tmp))), 1)

    def test_preference_requires_explicit_declaration_or_two_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = memory_manager.add_record_if_useful(
                "preferences",
                "Prefer compact status updates.",
                {"preference_key": "status_style", "preference_evidence_type": "accepted_edit", "decision_id": "d1"},
                tmp,
            )
            second = memory_manager.add_record_if_useful(
                "preferences",
                "Prefer compact status updates.",
                {"preference_key": "status_style", "preference_evidence_type": "adjusted_edit", "decision_id": "d2"},
                tmp,
            )
            self.assertEqual(first["record"].metadata["status"], "hypothesis")
            self.assertEqual(second["record"].metadata["status"], "active")

    def test_one_task_constraint_is_not_promoted_to_preference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = memory_manager.add_record_if_useful(
                "preferences",
                "Use terse output for this task.",
                {"preference_key": "output_style", "preference_evidence_type": "one_task_constraint"},
                tmp,
            )
            self.assertEqual(result["action"], "ignored")
            self.assertEqual(result["reason"], "non_durable_preference_evidence")

    def test_context_packet_never_exceeds_budget_and_reports_omissions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for index in range(20):
                memory_manager.add_record(
                    "architecture" if index % 2 else "decisions",
                    f"Memory {index} " + ("important context " * 20),
                    memory_manager.build_card_metadata(
                        summary=f"Important memory {index}",
                        source=f"source-{index % 4}",
                        status="validated" if index < 4 else "active",
                        importance=1.0,
                    ),
                    tmp,
                )
            packet = build_context_packet(ContextPacketRequest("important context", token_budget=120, root=tmp))
            payload = packet.to_dict()
            self.assertLessEqual(payload["estimated_tokens"], 120)
            self.assertGreater(payload["omitted_count"], 0)
            self.assertTrue(payload["cards"])
            self.assertIn("score_components", payload["cards"][0])


if __name__ == "__main__":
    unittest.main()
