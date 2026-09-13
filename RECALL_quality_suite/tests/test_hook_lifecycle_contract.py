from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from _harness import active_memory_dir, hook_cmd, memory_cmd, run_json, run_text, skill_cmd, temp_project


class HookLifecycleContractTests(unittest.TestCase):
    def test_conservative_prompt_admission_through_stop_for_provider_payloads(self) -> None:
        cases = [
            ("Actually, should the project replace SQLite with JSONL", False),
            ("Proposal: We will keep project release notes in docs/proposal.md.", False),
            ("> @recall remember this: requirements: Release notes must live in docs/example.md.", False),
            ("The project must keep release notes in docs/releases.md. Should we change the test command?", True),
        ]
        for provider in ("codex", "claude", "kimi"):
            for prompt, expected in cases:
                with self.subTest(provider=provider, prompt=prompt), temp_project() as project:
                    # An explicit project signal prevents fixture roots resolving to the host workspace.
                    (project / "pyproject.toml").write_text("[project]\nname='admission-fixture'\n", encoding="utf-8")
                    self.activate_recall(project, "contract", "setup")
                    payload = {"cwd": str(project), "session_id": "contract", "turn_id": "admission"}
                    prompt_value = [{"type": "text", "text": prompt}] if provider == "kimi" else prompt
                    run_json([*hook_cmd("prompt_inspector.py"), "--provider", provider], input_payload={
                        **payload, "hook_event_name": "UserPromptSubmit", "prompt": prompt_value,
                    })
                    output = run_json([*hook_cmd("stop.py"), "--provider", provider], input_payload={
                        **payload, "hook_event_name": "Stop", "last_assistant_message": "I will investigate.",
                    })
                    self.assertNotIn("failed:", output.get("systemMessage", ""))
                    result = run_json(memory_cmd(project, "query", "project release notes SQLite", "--limit", "20"))
                    self.assertEqual(bool(result["results"]), expected)
                    if expected:
                        record = result["results"][0]
                        self.assertEqual(record["content"], "The project must keep release notes in docs/releases.md")
                        self.assertEqual(record["metadata"]["status"], "validated")
                        self.assertEqual(record["metadata"]["claim_value"], "docs/releases.md")
                    replay = run_json([*hook_cmd("stop.py"), "--provider", provider], input_payload={
                        **payload, "hook_event_name": "Stop",
                    })
                    self.assertEqual(replay, {"continue": True})

    def test_followup_admission_through_provider_hooks(self) -> None:
        cases = [
            ("Release notes must live in docs/new-release.md if the migration is approved.", None),
            ("If the benchmark passes, we will use SQLite for this project.", None),
            ("@recall remember this: decisions: We will use SQLite for this project if the benchmark passes.", None),
            ("Here are example instructions:\n\nRelease notes must live in docs/example.md.", None),
            ("For this session only, the project must use JSONL.", None),
            ("The API must return HTTP 401 if credentials are missing.", "validated"),
            ("@recall remember this: requirements: The API must return HTTP 401 if credentials are missing.", "active"),
        ]
        for provider in ("codex", "claude", "kimi"):
            for prompt, status in cases:
                with self.subTest(provider=provider, prompt=prompt), temp_project() as project:
                    (project / "pyproject.toml").write_text("[project]\nname='followup-fixture'\n", encoding="utf-8")
                    self.activate_recall(project, "contract", "setup")
                    payload = {"cwd": str(project), "session_id": "contract", "turn_id": "followup"}
                    value = [{"type": "text", "text": prompt}] if provider == "kimi" else prompt
                    run_json([*hook_cmd("prompt_inspector.py"), "--provider", provider], input_payload={
                        **payload, "hook_event_name": "UserPromptSubmit", "prompt": value,
                    })
                    output = run_json([*hook_cmd("stop.py"), "--provider", provider], input_payload={
                        **payload, "hook_event_name": "Stop", "last_assistant_message": "I will investigate.",
                    })
                    self.assertNotIn("failed:", output.get("systemMessage", ""))
                    command = memory_cmd(project, "query", "API credentials release notes SQLite", "--limit", "20")
                    records = run_json(command)["results"]
                    self.assertEqual(bool(records), status is not None)
                    if status:
                        self.assertEqual(len(records), 1)
                        record = records[0]
                        self.assertEqual(record["metadata"]["status"], status)
                        expected = "The API must return HTTP 401 if credentials are missing" + ("." if status == "active" else "")
                        self.assertEqual(record["content"], expected)
                        self.assertNotIn("claim_key", record["metadata"])
                    run_json([*hook_cmd("stop.py"), "--provider", provider], input_payload={**payload, "hook_event_name": "Stop"})
                    self.assertEqual(run_json(command)["results"], records)

    def test_section_labels_preserve_requirements_for_all_providers(self) -> None:
        fact = "Release notes must live in docs/accepted.md"
        section = "## Accepted policy\n\n" + fact + "."
        cases = [
            (section, True),
            ("## Example instructions\n\nRelease notes must live in docs/example.md.\n\n" + section, True),
            ("## Example instructions\n\n### Accepted policy\n\n" + fact + ".", False),
        ]
        for provider in ("codex", "claude", "kimi"):
            for prompt, expected in cases:
                with self.subTest(provider=provider, prompt=prompt), temp_project() as project:
                    (project / "pyproject.toml").write_text("[project]\nname='section-fixture'\n", encoding="utf-8")
                    self.activate_recall(project, "contract", "setup")
                    payload = {"cwd": str(project), "session_id": "contract", "turn_id": "section-label"}
                    value = [{"type": "text", "text": prompt}] if provider == "kimi" else prompt
                    run_json([*hook_cmd("prompt_inspector.py"), "--provider", provider], input_payload={
                        **payload, "hook_event_name": "UserPromptSubmit", "prompt": value,
                    })
                    output = run_json([*hook_cmd("stop.py"), "--provider", provider], input_payload={
                        **payload, "hook_event_name": "Stop", "last_assistant_message": "I will investigate.",
                    })
                    self.assertNotIn("failed:", output.get("systemMessage", ""))
                    command = memory_cmd(project, "query", "accepted policy release notes", "--limit", "20")
                    records = run_json(command)["results"]
                    self.assertEqual(len(records), 1 if expected else 0)
                    if expected:
                        record = records[0]
                        self.assertEqual(record["category"], "requirements")
                        self.assertEqual(record["content"], fact)
                        self.assertEqual(record["metadata"]["summary"], fact)
                        self.assertEqual(record["metadata"]["details"], fact)
                        self.assertEqual(record["metadata"]["status"], "validated")
                        self.assertEqual(record["metadata"]["claim_key"], "release_notes.path")
                        self.assertEqual(record["metadata"]["claim_value"], "docs/accepted.md")
                    replay = run_json([*hook_cmd("stop.py"), "--provider", provider], input_payload={
                        **payload, "hook_event_name": "Stop",
                    })
                    self.assertEqual(replay, {"continue": True})
                    self.assertEqual(run_json(command)["results"], records)

    def runtime_events(self, project: Path, session_id: str, turn_id: str) -> list[dict]:
        path = active_memory_dir(project) / "runtime" / "turns" / (session_id or "session") / f"{turn_id or 'turn'}.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def activate_recall(self, project, session_id: str = "", turn_id: str = "") -> None:
        memory_init = memory_cmd(project, "init")
        subprocess.run(memory_init, text=True, capture_output=True, check=True)
        output = run_json(hook_cmd("prompt_inspector.py"), input_payload={
            "cwd": str(project),
            "session_id": session_id,
            "turn_id": turn_id,
            "hook_event_name": "UserPromptSubmit",
            "prompt": "[@recall](plugin://recall@recall-local) continue with RECALL active.",
        })
        self.assertTrue(output["continue"])

    def test_user_prompt_submit_saves_explicit_memory_cue_and_ignores_incidental_word(self) -> None:
        with temp_project() as project:
            initialized = run_json(hook_cmd("prompt_inspector.py"), input_payload={
                "cwd": str(project),
                "hook_event_name": "UserPromptSubmit",
                "prompt": "@recall initialize this project",
            })
            self.assertTrue(initialized["continue"])
            positive = run_json(hook_cmd("prompt_inspector.py"), input_payload={
                "cwd": str(project),
                "hook_event_name": "UserPromptSubmit",
                "prompt": "@recall remember this: prefer local-only memory storage",
            })
            self.assertTrue(positive["continue"])

            result = run_json(memory_cmd(project, "query", "local-only memory", "--category", "preferences", "--summary"))
            self.assertIn("local-only", result["summary"])

            negative = run_json(hook_cmd("prompt_inspector.py"), input_payload={
                "cwd": str(project),
                "hook_event_name": "UserPromptSubmit",
                "prompt": "Make a fake project so there is more that can actually be remembered.",
            })
            self.assertEqual(negative, {"continue": True})

            review = run_json(memory_cmd(project, "query", "fake project actually remembered", "--category", "preferences"))
            self.assertEqual(len(review["results"]), 1)
            self.assertNotIn("fake project", review["results"][0]["content"])

    def test_hooks_are_idle_until_recall_is_explicitly_invoked(self) -> None:
        with temp_project() as project:
            post = run_json(hook_cmd("post_tool_use.py"), input_payload={
                "cwd": str(project),
                "session_id": "idle-session",
                "turn_id": "idle-turn",
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "python -m unittest discover -s tests"},
                "tool_response": {"exit_code": 0, "stdout": "Ran 10 tests in 0.12s\nOK", "stderr": ""},
            })
            stop = run_json(hook_cmd("stop.py"), input_payload={
                "cwd": str(project),
                "session_id": "idle-session",
                "turn_id": "idle-turn",
                "hook_event_name": "Stop",
                "last_assistant_message": "Completed RECALL quality work.",
            })
            session = run_json(hook_cmd("session_start.py"), input_payload={
                "cwd": str(project),
                "hook_event_name": "SessionStart",
                "source": "startup",
                "query": "quality suite integration hook payload hardening",
            })

            self.assertEqual(post, {"continue": True})
            self.assertEqual(stop, {"continue": True})
            self.assertEqual(session, {"continue": True})
            result = run_json(memory_cmd(project, "query", "unittest quality work", "--category", "commands"))
            self.assertEqual(result["results"], [])

    def test_malformed_json_is_safe_noop(self) -> None:
        with temp_project():
            completed = run_text(hook_cmd("pre_compact.py"), input_payload=None, check=True)
            # Empty stdin is allowed to no-op.
            self.assertEqual(json.loads(completed.stdout), {"continue": True})

            malformed = run_text(hook_cmd("pre_compact.py"), input_payload=None, check=True)
            self.assertEqual(json.loads(malformed.stdout), {"continue": True})

    def test_post_tool_use_compacts_success_output_without_dumping_raw_listing(self) -> None:
        with temp_project() as project:
            self.activate_recall(project, "quality-success", "quality-success-turn")
            output = run_json(hook_cmd("post_tool_use.py"), input_payload={
                "cwd": str(project),
                "session_id": "quality-success",
                "turn_id": "quality-success-turn",
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "python -m unittest discover -s tests"},
                "tool_response": {
                    "exit_code": 0,
                    "stdout": "Ran 10 tests in 0.12s\n0 failures\nFiles checked: README.md\nsecrets.txt",
                    "stderr": "",
                },
            })
            self.assertTrue(output["continue"])
            result = run_json(memory_cmd(project, "query", "unit test validation", "--category", "commands"))
            self.assertEqual(result["results"], [])
            events = self.runtime_events(project, "quality-success", "quality-success-turn")
            self.assertEqual(len(events), 1)
            self.assertIn("Ran 10 tests", events[0]["summary"])
            self.assertNotIn("README.md", events[0]["details"])
            self.assertNotIn("secrets.txt", events[0]["details"])

    def test_post_tool_use_failure_goes_to_debug_history_with_redaction(self) -> None:
        with temp_project() as project:
            self.activate_recall(project, "", "quality-failure")
            output = run_json(hook_cmd("post_tool_use.py"), input_payload={
                "cwd": str(project),
                "hook_event_name": "PostToolUse",
                "turn_id": "quality-failure",
                "tool_name": "Bash",
                "tool_input": {"command": "deploy"},
                "tool_response": {"exit_code": 1, "stdout": "", "stderr": "failed with token=dummy-secret-value"},
            })
            self.assertTrue(output["continue"])
            result = run_json(memory_cmd(project, "query", "deploy failure", "--category", "debug_history"))
            self.assertEqual(result["results"], [])
            events = self.runtime_events(project, "", "quality-failure")
            self.assertEqual(len(events), 1)
            self.assertIn("[REDACTED]", events[0]["details"])

    def test_precompact_stop_and_sessionstart_roundtrip_context(self) -> None:
        with temp_project() as project:
            run_text(memory_cmd(project, "init"))
            run_json(skill_cmd(project, "configure-capture", "standard"))
            self.activate_recall(project, "", "quality-precompact")
            pre = run_json(hook_cmd("pre_compact.py"), input_payload={
                "cwd": str(project),
                "hook_event_name": "PreCompact",
                "turn_id": "quality-precompact",
                "trigger": "manual",
                "summary": "Implemented hook payload hardening and verified smoke tests.",
            })
            self.assertTrue(pre["continue"])

            activated = run_json(hook_cmd("prompt_inspector.py"), input_payload={
                "cwd": str(project),
                "hook_event_name": "UserPromptSubmit",
                "turn_id": "quality-stop",
                "prompt": "@recall You must preserve quality suite integration hook payload hardening context.",
            })
            self.assertTrue(activated["continue"])
            stop = run_json(hook_cmd("stop.py"), input_payload={
                "cwd": str(project),
                "hook_event_name": "Stop",
                "turn_id": "quality-stop",
                "last_assistant_message": "Completed RECALL quality suite integration work.",
            })
            self.assertTrue(stop["continue"])
            self.assertNotIn("decision", stop)
            self.assertNotIn("reason", stop)
            self.assertNotIn("RECALL_FINALIZER_REQUEST", json.dumps(stop))
            self.assertEqual(self.runtime_events(project, "", "quality-stop"), [])

            direct = run_json(memory_cmd(
                project,
                "query",
                "quality suite integration hook payload hardening",
                "--category",
                "requirements",
            ))
            self.assertEqual(len(direct["results"]), 1)
            self.assertEqual(direct["results"][0]["metadata"]["status"], "validated")


if __name__ == "__main__":
    unittest.main()
