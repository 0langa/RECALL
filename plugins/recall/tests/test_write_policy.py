from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import memory_manager  # noqa: E402
import write_policy  # noqa: E402
import config  # noqa: E402
import storage  # noqa: E402


class WritePolicyTests(unittest.TestCase):
    def test_each_keyed_confirmation_is_applied_once(self) -> None:
        for backend in ("sqlite", "jsonl"):
            with self.subTest(backend=backend), tempfile.TemporaryDirectory() as tmp:
                cfg = config.load_config(tmp)
                cfg["backend"] = backend
                config.save_config(cfg, tmp)
                content = "The canonical store stays on local disk."
                original = memory_manager.add_record_if_useful("architecture", content, {"idempotency_key": "initial-save"}, tmp)
                keys = ["confirm-retry-1", "confirm-retry-2"]
                for count, key in enumerate(keys, start=1):
                    result = memory_manager.add_record_if_useful("architecture", content, {"idempotency_key": key}, tmp)
                    self.assertEqual(result["action"], "updated_existing")
                    self.assertEqual(result["record"].metadata["confirmed_count"], count)
                for key in ["initial-save", *keys, *reversed(keys)]:
                    before = storage.get_record(original["record"].id, tmp)
                    replay = memory_manager.add_record_if_useful("architecture", content, {"idempotency_key": key}, tmp)
                    self.assertEqual(replay["reason"], "idempotent_replay")
                    self.assertEqual(replay["record"], before)
                    self.assertEqual(storage.find_by_idempotency_key(key, tmp).id, before.id)
                    self.assertEqual(storage.get_record(before.id, tmp), before)
                self.assertEqual(len(list(storage.iter_records(tmp))), 1)

    def test_new_retry_key_on_unkeyed_preference_update_is_preserved(self) -> None:
        for backend in ("sqlite", "jsonl"):
            with self.subTest(backend=backend), tempfile.TemporaryDirectory() as tmp:
                cfg = config.load_config(tmp)
                cfg["backend"] = backend
                config.save_config(cfg, tmp)
                metadata = {"preference_key": "runner", "preference_evidence_type": "approved_plan", "decision_id": "event-1"}
                original = memory_manager.add_record_if_useful("preferences", "Use the isolated test runner.", metadata, tmp)
                for event, key in (("event-2", "retry-a"), ("event-3", "retry-b")):
                    first = memory_manager.add_record_if_useful(
                        "preferences", "Use the isolated test runner.", {**metadata, "decision_id": event, "idempotency_key": f" {key} "}, tmp,
                    )
                    self.assertEqual(first["action"], "updated_existing")
                before = storage.get_record(original["record"].id, tmp)
                for key in ("retry-a", "retry-b"):
                    replay = memory_manager.add_record_if_useful(
                        "preferences", "Use the isolated test runner.", {**metadata, "decision_id": "must-not-apply", "idempotency_key": key}, tmp,
                    )
                    self.assertEqual(replay["reason"], "idempotent_replay")
                    self.assertEqual(replay["record"], before)
                self.assertEqual(before.metadata["supporting_event_ids"], ["event-1", "event-2", "event-3"])
                self.assertEqual(storage.get_record(before.id, tmp), before)

    def test_confirmation_does_not_change_exact_save_identity(self) -> None:
        for backend in ("sqlite", "jsonl"):
            with tempfile.TemporaryDirectory() as tmp:
                cfg = config.load_config(tmp)
                cfg["backend"] = backend
                config.save_config(cfg, tmp)
                results = [memory_manager.add_record_if_useful(
                    "architecture", "The project stores canonical facts on local disk.",
                    memory_manager.build_card_metadata(status="active"), tmp,
                ) for _ in range(5)]
                self.assertEqual({result["record"].id for result in results}, {results[0]["record"].id})
                self.assertEqual(len(list(memory_manager.iter_records(tmp))), 1)
                self.assertEqual(results[-1]["record"].metadata["confirmed_count"], 4)

    def test_preference_evidence_respects_scope(self) -> None:
        for backend in ("sqlite", "jsonl"):
            with tempfile.TemporaryDirectory() as tmp:
                cfg = config.load_config(tmp)
                cfg["backend"] = backend
                config.save_config(cfg, tmp)
                ids = []
                for provider, scope in (("all", "project"), ("codex", "project"), ("codex", "user")):
                    metadata = {"preference_key": "test-runner", "preference_evidence_type": "approved_plan",
                                "decision_id": "event-1", "applies_to_provider": provider, "preference_scope": scope}
                    saved = memory_manager.add_record_if_useful("preferences", "Run the isolated test runner.", metadata, tmp)
                    ids.append(saved["record"].id)
                    updated = memory_manager.add_record_if_useful(
                        "preferences", "Run the isolated test runner.", {**metadata, "decision_id": "event-2"}, tmp,
                    )
                    self.assertEqual(updated["record"].id, saved["record"].id)
                    self.assertEqual(updated["record"].metadata["supporting_event_ids"], ["event-1", "event-2"])
                self.assertEqual(len(set(ids)), 3)
                self.assertEqual(len(list(memory_manager.iter_records(tmp))), 3)

    def test_low_signal_listing_command_is_ignored(self) -> None:
        decision = write_policy.classify_write(
            "commands",
            "Tool: Bash\nCommand: Get-ChildItem -Force\nResult: completed\nexit_code: 0",
            {"source": "post_tool_use", "command": "Get-ChildItem -Force"},
        )

        self.assertEqual(decision.action, "ignore")
        self.assertEqual(decision.reason, "low_signal_command")

    def test_exact_duplicate_updates_existing_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            metadata = memory_manager.build_card_metadata(
                source="post_tool_use",
                status="active",
                base={
                    "command": "python -m unittest",
                    "tool_name": "Bash",
                    "turn_id": "turn-1",
                    "auto_capture_policy": "test_result",
                },
            )
            first = memory_manager.add_record_if_useful("commands", "Command: python -m unittest\nOK", metadata, tmp)
            second = memory_manager.add_record_if_useful("commands", "Command: python -m unittest\nOK", metadata, tmp)
            result = memory_manager.query("python unittest", categories=["commands"], root=tmp)

            self.assertEqual(second["action"], "updated_existing")
            self.assertEqual(second["duplicate_id"], first["record"].id)
            self.assertEqual(len(result["results"]), 1)
            self.assertIn("last_confirmed", result["results"][0]["metadata"])

    def test_explicit_supersession_cue_marks_old_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = memory_manager.add_record(
                "decisions",
                "Use raw transcripts for memory.",
                memory_manager.build_card_metadata(status="active"),
                root=tmp,
            )
            new = memory_manager.add_record_if_useful(
                "decisions",
                f"Correction to memory #{old.id}: use structured cards.",
                memory_manager.build_card_metadata(
                    source="stop",
                    status="active",
                    base={"auto_capture_policy": "project_checkpoint"},
                ),
                tmp,
            )
            fetched_old = memory_manager.get_record(old.id, tmp)

            self.assertEqual(new["action"], "saved")
            self.assertEqual(fetched_old.metadata["status"], "superseded")
            self.assertEqual(fetched_old.metadata["superseded_by"], new["record"].id)


if __name__ == "__main__":
    unittest.main()
