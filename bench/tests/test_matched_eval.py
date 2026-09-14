"""Harness mechanism tests. Synthetic transcripts are never native-agent proof."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BENCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BENCH))
from recall_bench import matched as m  # noqa: E402


class MatchedHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_tmp = tempfile.TemporaryDirectory()
        cls.repo = Path(cls.repo_tmp.name)
        subprocess.run(["git", "init", "-q", str(cls.repo)], check=True)
        (cls.repo / "source.py").write_text("x = 1\n", encoding="utf-8")
        (cls.repo / ".gitignore").write_text("dist/\n", encoding="utf-8")
        m.git(cls.repo, "add", "source.py", ".gitignore")
        m.git(cls.repo, "-c", "user.name=Harness Test", "-c", "user.email=test@example.invalid",
              "-c", "commit.gpgsign=false", "commit", "-qm", "Synthetic fixture")
        cls.commit = m.git(cls.repo, "rev-parse", "HEAD")

    @classmethod
    def tearDownClass(cls):
        # Git object files are read-only on Windows; do not remove this fixture's
        # repository here. TemporaryDirectory's Windows cleanup handles modes.
        cls.repo_tmp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.evidence, self.subjects = self.root / "evidence", self.root / "subjects"
        self.fixture = BENCH / "matched_tasks" / "tasks.json"
        self.host = {"name": "synthetic-unit-host", "version": "1"}
        self.models = dict.fromkeys(m.ARMS, "synthetic-unit-model")
        self.manifest = m.prepare(self.repo, self.commit, self.fixture, self.evidence, self.subjects,
                                  self.host, self.models)

    def begin(self, family="small_task", arm="candidate"):
        return m.begin(self.evidence, family, arm)

    def evidence_files(self, launch, *, assessment_changes=None, observation_changes=None, extra_events=None):
        task = next(t for t in m.load_fixture(self.fixture)["tasks"] if t["id"] == launch["family"])
        phases = task["subject"]["phases"]
        events = [{"kind": "run_start", "model": launch["requested_model"], "host": launch["host"],
                   "candidate": launch["candidate"]}]
        for i, phase in enumerate(phases):
            events.append({"kind": "phase_start", "phase_id": phase["id"], "session_id": f"session-{i}", "prompt": phase["prompt"]})
            events.extend([
                {"kind": "tool_call", "call_id": f"read-{i}", "name": "read_file", "arguments": {"path": "README.md"}},
                {"kind": "tool_result", "call_id": f"read-{i}", "output": "synthetic bytes", "is_error": False},
                {"kind": "assistant_message", "content": "Synthetic subject output for harness tests only."},
            ])
            if phase["interrupt_after"]:
                events.append({"kind": "interruption", "phase_id": phase["id"]})
        events.extend(extra_events or [])
        events.append({"kind": "run_end", "complete": True, "exit_code": 0})
        events = [{"seq": i, "attempt_id": launch["attempt_id"], **event} for i, event in enumerate(events, 1)]
        folder = self.root / "incoming" / self.evidence.name / launch["attempt_id"]
        folder.mkdir(parents=True)
        trace = folder / "trace.jsonl"
        trace.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
        raw = folder / "raw.jsonl"
        raw.write_bytes(trace.read_bytes())
        observation = {key: True for key in ("fresh_context", "workspace_only", "controller_context_absent",
                       "judge_context_absent", "fresh_store", "full_trace", "runtime_policy_verified")}
        observation.update({"evidence": "synthetic fixture attestation, not native proof", "tokens": {"input": 100, "output": 20},
                            "elapsed_seconds": 1.5, "memory_access_audit": {"complete": True,
                            "surfaces": sorted(m.AUDIT_SURFACES), "phases": [p["id"] for p in phases],
                            "event_count": sum(e["kind"] == "memory_access" for e in events),
                            "evidence": "synthetic instrumented host export"}})
        observation.update(observation_changes or {})
        assessment = {"judge": "synthetic-test-judge", "evidence": "synthetic artifact check", "harms": [],
                      "task_result": "pass", "wrong_action": False, "stale_memory_use": False,
                      "trace_sha256": m.sha256(trace), "history_benefit": None}
        assessment.update(assessment_changes or {})
        m.write_new(folder / "observation.json", observation)
        m.write_new(folder / "assessment.json", assessment)
        return {"trace": trace, "raw": raw, "observation": folder / "observation.json", "assessment": folder / "assessment.json"}

    def seal(self, launch, **changes):
        files = self.evidence_files(launch, **changes)
        summary = m.seal(self.evidence, launch["attempt_id"], **files)
        result = next(r for r in summary["attempts"] if r["attempt_id"] == launch["attempt_id"])
        return result, files

    def test_matrix_starts_with_twenty_unknown_cells(self):
        report = m.summarize(self.evidence)
        self.assertEqual(len(report["cells"]), 20)
        self.assertEqual(report["status"], "unknown")
        self.assertEqual(report["candidate_correct_families"], 0)
        self.assertIsNone(report["candidate"]["zip_sha256"])

    def test_each_arm_and_rerun_has_a_fresh_disjoint_store(self):
        roots = []
        for arm in m.ARMS:
            launch = self.begin(arm=arm)
            root = Path(launch["workspace"])
            for store in (".recall", ".native-memory", ".host"):
                self.assertEqual(list((root / store).iterdir()), [])
            (root / ".recall" / "witness").write_text(arm)
            roots.append(root)
            m.seal(self.evidence, launch["attempt_id"])
        rerun = self.begin()
        self.assertEqual(list((Path(rerun["workspace"]) / ".recall").iterdir()), [])
        roots.append(Path(rerun["workspace"]))
        m.disjoint(roots)
        self.assertEqual(m.check_isolation(self.evidence, self.manifest), [])
        for root, arm in zip(roots, m.ARMS, strict=False):
            self.assertEqual((root / ".recall" / "witness").read_text(), arm)

    def test_subject_payload_and_workspace_exclude_private_canaries(self):
        fixture = m.load_fixture(self.fixture)
        fixture["controller_conversation"] = "CONTROLLER_PRIVATE_CANARY"
        for task in fixture["tasks"]:
            task["judge"]["expected"] = "EXPECTED_PRIVATE_CANARY"
            task["judge"]["notes"] = "JUDGE_PRIVATE_CANARY"
        custom = self.root / "custom.json"
        m.write_new(custom, fixture)
        evidence, subjects = self.root / "private", self.root / "isolated"
        m.prepare(self.repo, self.commit, custom, evidence, subjects, self.host, self.models)
        for arm in m.ARMS:
            launch = m.begin(evidence, "recurring_failure", arm)
            payload = m.subject_input(evidence, launch["attempt_id"], "task")
            self.assertEqual(set(payload), {"prompt"})
            output = json.dumps(payload) + "".join(p.read_text() for p in Path(launch["workspace"]).rglob("*") if p.is_file())
            self.assertNotIn("PRIVATE_CANARY", output)
            self.assertNotIn(str(evidence), output)
            self.assertNotIn(str(self.repo), output)
            m.seal(evidence, launch["attempt_id"])

    def test_missing_trace_never_becomes_pass_or_zero_reads(self):
        launch = self.begin("no_memory")
        summary = m.seal(self.evidence, launch["attempt_id"])
        result = summary["attempts"][0]
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["task_result"], "unknown")
        self.assertIsNone(result["recall_reads"])
        self.assertIsNone(result["tokens"])

    def test_sealed_complete_fixture_keeps_fields_separate(self):
        result, _ = self.seal(self.begin())
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["tokens"], {"input": 100, "output": 20})
        self.assertEqual(result["elapsed_seconds"], 1.5)
        self.assertFalse(result["wrong_action"])
        self.assertFalse(result["stale_memory_use"])
        self.assertEqual(result["critical_faults"], [])

    def test_partial_tools_and_missing_raw_export_are_unknown(self):
        launch = self.begin()
        files = self.evidence_files(launch)
        lines = [json.loads(line) for line in files["trace"].read_text().splitlines()]
        lines = [line for line in lines if line["kind"] != "tool_result"]
        files["trace"].write_text("\n".join(json.dumps(line) for line in lines))
        files.pop("raw")
        result = m.seal(self.evidence, launch["attempt_id"], **files)["attempts"][0]
        self.assertEqual(result["status"], "unknown")
        self.assertIn("unpaired or duplicate tool calls", result["unknown_reasons"])
        self.assertIn("missing or changed raw-trace.bin", result["unknown_reasons"])

    def test_seeded_p0_stops_next_arm_and_preserves_failed_trace(self):
        launch = self.begin()
        result, files = self.seal(launch, extra_events=[{"kind": "fault", "fault": "data_loss", "severity": "P3"}])
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["critical_faults"][0]["severity"], "P0")
        retained = self.evidence / "attempts" / launch["attempt_id"] / "trace.jsonl"
        self.assertEqual(retained.read_bytes(), files["trace"].read_bytes())
        with self.assertRaisesRegex(ValueError, "halted"):
            self.begin(arm="memory_off")

    def test_seeded_p1_cannot_be_averaged_into_a_pass(self):
        result, _ = self.seal(self.begin(), assessment_changes={"harms": [{"severity": "P1", "fault": "wrong_current_truth", "evidence": "line 6"}]})
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(m.summarize(self.evidence)["status"], "blocked")

    def test_p0_survives_malformed_tail_and_unknown_completion(self):
        launch = self.begin()
        files = self.evidence_files(launch, extra_events=[{"kind": "fault", "fault": "secret_exposure"}])
        with files["trace"].open("a") as handle:
            handle.write("{broken\n")
        result = m.seal(self.evidence, launch["attempt_id"], **files)["attempts"][0]
        self.assertEqual(result["status"], "blocked")
        self.assertIn("malformed trace line", " ".join(result["unknown_reasons"]))

    def test_no_memory_setup_access_is_allowed(self):
        launch = self.begin("no_memory")
        setup = {"kind": "memory_access", "backend": "recall", "operation": "write", "phase_id": "setup", "project_root": launch["workspace"]}
        result, _ = self.seal(launch, extra_events=[setup])
        self.assertEqual(result["status"], "pass")

    def test_no_memory_task_access_is_p1(self):
        launch = self.begin("no_memory")
        result, _ = self.seal(launch, extra_events=[{"kind": "memory_access", "backend": "recall", "operation": "read",
            "phase_id": "task", "project_root": launch["workspace"]}])
        self.assertEqual(result["status"], "blocked")

    def test_no_memory_needs_full_hook_and_store_instrumentation(self):
        result, _ = self.seal(self.begin("no_memory"), observation_changes={"memory_access_audit": {"complete": True, "event_count": 0}})
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["recall_reads"])

    def test_null_audit_fields_and_unknown_backend_never_prove_zero_access(self):
        launch = self.begin("no_memory")
        result, _ = self.seal(launch, observation_changes={"memory_access_audit": {"complete": True, "surfaces": None}},
            extra_events=[{"kind": "memory_access", "backend": None, "operation": "read", "phase_id": "task", "project_root": launch["workspace"]}])
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["recall_reads"])
        self.assertIn("memory access backend unknown", result["unknown_reasons"])

    def test_foreign_project_access_is_p0(self):
        result, _ = self.seal(self.begin(), extra_events=[{"kind": "memory_access", "backend": "recall",
            "operation": "read", "phase_id": "task", "project_root": str(self.root / "foreign")}])
        self.assertEqual(result["critical_faults"][0]["fault"], "cross_project_memory")

    def test_stale_fact_use_blocks_despite_correct_reported_answer(self):
        result, _ = self.seal(self.begin("stale_fact"), assessment_changes={"stale_memory_use": True})
        self.assertEqual(result["status"], "blocked")

    def test_null_metrics_and_harm_review_stay_unknown(self):
        result, _ = self.seal(self.begin(), observation_changes={"tokens": None, "elapsed_seconds": None},
                             assessment_changes={"harms": None, "wrong_action": None})
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["tokens"])
        self.assertIsNone(result["wrong_action"])

    def test_reruns_preserve_failures_and_have_a_limit(self):
        first = self.begin()
        self.seal(first, assessment_changes={"task_result": "fail"})
        second = self.begin()
        self.seal(second, assessment_changes={"task_result": "fail"})
        with self.assertRaisesRegex(ValueError, "one rerun"):
            self.begin()
        self.assertEqual(len(m.summarize(self.evidence)["attempts"]), 2)
        with self.assertRaisesRegex(ValueError, "already sealed"):
            m.seal(self.evidence, first["attempt_id"])

    def test_clean_cases_cannot_be_rerun_and_pending_cases_must_be_sealed(self):
        launch = self.begin()
        with self.assertRaisesRegex(ValueError, "pending"):
            self.begin(arm="docs_only")
        self.seal(launch)
        with self.assertRaisesRegex(ValueError, "one rerun"):
            self.begin()

    def test_changed_trace_is_unknown_and_original_receipt_is_preserved(self):
        launch = self.begin()
        self.seal(launch)
        folder = self.evidence / "attempts" / launch["attempt_id"]
        receipt = (folder / "receipt.json").read_bytes()
        with (folder / "raw-trace.bin").open("ab") as handle:
            handle.write(b"changed")
        self.assertEqual(m.summarize(self.evidence)["attempts"][0]["status"], "unknown")
        self.assertEqual((folder / "receipt.json").read_bytes(), receipt)

    def test_unknown_model_and_missing_interruption_are_unknown(self):
        launch = self.begin("interrupted_task")
        files = self.evidence_files(launch)
        lines = [json.loads(line) for line in files["trace"].read_text().splitlines()]
        lines[0]["model"] = "some-other-model"
        lines = [e for e in lines if e["kind"] != "interruption"]
        files["trace"].write_text("\n".join(json.dumps(e) for e in lines))
        result = m.seal(self.evidence, launch["attempt_id"], **files)["attempts"][0]
        self.assertEqual(result["status"], "unknown")
        self.assertIn("interruption not evidenced", result["unknown_reasons"])

    def test_candidate_sha_is_fixed_and_dirty_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "full, current"):
            m.candidate_identity(self.repo, self.commit[:7])
        extra = self.repo / "untracked.py"
        extra.write_text("new source")
        try:
            with self.assertRaisesRegex(ValueError, "clean"):
                self.begin()
            self.assertEqual(m.summarize(self.evidence)["status"], "unknown")
        finally:
            extra.unlink()

    def test_zip_hash_is_frozen_and_changed_zip_blocks_launch(self):
        artifact = self.root / "candidate.zip"
        artifact.write_bytes(b"synthetic ZIP bytes; hashing mechanism only")
        evidence, subjects = self.root / "zip-evidence", self.root / "zip-subjects"
        manifest = m.prepare(self.repo, self.commit, self.fixture, evidence, subjects, self.host, self.models, artifact)
        self.assertEqual(manifest["candidate"]["zip_sha256"], m.sha256(artifact))
        artifact.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "ZIP changed"):
            m.begin(evidence, "small_task", "candidate")

    def test_fixture_manifest_and_workspace_redirection_fail_closed(self):
        launch = self.begin()
        folder = self.evidence / "attempts" / launch["attempt_id"]
        changed = dict(launch, workspace=str(self.root / "foreign"))
        (folder / "launch.json").write_text(json.dumps(changed))
        report = m.summarize(self.evidence)
        self.assertEqual(report["status"], "blocked")
        self.assertTrue(report["isolation_errors"])
        (self.evidence / "fixture.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "fixture changed"):
            m.summarize(self.evidence)

    def test_existing_or_overlapping_roots_never_overwrite(self):
        before = (self.evidence / "manifest.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "new roots"):
            m.prepare(self.repo, self.commit, self.fixture, self.evidence, self.subjects, self.host, self.models)
        self.assertEqual((self.evidence / "manifest.json").read_bytes(), before)
        with self.assertRaisesRegex(ValueError, "overlap"):
            m.prepare(self.repo, self.commit, self.fixture, self.root / "nested", self.root / "nested" / "subject", self.host, self.models)
        for unsafe in ("../secret", "C:/secret", ".recall/store.json", "..\\secret", "."):
            with self.assertRaises(ValueError):
                m.safe_relative(unsafe)

    def test_twenty_synthetic_cases_exercise_gate_without_native_claims(self):
        artifact = self.root / "synthetic.zip"
        artifact.write_bytes(b"synthetic identity bytes; never native proof")
        self.evidence, self.subjects = self.root / "matrix-evidence", self.root / "matrix-subjects"
        m.prepare(self.repo, self.commit, self.fixture, self.evidence, self.subjects, self.host, self.models, artifact)
        for family in m.FAMILIES:
            controls = []
            for arm in ("memory_off", "docs_only", "native_memory", "candidate"):
                launch = self.begin(family, arm)
                benefit = None
                if arm == "candidate" and family in ("recurring_failure", "interrupted_task"):
                    benefit = {"helps": True, "compared_attempts": controls, "evidence": "synthetic comparison for gate mechanism only"}
                self.seal(launch, assessment_changes={"history_benefit": benefit})
                if arm != "candidate":
                    controls.append(launch["attempt_id"])
        report = m.summarize(self.evidence)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["candidate_correct_families"], 5)
        self.assertEqual(len(report["history_benefit_families"]), 2)
        self.assertNotIn("mean_score", report)
        self.assertEqual(len(report["attempts"]), 20)

    def test_mixed_models_are_not_a_matched_trial(self):
        models = dict(self.models, native_memory="another-model")
        with self.assertRaisesRegex(ValueError, "same model"):
            m.prepare(self.repo, self.commit, self.fixture, self.root / "new-evidence", self.root / "new-subjects", self.host, models)

    def test_run_failure_is_retained_even_with_judge_pass(self):
        launch = self.begin()
        files = self.evidence_files(launch)
        lines = [json.loads(line) for line in files["trace"].read_text().splitlines()]
        lines[-1]["exit_code"] = 1
        files["trace"].write_text("\n".join(json.dumps(e) for e in lines))
        assessment = m.read_json(files["assessment"])
        assessment["trace_sha256"] = m.sha256(files["trace"])
        files["assessment"].write_text(json.dumps(assessment))
        result = m.seal(self.evidence, launch["attempt_id"], **files)["attempts"][0]
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["exit_code"], 1)
        self.assertEqual(result["reported_task_result"], "pass")

    def test_launch_cannot_substitute_another_candidate(self):
        launch = self.begin()
        launch["candidate"] = dict(launch["candidate"], commit="0" * 40)
        folder = self.evidence / "attempts" / launch["attempt_id"]
        (folder / "launch.json").write_text(json.dumps(launch))
        result, _ = self.seal(launch)
        self.assertEqual(result["status"], "unknown")
        self.assertIn("launch identity differs from frozen matrix", result["unknown_reasons"])

    def test_cli_unknown_report_exits_two(self):
        process = subprocess.run([sys.executable, str(BENCH / "run_matched_eval.py"), "report", "--evidence", str(self.evidence)], capture_output=True, text=True)
        self.assertEqual(process.returncode, 2)
        self.assertEqual(json.loads(process.stdout)["status"], "unknown")

    def fresh_matrix(self, label):
        self.evidence, self.subjects = self.root / f"evidence-{label}", self.root / f"subjects-{label}"
        self.manifest = m.prepare(self.repo, self.commit, self.fixture, self.evidence, self.subjects,
                                  self.host, self.models)

    def test_review_arm_policy_checks_both_backends_and_operations(self):
        for arm in m.ARMS:
            for backend in ("recall", "native_memory"):
                for operation in ("read", "write"):
                    with self.subTest(arm=arm, backend=backend, operation=operation):
                        self.fresh_matrix(f"{arm}-{backend}-{operation}")
                        launch = self.begin(arm=arm)
                        # A contradictory mutable policy/attestation cannot grant access.
                        launch["runtime_policy"].update(recall_enabled=True, native_memory_enabled=True)
                        (self.evidence / "attempts" / launch["attempt_id"] / "launch.json").write_text(json.dumps(launch))
                        result, _ = self.seal(launch, extra_events=[{"kind": "memory_access", "backend": backend,
                            "operation": operation, "phase_id": "task", "project_root": launch["workspace"]}])
                        permitted = (arm, backend) in (("candidate", "recall"), ("native_memory", "native_memory"))
                        self.assertEqual(result["status"], "pass" if permitted else "blocked")
                        if not permitted:
                            self.assertTrue(any(f["severity"] == "P1" for f in result["critical_faults"]))
                            with self.assertRaisesRegex(ValueError, "halted"):
                                self.begin("stale_fact", arm)

    def test_review_forbidden_access_still_blocks_when_metrics_are_unknown(self):
        launch = self.begin(arm="memory_off")
        result, _ = self.seal(launch, extra_events=[{"kind": "memory_access", "backend": "native_memory",
            "operation": "write", "phase_id": "task", "project_root": launch["workspace"]}],
            observation_changes={"tokens": None, "elapsed_seconds": None})
        self.assertEqual(result["status"], "blocked")
        self.assertIsNone(result["tokens"])
        self.assertIsNone(result["elapsed_seconds"])

    def test_review_null_backend_or_operation_remains_unknown(self):
        for backend, operation in ((None, "read"), ("native_memory", None)):
            with self.subTest(backend=backend, operation=operation):
                self.fresh_matrix(f"null-{backend}-{operation}")
                launch = self.begin(arm="memory_off")
                result, _ = self.seal(launch, extra_events=[{"kind": "memory_access", "backend": backend,
                    "operation": operation, "phase_id": "task", "project_root": launch["workspace"]}])
                self.assertEqual(result["status"], "unknown")
                self.assertEqual(result["critical_faults"], [])
                self.assertIsNone(result["recall_reads"])

    def history_controls(self):
        controls = []
        for arm in ("memory_off", "docs_only", "native_memory"):
            launch = self.begin("recurring_failure", arm)
            self.seal(launch)
            controls.append(launch["attempt_id"])
        return controls

    def test_review_history_benefit_needs_each_control_arm(self):
        for omitted in ("memory_off", "docs_only", "native_memory"):
            with self.subTest(omitted=omitted):
                self.fresh_matrix(omitted)
                controls = self.history_controls()
                selected = [ref for ref in controls if f"--{omitted}--" not in ref]
                self.seal(self.begin("recurring_failure"), assessment_changes={"history_benefit": {
                    "helps": True, "compared_attempts": selected, "evidence": "Synthetic missing-control probe"}})
                self.assertEqual(m.summarize(self.evidence)["history_benefit_families"], [])

    def test_review_history_control_receipts_are_frozen_with_judgment(self):
        controls = self.history_controls()
        launch = self.begin("recurring_failure")
        self.seal(launch, assessment_changes={"history_benefit": {
            "helps": True, "compared_attempts": controls, "evidence": "Synthetic complete-control probe"}})
        self.assertEqual(m.summarize(self.evidence)["history_benefit_families"], ["recurring_failure"])
        candidate_folder = self.evidence / "attempts" / launch["attempt_id"]
        original_receipt = (candidate_folder / "receipt.json").read_bytes()
        original_judgment = (candidate_folder / "assessment.json").read_bytes()
        control_receipt = self.evidence / "attempts" / controls[0] / "receipt.json"
        changed = m.read_json(control_receipt)
        changed["sealed_at"] = "changed after comparison"
        control_receipt.write_text(json.dumps(changed))
        # Control artifact hashes still verify, but it is not the compared receipt.
        self.assertEqual(m.summarize(self.evidence)["history_benefit_families"], [])
        self.assertEqual((candidate_folder / "receipt.json").read_bytes(), original_receipt)
        self.assertEqual((candidate_folder / "assessment.json").read_bytes(), original_judgment)


if __name__ == "__main__":
    unittest.main()
