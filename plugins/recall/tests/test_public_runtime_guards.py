"""Public boundaries must enforce task scope and observed verification."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))
import config
import kimi_mcp_server as server
import memory_manager
import storage
from services import lifecycle_service


def call(name, root, **arguments):
    response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                              "params": {"name": name, "arguments": {"root": str(root), **arguments}}})
    if "error" in response:
        return response
    return json.loads(response["result"]["content"][0]["text"])


class PublicRuntimeGuards(unittest.TestCase):
    def test_public_batch_ingest_cannot_claim_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            command = [
                sys.executable,
                str(PLUGIN / "scripts/recall_skill.py"),
                "--root",
                tmp,
                "batch-ingest",
                "--stdin",
            ]
            payload = {
                "schema": "recall.batch_ingest.v1",
                "cards": [
                    {
                        "category": "requirements",
                        "content": "Release evidence must be observed.",
                        "metadata": {"status": "validated", "confidence": 1},
                    }
                ],
            }
            completed = subprocess.run(
                command,
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertEqual(json.loads(completed.stdout)["saved"], 1)
            record = next(storage.iter_records(tmp))
            self.assertEqual(record.metadata["status"], "active")
            self.assertEqual(record.metadata["verification_reason"], "observed_evidence_required")
            self.assertNotIn("validated_at", record.metadata)

    def test_conflict_resolution_rejects_bad_ids_before_any_backend_write(self):
        for backend in ("sqlite", "jsonl"):
            with self.subTest(backend=backend), tempfile.TemporaryDirectory() as tmp:
                cfg = config.default_config()
                cfg["backend"] = backend
                config.save_config(cfg, tmp)
                winner = memory_manager.add_record("requirements", "Current release format.", root=tmp)
                loser = memory_manager.add_record("requirements", "Older release format.", root=tmp)
                before = [(r.id, dict(r.metadata or {})) for r in storage.iter_records(tmp)]
                for selected, error in (([loser.id, 999999], KeyError), ([loser.id, winner.id], ValueError)):
                    with self.subTest(selected=selected), self.assertRaises(error):
                        lifecycle_service.resolve_conflict(winner.id, selected, tmp)
                    self.assertEqual([(r.id, dict(r.metadata or {})) for r in storage.iter_records(tmp)], before)

    def test_reviewed_plan_survives_mcp_and_cli_transport(self):
        for surface in ("mcp", "cli"):
            with self.subTest(surface=surface), tempfile.TemporaryDirectory() as tmp:
                for _ in range(2):
                    memory_manager.add_record("requirements", "Release checks must pass before tagging.",
                                              {"status": "active"}, tmp)
                if surface == "mcp":
                    plan = call("memory_hygiene", tmp, mode="plan", scan_limit=10, output_limit=10, action_limit=1)
                    result = call("memory_hygiene", tmp, mode="apply_safe", plan=plan)
                else:
                    saved = Path(tmp) / "reviewed-plan.json"
                    command = [sys.executable, str(PLUGIN / "scripts/recall_skill.py"), "--root", tmp]
                    planned = subprocess.run([*command, "hygiene-plan", "--scan-limit", "10", "--output-limit", "10",
                                              "--action-limit", "1", "--save-plan", str(saved)],
                                             capture_output=True, text=True, check=True)
                    self.assertEqual(json.loads(planned.stdout), json.loads(saved.read_text(encoding="utf-8")))
                    applied = subprocess.run([*command, "hygiene-apply", "--safe", "--plan-file", str(saved)],
                                             capture_output=True, text=True, check=True)
                    result = json.loads(applied.stdout)
                self.assertEqual(result["applied_count"], 1, result)
                records = list(storage.iter_records(tmp))
                self.assertEqual(len(records), 2)
                self.assertEqual(sum(record.metadata.get("status") == "superseded" for record in records), 1)

    def test_rootless_cli_failure_reports_decision_without_creating_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {key: value for key, value in os.environ.items() if key != "RECALL_PROJECT_ROOT"}
            result = subprocess.run([sys.executable, str(PLUGIN / "scripts/recall_skill.py"), "retrieve-memory", "history"],
                                    cwd=tmp, env=env, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn(payload["root_decision"]["status"], ("unresolved", "ambiguous"))
            self.assertFalse(Path(tmp, ".recall").exists())

    def test_exact_actual_tool_observation_can_validate_but_cannot_transfer(self):
        import observed_evidence
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "test_actual.py").write_text("import unittest\nclass Probe(unittest.TestCase):\n def test_sum(self): self.assertEqual(2+2,4)\n", encoding="utf-8")
            command = [sys.executable, "-m", "unittest", "discover", "-s", tmp]
            completed = subprocess.run(command, capture_output=True, text=True, check=True)
            response = {"exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
            command_text = subprocess.list2cmdline(command)
            content = observed_evidence.observed_content(command_text, response)
            event = {"event_id": "actual-test", "session_id": "actual-session", "turn_id": "actual-turn",
                     "signal": "test_pass", "category_hint": "commands", "command": command_text,
                     "details": content, "tool_response": response, "origin_provider": "kimi"}
            self.assertIsNotNone(observed_evidence.observe_tool_result(tmp, event))
            fields = {"status": "validated", "source_session": "actual-session", "source_turn": "actual-turn",
                      "evidence_ids": ["actual-test"]}
            saved = call("save_insight", tmp, category="commands", content=content, **fields)
            self.assertEqual(saved["metadata"]["status"], "validated")
            self.assertTrue(observed_evidence.has_observed_evidence(tmp, "commands", content, saved["metadata"]))
            claimed = call("save_insight", tmp, category="requirements", content="The whole system is production ready.", **fields)
            self.assertEqual(claimed["metadata"]["status"], "active")

    def test_claimed_validation_and_repeated_confirmation_stay_unverified(self):
        for backend in ("sqlite", "jsonl"):
            with self.subTest(backend=backend), tempfile.TemporaryDirectory() as tmp:
                cfg = config.default_config()
                cfg["backend"] = backend
                config.save_config(cfg, tmp)
                result = call("save_insight", tmp, category="requirements",
                              content="Release notes must live in docs/accepted.md.", status="validated", confidence=1)
                self.assertEqual(result["metadata"]["status"], "active")
                for session in ("invented-A", "invented-B"):
                    memory_manager.confirm_record(result["id"], tmp, source_session=session)
                self.assertNotEqual(storage.get_record(result["id"], tmp).metadata["status"], "validated")
                assigned = call("update_memory", tmp, op="update", id=result["id"], status="validated")
                self.assertEqual(assigned["record"]["status"], "active")

    def test_promote_without_observation_cannot_validate(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = memory_manager.add_record("requirements", "Release notes belong in docs/accepted.md.", {"status": "active"}, tmp)
            with self.assertRaisesRegex(ValueError, "observed evidence"):
                lifecycle_service.promote(record.id, tmp)
            self.assertEqual(storage.get_record(record.id, tmp).metadata["status"], "active")

    def test_mcp_preserves_opaque_claim_whitespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = call("save_insight", tmp, category="requirements", content="Artifact path has meaningful edge spaces.",
                          claim_key="artifact.path", claim_value="  docs/accepted.md  ")
            self.assertEqual(result["metadata"]["claim_value"], "  docs/accepted.md  ")
            edited = call("update_memory", tmp, op="update", id=result["id"],
                          claim_key="artifact.path", claim_value=" docs/accepted.md ")
            self.assertEqual(edited["record"]["metadata"]["claim_value"], " docs/accepted.md ")

    def test_no_memory_blocks_persistent_mcp_before_canonical_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            config.activate_project(tmp, activated_by="test")
            memory_manager.add_record("requirements", "Private project marker for scope probe.", root=tmp)
            command = [sys.executable, str(PLUGIN / "hooks/scripts/prompt_inspector.py"), "--root", tmp]
            payload = {"hook_event_name": "UserPromptSubmit", "cwd": tmp, "session_id": "scope-session",
                       "turn_id": "disabled-turn", "prompt": "Do not use memory for this task. Return READY."}
            result = subprocess.run(command, input=json.dumps(payload), text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            actions = [("retrieve_memory", {"query_text": "private"}), ("context_packet", {"query_text": "private"}),
                       ("review_memory", {}), ("save_insight", {"category": "requirements", "content": "Must not persist."}),
                       ("initialize_project", {}), ("memory_hygiene", {"mode": "scan"})]
            with mock.patch.object(storage, "iter_records", side_effect=AssertionError("canonical read")), \
                 mock.patch.object(storage, "write_transaction", side_effect=AssertionError("canonical transaction")):
                for name, arguments in actions:
                    with self.subTest(name=name):
                        response = call(name, tmp, **arguments)
                        self.assertEqual(response.get("memory_action"), "disabled", response)
                import runtime_guard
                with self.assertRaises(runtime_guard.MemoryDisabledError):
                    memory_manager.add_record_if_useful("requirements", "Never write this fact.", root=tmp)
            cli = subprocess.run([sys.executable, str(PLUGIN / "scripts/recall_skill.py"), "--root", tmp,
                                  "retrieve-memory", "private"], text=True, capture_output=True, check=False)
            self.assertEqual(json.loads(cli.stdout).get("memory_action"), "disabled")
            payload.update(turn_id="normal-turn", prompt="Use project history to find the private project marker.")
            later = subprocess.run(command, input=json.dumps(payload), text=True, capture_output=True, check=False)
            self.assertEqual(later.returncode, 0, later.stderr)
            self.assertIn("results", call("retrieve_memory", tmp, query_text="private project marker"))


if __name__ == "__main__":
    unittest.main()
