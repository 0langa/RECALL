from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import config as recall_config  # noqa: E402
import memory_manager  # noqa: E402
import project_context  # noqa: E402
import retrieval  # noqa: E402
import turn_buffer  # noqa: E402
from finalizer_prompt import build_finalizer_prompt  # noqa: E402
from services.finalizer_service import apply_finalizer_batch  # noqa: E402


def batch(session: str, turn: str, operations: list[dict]) -> dict:
    return {
        "schema": "recall.finalizer_batch.v1",
        "session_id": session,
        "turn_id": turn,
        "operations": operations,
    }


def card(content: str, *, category: str = "requirements", explicit: bool = False) -> dict:
    return {
        "category": category,
        "content": content,
        "summary": content,
        "details": content,
        "tags": ["hardening-test"],
        "explicit_user_evidence": explicit,
        "evidence_ids": ["event-1"],
    }


class ReleaseHardeningTests(unittest.TestCase):
    def test_tracked_files_do_not_expose_private_windows_identity(self) -> None:
        repo = ROOT.parents[1]
        private_name = "Ju" + "lius"
        forbidden = (
            private_name.casefold(),
            f"c:/users/{private_name}".casefold(),
            f"c:\\users\\{private_name}".casefold(),
        )
        tracked = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=repo,
            check=True,
            capture_output=True,
        ).stdout.split(b"\0")

        leaks: list[str] = []
        for raw_path in tracked:
            if not raw_path:
                continue
            relative = raw_path.decode("utf-8")
            data = (repo / relative).read_bytes()
            if b"\0" in data:
                continue
            text = data.decode("utf-8", errors="replace").casefold()
            if any(value in text for value in forbidden):
                leaks.append(relative)

        self.assertEqual(leaks, [])

    def test_unrecognized_directory_resolves_to_no_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(project_context.resolve_project_root(tmp))
            self.assertFalse((Path(tmp) / ".codex_memory").exists())

    def test_manifest_project_and_nested_directory_resolve_to_one_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0.1.0'\n", encoding="utf-8")
            nested = root / "src" / "pkg"
            nested.mkdir(parents=True)
            self.assertEqual(project_context.resolve_project_root(nested), root.resolve())

    def test_activation_persists_and_deactivation_preserves_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = recall_config.activate_project(tmp, activated_by="test")
            self.assertTrue(cfg["activation"]["enabled"])
            self.assertTrue(recall_config.project_is_active(tmp))
            memory_manager.add_record("requirements", "Keep local storage.", root=tmp)
            recall_config.deactivate_project(tmp)
            self.assertFalse(recall_config.project_is_active(tmp))
            self.assertEqual(len(list(memory_manager.iter_records(tmp))), 1)

    def test_finalizer_batch_is_atomic_and_replay_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recall_config.activate_project(tmp, activated_by="test")
            invalid = batch("s1", "t1", [
                {"op": "save", "card": card("Atomic requirement.")},
                {"op": "confirm", "id": 9999},
            ])
            with self.assertRaises(KeyError):
                apply_finalizer_batch(invalid, tmp)
            self.assertEqual(list(memory_manager.iter_records(tmp)), [])

            valid = batch("s1", "t1", [{"op": "save", "card": card("Atomic requirement.")}])
            first = apply_finalizer_batch(valid, tmp)
            replay = apply_finalizer_batch(valid, tmp)
            self.assertEqual(first["action"], "applied")
            self.assertEqual(replay["reason"], "idempotent_replay")
            self.assertEqual(len(list(memory_manager.iter_records(tmp))), 1)

    def test_independent_sessions_validate_automatic_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recall_config.activate_project(tmp, activated_by="test")
            content = "The release requires source and installed smoke checks."
            apply_finalizer_batch(batch("session-a", "turn-a", [{"op": "save", "card": card(content)}]), tmp)
            first = list(memory_manager.iter_records(tmp))[0]
            self.assertEqual(first.metadata["status"], "hypothesis")
            apply_finalizer_batch(batch("session-b", "turn-b", [{"op": "save", "card": card(content)}]), tmp)
            confirmed = memory_manager.get_record(first.id, tmp)
            self.assertEqual(confirmed.metadata["status"], "validated")
            self.assertEqual(set(confirmed.metadata["confirmation_sessions"]), {"session-a", "session-b"})

    def test_explicit_requirement_validates_immediately_and_secrets_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recall_config.activate_project(tmp, activated_by="test")
            result = apply_finalizer_batch(
                batch("session-a", "turn-a", [{"op": "save", "card": card("Never upload project memory.", explicit=True)}]),
                tmp,
            )
            record = memory_manager.get_record(result["operations"][0]["id"], tmp)
            self.assertEqual(record.metadata["status"], "validated")
            with self.assertRaisesRegex(ValueError, "secret-like"):
                apply_finalizer_batch(
                    batch("session-a", "turn-secret", [{"op": "save", "card": card("token=dummy-secret-value")}]),
                    tmp,
                )

    def test_finalizer_ignores_raw_prompt_plan_cards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recall_config.activate_project(tmp, activated_by="test")
            raw_prompt = (
                "PLEASE IMPLEMENT THIS PLAN: # Scalpel Release-Ready Improvements 6-10\n"
                "## Summary\n"
                "Implement the following release plan exactly as written.\n"
                "## Key Changes\n"
                "- Large-file strategy with read_chunk and clear max-size errors.\n"
                "- Binary/encoding guard.\n"
                "- Operation journal.\n"
                "- Better eval harness.\n"
                "- Tool namespacing.\n"
                + "More implementation detail. " * 30
            )
            result = apply_finalizer_batch(
                batch(
                    "session-a",
                    "turn-plan",
                    [
                        {
                            "op": "save",
                            "card": {
                                "category": "decisions",
                                "content": raw_prompt,
                                "summary": raw_prompt,
                                "details": raw_prompt,
                                "tags": ["user-prompt", "correction"],
                                "explicit_user_evidence": True,
                            },
                        }
                    ],
                ),
                tmp,
            )
            self.assertEqual(result["operations"][0]["action"], "ignored")
            self.assertEqual(result["operations"][0]["reason"], "raw_prompt_transcript")
            self.assertEqual(list(memory_manager.iter_records(tmp)), [])

    def test_finalizer_keeps_distilled_plan_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recall_config.activate_project(tmp, activated_by="test")
            result = apply_finalizer_batch(
                batch(
                    "session-a",
                    "turn-distilled",
                    [
                        {
                            "op": "save",
                            "card": {
                                "category": "project_state",
                                "content": "Scalpel release-ready improvements 6-10 are implemented and validated.",
                                "summary": "Scalpel release-ready improvements 6-10 implemented.",
                                "details": "Validation passed via lint, typecheck, tests, build, and MCP smoke.",
                                "tags": ["scalpel", "release-ready", "validation"],
                                "explicit_user_evidence": False,
                            },
                        }
                    ],
                ),
                tmp,
            )
            self.assertEqual(result["operations"][0]["action"], "saved")
            self.assertEqual(len(list(memory_manager.iter_records(tmp))), 1)

    def test_finalizer_ignores_raw_tool_wrapper_cards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recall_config.activate_project(tmp, activated_by="test")
            raw_wrapper = (
                'Tool: Bash\n'
                'Command: uv run pytest -q --tb=short\n'
                '{"code":"internal","message":"error: Failed to spawn: `pytest`\\n'
                '  Caused by: program not found\\nCommand failed with exit code: 2.",'
                '"retryable":false}\n'
                'exit_code: 2'
            )
            result = apply_finalizer_batch(
                batch(
                    "session-a",
                    "turn-wrapper",
                    [
                        {
                            "op": "save",
                            "card": {
                                "category": "debug_history",
                                "content": raw_wrapper,
                                "summary": raw_wrapper[:220],
                                "details": raw_wrapper,
                                "tags": ["tool-use", "bash", "failure", "tests"],
                                "explicit_user_evidence": False,
                            },
                        }
                    ],
                ),
                tmp,
            )
            self.assertEqual(result["operations"][0]["action"], "ignored")
            self.assertEqual(result["operations"][0]["reason"], "raw_tool_wrapper")
            self.assertEqual(list(memory_manager.iter_records(tmp)), [])

    def test_successful_quiet_finalization_removes_turn_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recall_config.activate_project(tmp, activated_by="test")
            turn_buffer.mark_active(tmp, "session", "turn", "prompt")
            turn_buffer.append_event(tmp, "session", "turn", {"durable_candidate": True, "signal": "requirement", "summary": "Keep it local."})
            apply_finalizer_batch(batch("session", "turn", []), tmp)
            self.assertFalse(turn_buffer.turn_events_path(tmp, "session", "turn").exists())
            self.assertFalse(turn_buffer.activation_path(tmp, "session", "turn").exists())

    def test_relevance_gate_meets_precision_and_recall_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixtures = [
                ("architecture", "RECALL stores project memory in SQLite with FTS5 and a local vector index."),
                ("requirements", "Runtime memory must remain inside the project .recall directory, or an existing legacy .codex_memory store."),
                ("risks", "Hook payload drift can break prompt retrieval and tool evidence buffering."),
                ("commands", "Run python -m unittest discover -s tests to validate the plugin."),
                ("decisions", "PostToolUse buffers evidence and Stop requests one atomic semantic finalizer batch."),
            ]
            for category, content in fixtures:
                memory_manager.add_record(
                    category,
                    content,
                    memory_manager.build_card_metadata(summary=content, source="calibration", status="active"),
                    tmp,
                )
            memory_manager.add_record(
                "requirements",
                "Generated release notes must stay in docs/manual-release-notes.md.",
                memory_manager.build_card_metadata(
                    summary="Generated release notes must stay in docs/manual-release-notes.md.",
                    source="calibration",
                    status="validated",
                ),
                tmp,
            )
            positives = [
                "How does RECALL store project memory?",
                "Where must runtime memory be stored?",
                "What risk can break hook retrieval?",
                "How do I run the plugin tests?",
                "What happens after PostToolUse and Stop?",
                "What release notes requirement should I preserve?",
                "Without running commands, answer from any automatically provided project memory: what release notes requirement should I preserve?",
            ]
            negatives = [
                "Write a poem about rain.",
                "What is the capital of France?",
                "Plan a birthday dinner.",
                "Explain photosynthesis.",
                "Draft a gym routine.",
                "Recommend a movie.",
                "Help me learn guitar.",
                "Translate hello to Spanish.",
                "Compare coffee beans.",
                "Tell me a joke.",
            ]
            true_positive = sum(retrieval.assess_relevance(prompt, root=tmp, exclude_categories=[])["relevant"] for prompt in positives)
            false_positive = sum(retrieval.assess_relevance(prompt, root=tmp, exclude_categories=[])["relevant"] for prompt in negatives)
            recall = true_positive / len(positives)
            precision = true_positive / max(1, true_positive + false_positive)
            self.assertGreaterEqual(recall, 0.85)
            self.assertGreaterEqual(precision, 0.95)

    def test_finalizer_prompt_does_not_inline_large_tool_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            patch = "*** Begin Patch\n" + "\n".join(f"+line {i}" for i in range(300)) + "\n*** End Patch"
            events = [
                {
                    "durable_candidate": True,
                    "signal": "file_patch",
                    "summary": "Edited file(s): C:\\Users\\ExampleUser\\source\\repos\\RECALL\\plugins\\recall\\scripts\\turn_buffer.py, C:\\Users\\ExampleUser\\source\\repos\\RECALL\\plugins\\recall\\scripts\\finalizer_prompt.py",
                    "details": "Tool: apply_patch\nFiles: README.md\nResult: success",
                    "command": patch,
                    "category_hint": "commands",
                    "record_kind": "file_edit",
                    "tags": ["tool-use", "apply_patch", "file-edit"],
                }
            ]
            packet = turn_buffer.create_finalizer_request(
                tmp,
                session_id="session",
                turn_id="turn",
                cwd=tmp,
                plugin_root=tmp,
                adapter="recall_skill.py",
                transcript_path=None,
                last_assistant_message="Finished.",
                events=events,
            )
            prompt = build_finalizer_prompt(str(packet), packet=json.loads(packet.read_text(encoding="utf-8")))
            self.assertLess(len(prompt), 1400)
            self.assertNotIn("*** Begin Patch", prompt)
            self.assertNotIn("+line 299", prompt)
            self.assertNotIn("C:\\Users\\ExampleUser", prompt)
            self.assertNotIn("turn_buffer.py", prompt)
            self.assertIn("signal_counts", prompt)


if __name__ == "__main__":
    unittest.main()
