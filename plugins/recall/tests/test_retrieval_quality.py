from __future__ import annotations

import tempfile
import unittest

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import memory_manager  # noqa: E402
import session_context  # noqa: E402


class RetrievalQualityTests(unittest.TestCase):
    def test_session_context_includes_validated_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_manager.add_record(
                "requirements",
                "Generated release notes must stay in docs/manual-release-notes.md.",
                memory_manager.build_card_metadata(
                    summary="Generated release notes must stay in docs/manual-release-notes.md.",
                    status="validated",
                    source="unit-test",
                ),
                root=tmp,
            )

            context = session_context.build_session_context(
                tmp,
                "What release notes requirement should I preserve?",
                8,
                exclude_categories=["commands"],
            )

            self.assertIn("Curated RECALL project memory", context)
            self.assertIn("docs/manual-release-notes.md", context)

    def test_structured_fields_beat_plain_keyword_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_manager.add_record(
                "tasks",
                "Release checklist mentions payload shape and command output.",
                memory_manager.build_card_metadata(status="active", source="unit-test"),
                root=tmp,
            )
            memory_manager.add_record(
                "requirements",
                "Stable contract memory.",
                memory_manager.build_card_metadata(
                    summary="Payload shape for command output must stay stable.",
                    details="Release automation depends on stable JSON fields.",
                    tags=["payload-shape", "command-output"],
                    source="unit-test",
                    status="active",
                    importance=1.0,
                ),
                root=tmp,
            )

            result = memory_manager.query("payload shape command output", root=tmp)

            self.assertEqual(result["results"][0]["category"], "requirements")

    def test_status_weighting_prefers_current_memory_for_broad_queries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_manager.add_record(
                "requirements",
                "Old CLI contract can emit raw command output.",
                memory_manager.build_card_metadata(
                    summary="Old CLI output contract.",
                    tags=["cli-contract"],
                    status="superseded",
                    importance=1.0,
                ),
                root=tmp,
            )
            memory_manager.add_record(
                "requirements",
                "Current CLI contract must emit compact JSON summaries.",
                memory_manager.build_card_metadata(
                    summary="Current CLI output contract.",
                    tags=["cli-contract"],
                    status="active",
                    importance=0.5,
                ),
                root=tmp,
            )

            result = memory_manager.query("CLI output contract", root=tmp)
            superseded = memory_manager.query("CLI output contract", statuses=["superseded"], root=tmp)

            self.assertIn("Current", result["results"][0]["content"])
            self.assertEqual(len(superseded["results"]), 1)
            self.assertIn("Old", superseded["results"][0]["content"])

    def test_durable_categories_outrank_session_summaries_for_startup_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_manager.add_record(
                "session_summaries",
                "Session discussed local-first runtime storage and hook payloads several times.",
                memory_manager.build_card_metadata(status="active", tags=["local-first", "hooks"], importance=0.4),
                root=tmp,
            )
            memory_manager.add_record(
                "constraints",
                "Runtime memory must stay inside the active project's .codex_memory directory.",
                memory_manager.build_card_metadata(
                    summary="Runtime memory is project-local.",
                    tags=["local-first", "runtime-storage"],
                    status="active",
                    importance=1.0,
                ),
                root=tmp,
            )

            result = memory_manager.query("local-first runtime storage", root=tmp)

            self.assertEqual(result["results"][0]["category"], "constraints")

    def test_failure_queries_surface_risks_and_debug_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_manager.add_record(
                "commands",
                "Run python -m unittest discover -s tests.",
                memory_manager.build_card_metadata(status="active", tags=["tests"]),
                root=tmp,
            )
            memory_manager.add_record(
                "risks",
                "Hook payload drift can break explicit RECALL context retrieval.",
                memory_manager.build_card_metadata(
                    summary="Hook payload drift can break explicit recall retrieval.",
                    tags=["hook-payload", "recall-retrieval", "failure"],
                    status="open",
                    importance=0.9,
                ),
                root=tmp,
            )
            memory_manager.add_record(
                "debug_history",
                "Explicit RECALL retrieval failed when the hook payload omitted cwd.",
                memory_manager.build_card_metadata(
                    summary="Missing cwd caused explicit RECALL retrieval failure.",
                    tags=["hook-payload", "recall-retrieval", "failure"],
                    status="active",
                    importance=0.8,
                ),
                root=tmp,
            )

            result = memory_manager.query("explicit RECALL hook payload failure", root=tmp)
            categories = [item["category"] for item in result["results"][:2]]

            self.assertIn("risks", categories)
            self.assertIn("debug_history", categories)

    def test_sorting_is_deterministic_for_equal_scores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = memory_manager.add_record(
                "commands",
                "Run deterministic command.",
                memory_manager.build_card_metadata(status="active", tags=["deterministic"]),
                root=tmp,
            )
            second = memory_manager.add_record(
                "commands",
                "Run deterministic command.",
                memory_manager.build_card_metadata(status="active", tags=["deterministic"]),
                root=tmp,
            )

            result = memory_manager.query("deterministic command", categories=["commands"], root=tmp)

            self.assertEqual([item["id"] for item in result["results"][:2]], [second.id, first.id])


if __name__ == "__main__":
    unittest.main()
