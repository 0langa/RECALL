"""Turn policy, observation provenance and real UTF-8 hook probes (U2)."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "hooks" / "scripts"))
import capture_policy
import config as recall_config
from hook_io import normalize_hook_event
import observed_evidence
import storage
import turn_buffer
import turn_policy
from services.finalizer_service import apply_finalizer_batch
from tests.test_hooks import run_hook


class RuntimeInterlockTests(unittest.TestCase):
    def test_first_no_memory_prompt_never_reads_records_or_captures_text(self):
        for provider in ("codex", "claude", "kimi"):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as tmp:
                recall_config.activate_project(tmp)
                recall_config.set_capture_mode("standard", tmp)
                payload = {"cwd": tmp, "provider": provider, "session_id": "private"}
                text = "Do not use memory for this task. PRIVATE-UNICODE-秘密-Ä. The project must use SQLite."
                self.assertFalse(turn_policy.policy_status(tmp)["scope_known"])
                with patch("retrieval.assess_relevance", side_effect=AssertionError("memory read")), patch("storage.iter_records", side_effect=AssertionError("memory read")):
                    output = run_hook("prompt_inspector.py", {**payload, "prompt": text})
                    self.assertEqual(output["memory_action"], "disabled")
                    self.assertNotIn("hookSpecificOutput", output)
                    run_hook("post_tool_use.py", {**payload, "tool_name": "Bash", "tool_input": {"command": "python -m pytest"}, "tool_response": {"exit_code": 0, "stdout": "1 passed 秘密"}})
                    run_hook("pre_compact.py", {**payload, "summary": text})
                    run_hook("stop.py", {**payload, "last_assistant_message": text})
                for path in recall_config.memory_dir(tmp).rglob("*"):
                    if path.is_file():
                        self.assertNotIn("PRIVATE-UNICODE", path.read_bytes().decode("utf-8", errors="ignore"))
                self.assertEqual(list(storage.iter_records(tmp)), [])
                normal = run_hook("prompt_inspector.py", {**payload, "prompt": "The project must keep release notes in docs/accepted.md."})
                self.assertNotIn("memory_action", normal)
                run_hook("stop.py", payload)
                records = list(storage.iter_records(tmp))
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0].metadata["status"], "active")

    def test_missing_ids_share_one_turn_then_rotate_and_old_id_cannot_bypass(self):
        for provider in ("codex", "claude", "kimi"):
            with tempfile.TemporaryDirectory() as tmp:
                kwargs = {"provider": provider, "fallback_root": tmp}
                first = normalize_hook_event({"prompt": "normal"}, fallback_event="UserPromptSubmit", **kwargs)
                tool = normalize_hook_event({}, fallback_event="PostToolUse", **kwargs)
                stop = normalize_hook_event({}, fallback_event="Stop", **kwargs)
                self.assertTrue(first.turn_id)
                self.assertNotEqual(first.turn_id, "turn")
                self.assertEqual((first.session_id, first.turn_id), (tool.session_id, tool.turn_id))
                self.assertEqual(first.turn_id, stop.turn_id)
                second = normalize_hook_event({"prompt": "No memory for this turn."}, fallback_event="UserPromptSubmit", **kwargs)
                self.assertNotEqual(first.turn_id, second.turn_id)
                self.assertTrue(turn_policy.policy_status(tmp, first.session_id, first.turn_id)["disabled"])

    def test_missing_identity_expires_without_rejoining_old_turn(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = normalize_hook_event({"prompt": "normal"}, fallback_event="UserPromptSubmit", fallback_root=tmp)
            with patch("turn_policy.time.time", return_value=__import__("time").time() + 8 * 86400):
                later = normalize_hook_event({}, fallback_event="PostToolUse", fallback_root=tmp)
            self.assertNotEqual(first.turn_id, later.turn_id)

    def test_closed_no_memory_turn_yields_to_new_normal_scope_but_not_active_disabled_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = normalize_hook_event(
                {"prompt": "Do not read or write memory.", "session_id": "old", "turn_id": "one"},
                fallback_event="UserPromptSubmit", fallback_root=tmp,
            )
            turn_policy.finish_turn(tmp, old.session_id, old.turn_id)
            self.assertTrue(turn_policy.policy_status(tmp)["disabled"])

            newer = normalize_hook_event(
                {"prompt": "Keep working on the release.", "session_id": "new", "turn_id": "two"},
                fallback_event="UserPromptSubmit", fallback_root=tmp,
            )
            contextless = turn_policy.policy_status(tmp)
            self.assertFalse(contextless["disabled"])
            self.assertEqual(contextless["session_id"], newer.session_id)
            self.assertTrue(turn_policy.policy_status(tmp, old.session_id, old.turn_id)["disabled"])

            turn_policy.finish_turn(tmp, newer.session_id, newer.turn_id)
            after_normal_stop = turn_policy.policy_status(tmp)
            self.assertFalse(after_normal_stop["disabled"])
            self.assertEqual((after_normal_stop["session_id"], after_normal_stop["turn_id"]),
                             (newer.session_id, newer.turn_id))
            self.assertTrue(after_normal_stop["closed"])

            normalize_hook_event(
                {"prompt": "No memory for this task.", "session_id": "active-disabled", "turn_id": "three"},
                fallback_event="UserPromptSubmit", fallback_root=tmp,
            )
            self.assertTrue(turn_policy.policy_status(tmp)["disabled"])

    def test_same_session_late_private_event_stays_blocked_after_normal_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            recall_config.activate_project(tmp)
            recall_config.set_capture_mode("standard", tmp)
            base = {"cwd": tmp, "session_id": "same"}
            run_hook("prompt_inspector.py", {**base, "turn_id": "private", "prompt": "No memory for this turn."})
            run_hook("stop.py", {**base, "turn_id": "private"})
            run_hook("prompt_inspector.py", {**base, "turn_id": "normal", "prompt": "Continue normal work."})
            self.assertTrue(turn_policy.policy_status(tmp, "same", "private")["disabled"])
            late = run_hook(
                "post_tool_use.py",
                {
                    **base, "turn_id": "private", "tool_name": "Bash",
                    "tool_input": {"command": "python -m pytest"},
                    "tool_response": {"exit_code": 1, "stdout": "FAILED PRIVATE_LATE_OUTPUT"},
                },
            )
            self.assertEqual(late["action"], "disabled")
            for path in recall_config.memory_dir(tmp).rglob("*"):
                if path.is_file():
                    self.assertNotIn("PRIVATE_LATE_OUTPUT", path.read_text(encoding="utf-8", errors="ignore"))

    def test_no_memory_finalizer_rejects_before_store_initialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            event = normalize_hook_event({"prompt": "Do not read or write memory."}, fallback_event="UserPromptSubmit", fallback_root=tmp)
            batch = {"schema": "recall.finalizer_batch.v1", "session_id": event.session_id, "turn_id": event.turn_id, "operations": []}
            with patch("storage.init_store", side_effect=AssertionError("store write")):
                self.assertEqual(apply_finalizer_batch(batch, tmp)["action"], "disabled")

    def test_observed_success_is_bound_to_exact_result_and_factual_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "test_observation.py").write_text("import unittest\nclass Probe(unittest.TestCase):\n def test_sum(self): self.assertEqual(2+2,4)\n", encoding="utf-8")
            command = [sys.executable, "-m", "unittest", "discover", "-s", tmp]
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            command_text = subprocess.list2cmdline(command)
            response = {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
            event = {"event_id": "real-result", "session_id": "s", "turn_id": "t", "signal": "test_pass", "category_hint": "commands", "command": command_text, "details": observed_evidence.observed_content(command_text, response), "tool_response": response}
            receipt = observed_evidence.observe_tool_result(tmp, event)
            self.assertIsNotNone(receipt)
            metadata = {"observed_evidence": receipt}
            self.assertTrue(observed_evidence.has_observed_evidence(tmp, "commands", event["details"], metadata))
            self.assertTrue(observed_evidence.has_observed_evidence(tmp, "commands", event["details"], {**metadata, "tags": ["new"]}))
            self.assertFalse(observed_evidence.has_observed_evidence(tmp, "commands", "The project is production ready.", metadata))
            self.assertFalse(observed_evidence.has_observed_evidence(tmp, "commands", event["details"], {**metadata, "claim_value": "different"}))
            self.assertIsNone(observed_evidence.observe_tool_result(tmp, {**event, "tool_response": {}}))
            self.assertIsNone(observed_evidence.observe_tool_result(tmp, {**event, "command": "git status"}))
            forged = {"status": "validated", "tool_success": True, "observed_at": "2026-01-01", "confidence": 1, "source_session": "tool"}
            self.assertFalse(observed_evidence.has_observed_evidence(tmp, "commands", event["details"], forged))

    def test_concurrent_observers_publish_complete_receipts_with_one_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            command = "python -m unittest discover -s tests"
            response = {"exit_code": 0, "stdout": "Ran 1 test in 0.001s\n\nOK"}
            event = {
                "event_id": "shared-result", "session_id": "session", "turn_id": "turn",
                "signal": "test_pass", "category_hint": "commands", "command": command,
                "details": observed_evidence.observed_content(command, response), "tool_response": response,
            }
            worker = (
                "import json,sys;"
                f"sys.path.insert(0, {str(ROOT / 'scripts')!r});"
                "import observed_evidence;"
                "print(json.dumps(observed_evidence.observe_tool_result(sys.argv[1], json.loads(sys.argv[2]))))"
            )
            calls = [
                subprocess.Popen([sys.executable, "-c", worker, tmp, json.dumps(event)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                for _ in range(6)
            ]
            receipts = []
            for call in calls:
                stdout, stderr = call.communicate(timeout=30)
                self.assertEqual(call.returncode, 0, stderr.decode("utf-8", errors="replace"))
                receipts.append(json.loads(stdout.decode("utf-8")))
            self.assertTrue(observed_evidence.has_observed_evidence(
                tmp, "commands", event["details"], {"observed_evidence": receipts[0]},
            ))
            folder = recall_config.memory_dir(tmp) / "runtime" / "observed_evidence"
            self.assertEqual((folder / "receipt.key").stat().st_size, 32)
            receipt_path = folder / (hashlib.sha256(b"shared-result").hexdigest() + ".json")
            stored = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertTrue(observed_evidence.has_observed_evidence(
                tmp, "commands", event["details"], {"observed_evidence": stored},
            ))

    def test_material_success_requires_result_and_rejects_generic_exploration(self):
        for command, response, expected in [
            ("python -m pytest", {"exit_code": 0, "stdout": "1 passed"}, True),
            ("python build_plugin.py", {"exit_code": 0, "stdout": "Build passed"}, True),
            ("gh release create v1.0", {"exit_code": 0, "stdout": "https://github.com/org/repo/releases/tag/v1.0"}, True),
            ("python -m pytest", {}, False),
            ("python -m pytest", {"stdout": "1 passed"}, False),
            ("python -m pytest", {"exit_code": 0}, False),
            ("git status", {"exit_code": 0, "stdout": "clean"}, False),
            ("echo build passed", {"exit_code": 0, "stdout": "build passed"}, False),
            ("python -m pytest", {"exit_code": 0, "stdout": "done"}, False),
        ]:
            with self.subTest(command=command, response=response):
                decision = capture_policy.classify_tool_capture(root=None, payload={"tool_response": response}, tool_name="Bash", command=command, content=str(response.get("stdout", "")), mode="standard")
                self.assertEqual(decision is not None, expected)

    def test_material_success_redacts_before_signed_buffer_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            recall_config.activate_project(tmp)
            recall_config.set_capture_mode("standard", tmp)
            base = {"cwd": tmp, "session_id": "redaction", "turn_id": "output"}
            run_hook("prompt_inspector.py", {**base, "prompt": "Run the test."})
            response = {"exit_code": 0, "stdout": "1 passed\ntoken=dummy-secret-value"}
            run_hook(
                "post_tool_use.py",
                {**base, "tool_name": "Bash", "tool_input": {"command": "python -m pytest"}, "tool_response": response},
            )
            events = turn_buffer.load_events(tmp, "redaction", "output")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["details"], observed_evidence.observed_content("python -m pytest", response))
            self.assertIn("[REDACTED]", events[0]["details"])
            self.assertNotIn("dummy-secret-value", events[0]["details"])
            for path in recall_config.memory_dir(tmp).rglob("*"):
                if path.is_file():
                    self.assertNotIn("token=dummy-secret-value", path.read_text(encoding="utf-8", errors="ignore"))

    def test_debug_finalizer_packet_write_failure_retries_with_one_valid_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            recall_config.activate_project(tmp)
            recall_config.set_capture_mode("standard", tmp)
            cfg_path = recall_config.config_path(tmp)
            config = json.loads(cfg_path.read_text(encoding="utf-8"))
            config["observability_mode"] = "debug"
            cfg_path.write_text(json.dumps(config), encoding="utf-8")
            base = {"cwd": tmp, "session_id": "packet", "turn_id": "failure"}
            run_hook("prompt_inspector.py", {**base, "prompt": "The project must preserve finalizer evidence."})
            with patch("turn_buffer.json.dump", side_effect=OSError("simulated write failure")):
                first = run_hook("stop.py", base)
            self.assertIn("Evidence was retained for retry", first["systemMessage"])
            self.assertEqual(turn_buffer.finalizer_status(tmp, "packet", "failure"), "none")
            second = run_hook("stop.py", base)
            self.assertEqual(second["decision"], "block")
            self.assertEqual(turn_buffer.finalizer_status(tmp, "packet", "failure"), "requested")
            self.assertEqual(run_hook("stop.py", base), {"continue": True})

    def test_real_observed_result_finalizes_once_and_asserted_claims_do_not_validate(self):
        with tempfile.TemporaryDirectory() as tmp:
            recall_config.activate_project(tmp)
            recall_config.set_capture_mode("standard", tmp)
            Path(tmp, "test_real.py").write_text("import unittest\nclass Probe(unittest.TestCase):\n def test_sum(self): self.assertEqual(2+2,4)\n", encoding="utf-8")
            command = [sys.executable, "-m", "unittest", "discover", "-s", tmp]
            completed = subprocess.run(command, capture_output=True, text=True, check=True)
            response = {"exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
            base = {"cwd": tmp, "session_id": "real", "turn_id": "observed"}
            run_hook("prompt_inspector.py", {**base, "prompt": "Run the test."})
            run_hook("post_tool_use.py", {**base, "tool_name": "Bash", "tool_input": {"command": subprocess.list2cmdline(command)}, "tool_response": response})
            first = run_hook("stop.py", base)
            self.assertNotIn("failed", first.get("systemMessage", ""))
            records = list(storage.iter_records(tmp))
            self.assertEqual(len(records), 1)
            record = records[0]
            self.assertEqual(record.metadata["status"], "validated")
            self.assertTrue(observed_evidence.has_observed_evidence(tmp, record.category, record.content, record.metadata))
            self.assertEqual(run_hook("stop.py", base), {"continue": True})
            self.assertEqual([(r.id, r.content, r.metadata) for r in storage.iter_records(tmp)], [(record.id, record.content, record.metadata)])
            claim = {"category": "requirements", "summary": "Production ready", "content": "The application is production ready.", "status": "validated", "confidence": 1, "explicit_user_evidence": True, "observed_evidence": record.metadata["observed_evidence"], "evidence_ids": [record.metadata["observed_evidence"]["event_id"]]}
            batch = {"schema": "recall.finalizer_batch.v1", "session_id": "invented", "turn_id": "invented", "operations": [{"op": "save", "card": claim}]}
            saved = apply_finalizer_batch(batch, tmp)
            claimed_id = saved["operations"][0]["id"]
            apply_finalizer_batch({**batch, "session_id": "invented-2", "operations": [{"op": "confirm", "id": claimed_id, "explicit_confirmation": True}]}, tmp)
            claimed = next(r for r in storage.iter_records(tmp) if r.id == claimed_id)
            self.assertEqual(claimed.metadata["status"], "active")
            self.assertNotIn("observed_evidence", claimed.metadata)

    def test_finalizer_conflicting_opaque_claims_remain_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            for index, value in enumerate(("docs/release notes.md", "docs/release  notes.md")):
                batch = {"schema": "recall.finalizer_batch.v1", "session_id": "claims", "turn_id": str(index), "operations": [{"op": "save", "card": {"category": "requirements", "content": "Release notes: " + value, "summary": value, "status": "active", "claim_key": "notes.path", "claim_value": value}}]}
                apply_finalizer_batch(batch, tmp)
            records = list(storage.iter_records(tmp))
            self.assertEqual(len(records), 2)
            self.assertEqual({r.metadata["status"] for r in records}, {"active"})
            self.assertEqual({r.metadata["claim_value"] for r in records}, {"docs/release notes.md", "docs/release  notes.md"})
            self.assertTrue(all(r.metadata["review_claim_conflict"] for r in records))

    def test_unicode_debug_stop_is_valid_utf8_json_and_second_stop_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            recall_config.activate_project(tmp)
            recall_config.set_capture_mode("standard", tmp)
            cfg_path = recall_config.config_path(tmp)
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            cfg["observability_mode"] = "debug"
            cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
            base = {"cwd": tmp, "session_id": "unicode", "turn_id": "utf8"}
            run_hook("prompt_inspector.py", {**base, "prompt": "The project must preserve Grüße and 日本語."})
            turn_buffer.append_event(tmp, "unicode", "utf8", {"durable_candidate": True, "signal": "test_fail", "summary": "échec 秘密", "details": "Grüße 日本語", "category_hint": "debug_history"})
            data = json.dumps({**base, "last_assistant_message": "Fixed Grüße 日本語 ✅"}, ensure_ascii=False).encode("utf-8")
            env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
            command = [sys.executable, str(ROOT / "hooks" / "scripts" / "stop.py")]
            one = subprocess.run(command, input=data, capture_output=True, env=env, check=True)
            two = subprocess.run(command, input=data, capture_output=True, env=env, check=True)
            self.assertEqual(json.loads(one.stdout.decode("utf-8"))["decision"], "block")
            self.assertEqual(json.loads(two.stdout.decode("utf-8")), {"continue": True})
            packet = json.loads(turn_buffer.finalizer_request_path(tmp, "unicode", "utf8").read_text(encoding="utf-8"))
            self.assertEqual(packet["last_assistant_message"], "Fixed Grüße 日本語 ✅")
            events = turn_buffer.load_events(tmp, "unicode", "utf8")
            self.assertTrue(any(e.get("details") == "Grüße 日本語" for e in events))
            self.assertTrue(any("Grüße and 日本語" in e.get("details", "") for e in events))


if __name__ == "__main__":
    unittest.main()
