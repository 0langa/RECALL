from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import config as recall_config  # noqa: E402


def run_hook(script: str, payload: dict) -> dict:
    return run_hook_raw(script, json.dumps(payload))


def run_hook_with_args(script: str, payload: dict, *args: str) -> dict:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "hooks" / "scripts" / script), *args],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
        cwd=ROOT,
    )
    return json.loads(completed.stdout)


def run_hook_raw(script: str, raw: str) -> dict:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "hooks" / "scripts" / script)],
        input=raw,
        text=True,
        capture_output=True,
        check=True,
        cwd=ROOT,
    )
    return json.loads(completed.stdout)


def query_memory(root: str, query: str, category: str) -> dict:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "memory_manager.py"),
            "--root",
            root,
            "query",
            query,
            "--category",
            category,
        ],
        text=True,
        capture_output=True,
        check=True,
        cwd=ROOT,
    )
    return json.loads(completed.stdout)


def runtime_events(root: str, session_id: str, turn_id: str) -> list[dict]:
    safe_session = session_id or "session"
    safe_turn = turn_id or "turn"
    path = recall_config.memory_dir(root) / "runtime" / "turns" / safe_session / f"{safe_turn}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def activate_recall(root: str, session_id: str = "", turn_id: str = "", prompt: str | None = None) -> dict:
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "memory_manager.py"),
            "--root",
            root,
            "init",
        ],
        text=True,
        capture_output=True,
        check=True,
        cwd=ROOT,
    )
    return run_hook(
        "prompt_inspector.py",
        {
            "cwd": root,
            "session_id": session_id,
            "turn_id": turn_id,
            "hook_event_name": "UserPromptSubmit",
            "prompt": prompt or "[@recall](plugin://recall@recall-local) continue with RECALL active.",
        },
    )


class HookTests(unittest.TestCase):
    def test_prompt_inspector_saves_remembered_preference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0.1.0'\n", encoding="utf-8")
            output = run_hook(
                "prompt_inspector.py",
                {
                    "cwd": tmp,
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "@recall remember this: prefer local-only memory storage",
                },
            )
            self.assertTrue(output["continue"])
            self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")

            query = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "memory_manager.py"),
                    "--root",
                    tmp,
                    "query",
                    "local memory",
                    "--category",
                    "preferences",
                    "--summary",
                ],
                text=True,
                capture_output=True,
                check=True,
                cwd=ROOT,
            )
            result = json.loads(query.stdout)
            self.assertIn("local-only", result["summary"])

    def test_prompt_inspector_respects_remembered_category_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0.1.0'\n", encoding="utf-8")
            output = run_hook(
                "prompt_inspector.py",
                {
                    "cwd": tmp,
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "@recall remember this: requirements: Release notes stay under docs/manual-release-notes.md.",
                },
            )
            self.assertTrue(output["continue"])

            requirements = query_memory(tmp, "release notes", "requirements")
            preferences = query_memory(tmp, "release notes", "preferences")
            self.assertEqual(len(requirements["results"]), 1)
            self.assertEqual(preferences["results"], [])
            self.assertEqual(requirements["results"][0]["content"], "Release notes stay under docs/manual-release-notes.md.")
            self.assertEqual(requirements["results"][0]["metadata"]["claim_key"], "release_notes.path")

    def test_prompt_inspector_saves_kimi_content_part_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0.1.0'\n", encoding="utf-8")
            output = run_hook_with_args(
                "prompt_inspector.py",
                {
                    "cwd": tmp,
                    "session_id": "kimi-session",
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": [
                        {
                            "type": "text",
                            "text": "@recall remember this: requirements: Kimi content-part prompts must save.",
                        }
                    ],
                },
                "--provider",
                "kimi",
            )
            self.assertIn("RECALL saved memory", output["hookSpecificOutput"]["additionalContext"])

            requirements = query_memory(tmp, "content-part prompts", "requirements")
            self.assertEqual(len(requirements["results"]), 1)
            self.assertEqual(requirements["results"][0]["metadata"]["origin_provider"], "kimi")
            self.assertEqual(requirements["results"][0]["metadata"]["capture_channel"], "hook")

    def test_natural_use_recall_phrase_activates_project_and_buffers_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "package.json").write_text('{"name":"fixture","version":"0.1.0"}', encoding="utf-8")
            output = run_hook(
                "prompt_inspector.py",
                {
                    "cwd": tmp,
                    "session_id": "session-natural",
                    "turn_id": "turn-natural",
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "Use RECALL for this project. We must keep generated release notes under docs/manual-release-notes.md.",
                },
            )
            self.assertTrue(output["continue"])
            events = runtime_events(tmp, "session-natural", "turn-natural")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["category_hint"], "requirements")
            self.assertIn("generated release notes", events[0]["summary"])

    def test_release_notes_correction_supersedes_previous_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0.1.0'\n", encoding="utf-8")
            run_hook(
                "prompt_inspector.py",
                {
                    "cwd": tmp,
                    "session_id": "session-conflict",
                    "turn_id": "turn-original",
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "@recall remember this: requirements: The release notes file must live at docs/manual-release-notes.md.",
                },
            )
            run_hook(
                "stop.py",
                {
                    "cwd": tmp,
                    "session_id": "session-conflict",
                    "turn_id": "turn-original",
                    "hook_event_name": "Stop",
                    "last_assistant_message": "Recorded the original requirement.",
                },
            )
            run_hook(
                "prompt_inspector.py",
                {
                    "cwd": tmp,
                    "session_id": "session-conflict",
                    "turn_id": "turn-correction",
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "Correction: the release notes file should instead live at docs/release/manual-notes.md.",
                },
            )
            run_hook(
                "stop.py",
                {
                    "cwd": tmp,
                    "session_id": "session-conflict",
                    "turn_id": "turn-correction",
                    "hook_event_name": "Stop",
                    "last_assistant_message": "Recorded the corrected requirement.",
                },
            )

            active = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "recall_skill.py"),
                    "--root",
                    tmp,
                    "review-memory",
                    "--category",
                    "requirements",
                    "--status",
                    "active",
                    "--status",
                    "validated",
                    "--limit",
                    "20",
                ],
                text=True,
                capture_output=True,
                check=True,
                cwd=ROOT,
            )
            active_review = json.loads(active.stdout)["review"]
            self.assertEqual(active_review["matched"], 1)
            self.assertIn("docs/release/manual-notes.md", active_review["memories"][0]["summary"])

            superseded = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "recall_skill.py"),
                    "--root",
                    tmp,
                    "review-memory",
                    "--category",
                    "requirements",
                    "--status",
                    "superseded",
                    "--limit",
                    "20",
                ],
                text=True,
                capture_output=True,
                check=True,
                cwd=ROOT,
            )
            superseded_review = json.loads(superseded.stdout)["review"]
            self.assertGreaterEqual(superseded_review["matched"], 1)

    def test_prompt_inspector_ignores_incidental_remembered_word(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = run_hook(
                "prompt_inspector.py",
                {
                    "cwd": tmp,
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "Make a fake project so there is more that can actually be remembered.",
                },
            )
            self.assertEqual(output, {"continue": True})
            result = query_memory(tmp, "actually remembered", "preferences")
            self.assertEqual(result["results"], [])

    def test_prompt_invocation_injects_additional_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "memory_manager.py"),
                    "--root",
                    tmp,
                    "add",
                    "project_state",
                    "RECALL hook tests have a saved project state.",
                    "--status",
                    "active",
                    "--summary",
                    "RECALL hook tests have a saved project state.",
                ],
                check=True,
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            output = run_hook(
                "prompt_inspector.py",
                {
                    "cwd": tmp,
                    "session_id": "session-context",
                    "turn_id": "turn-context",
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "@recall what is the current project state?",
                },
            )
            self.assertTrue(output["continue"])
            self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
            self.assertIn("RECALL hook tests", output["hookSpecificOutput"]["additionalContext"])

    def test_always_recall_mode_injects_without_explicit_invocation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_manager_cmd = [sys.executable, str(ROOT / "scripts" / "memory_manager.py"), "--root", tmp]
            subprocess.run(memory_manager_cmd + ["add", "project_state", "Release train is green.", "--status", "active"], check=True, capture_output=True, text=True, cwd=ROOT)
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "recall_skill.py"), "--root", tmp, "configure-recall", "always"],
                check=True,
                capture_output=True,
                text=True,
                cwd=ROOT,
            )
            activate_recall(tmp, "always-session", "always-turn")

            output = run_hook("prompt_inspector.py", {"cwd": tmp, "prompt": "What is the release state?"})
            self.assertIn("Release train is green", output["hookSpecificOutput"]["additionalContext"])

    def test_relevant_recall_mode_ignores_unrelated_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "memory_manager.py"), "--root", tmp, "add", "architecture", "SQLite stores project memory."],
                check=True,
                capture_output=True,
                text=True,
                cwd=ROOT,
            )
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "recall_skill.py"), "--root", tmp, "configure-recall", "relevant"],
                check=True,
                capture_output=True,
                text=True,
                cwd=ROOT,
            )

            output = run_hook("prompt_inspector.py", {"cwd": tmp, "prompt": "Write a limerick about clouds."})
            self.assertEqual(output, {"continue": True})

    def test_source_blind_category_prompt_receives_project_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "recall_skill.py"),
                    "--root",
                    tmp,
                    "initialize-project",
                ],
                text=True,
                capture_output=True,
                check=True,
                cwd=ROOT,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "recall_skill.py"),
                    "--root",
                    tmp,
                    "save-insight",
                    "requirements",
                    "Generated release notes must stay in docs/manual-release-notes.md.",
                    "--summary",
                    "Generated release notes must stay in docs/manual-release-notes.md.",
                    "--status",
                    "validated",
                ],
                text=True,
                capture_output=True,
                check=True,
                cwd=ROOT,
            )
            output = run_hook(
                "prompt_inspector.py",
                {
                    "cwd": tmp,
                    "session_id": "session-source-blind",
                    "turn_id": "turn-source-blind",
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": (
                        "Without running commands or reading source files, use only automatically provided "
                        "RECALL memory: summarize this fixture project's current requirements and risks."
                    ),
                },
            )
            context = output["hookSpecificOutput"]["additionalContext"]
            self.assertIn("Curated RECALL project memory", context)
            self.assertIn("Generated release notes", context)

    def test_prompt_invocation_excludes_superseded_when_active_context_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "memory_manager.py"),
                    "--root",
                    tmp,
                    "add",
                    "requirements",
                    "Old startup requirement should not appear.",
                    "--summary",
                    "Old startup requirement.",
                    "--tag",
                    "startup",
                    "--status",
                    "superseded",
                ],
                check=True,
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "memory_manager.py"),
                    "--root",
                    tmp,
                    "add",
                    "requirements",
                    "Current startup requirement should appear.",
                    "--summary",
                    "Current startup requirement.",
                    "--tag",
                    "startup",
                    "--status",
                    "active",
                ],
                check=True,
                cwd=ROOT,
                capture_output=True,
                text=True,
            )

            output = run_hook(
                "prompt_inspector.py",
                {
                    "cwd": tmp,
                    "session_id": "session-startup",
                    "turn_id": "turn-startup",
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "@recall startup requirement",
                },
            )
            context = output["hookSpecificOutput"]["additionalContext"]

            self.assertIn("Curated RECALL project memory", context)
            self.assertIn("Current startup requirement", context)
            self.assertNotIn("Old startup requirement", context)

    def test_session_start_is_quiet_even_with_memories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "memory_manager.py"),
                    "--root",
                    tmp,
                    "add",
                    "project_state",
                    "SessionStart should not inject this automatically.",
                    "--summary",
                    "SessionStart should not inject this automatically.",
                ],
                check=True,
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            output = run_hook(
                "session_start.py",
                {"cwd": tmp, "hook_event_name": "SessionStart", "source": "startup"},
            )
            self.assertEqual(output, {"continue": True})

    def test_recall_invocation_is_required_for_hook_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_hook(
                "post_tool_use.py",
                {
                    "cwd": tmp,
                    "session_id": "session-off",
                    "turn_id": "turn-off",
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "python -m unittest discover -s tests"},
                    "tool_response": {"exit_code": 0, "stdout": "Ran 9 tests in 1.2s\nOK", "stderr": ""},
                },
            )
            stop = run_hook(
                "stop.py",
                {
                    "cwd": tmp,
                    "session_id": "session-off",
                    "turn_id": "turn-off",
                    "hook_event_name": "Stop",
                    "last_assistant_message": "Completed tests and changed memory policy.",
                },
            )
            self.assertEqual(stop, {"continue": True})
            self.assertEqual(runtime_events(tmp, "session-off", "turn-off"), [])

    def test_retrieval_only_recall_prompt_does_not_initialize_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = run_hook(
                "prompt_inspector.py",
                {
                    "cwd": tmp,
                    "session_id": "session-readonly",
                    "turn_id": "turn-readonly",
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "@recall what matters here?",
                },
            )
            self.assertIn("initialize this project", output["hookSpecificOutput"]["additionalContext"])
            self.assertFalse((Path(tmp) / ".recall").exists())
            self.assertFalse((Path(tmp) / ".codex_memory").exists())

    def test_malformed_hook_json_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = run_hook_raw("pre_compact.py", '{"cwd": "' + tmp.replace("\\", "\\\\"))
            self.assertEqual(output, {"continue": True})
            result = query_memory(tmp, "cwd", "session_summaries")
            self.assertEqual(result["results"], [])

    def test_post_tool_use_stores_allowed_successful_command_directly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            activate_recall(tmp, "session-test", "turn-test")
            output = run_hook(
                "post_tool_use.py",
                {
                    "cwd": tmp,
                    "session_id": "session-test",
                    "turn_id": "turn-test",
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "python -m unittest discover -s tests"},
                    "tool_response": {
                        "exit_code": 0,
                        "stdout": "line\n" * 200 + "Ran 9 tests in 1.2s\nOK",
                        "stderr": "",
                    },
                },
            )
            self.assertTrue(output["continue"])
            result = query_memory(tmp, "unittest", "commands")
            self.assertEqual(result["results"], [])
            events = runtime_events(tmp, "session-test", "turn-test")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["record_kind"], "test_result")
            self.assertIn("Ran 9 tests", events[0]["summary"])

    def test_post_tool_use_suppresses_exact_duplicate_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            activate_recall(tmp)
            payload = {
                "cwd": tmp,
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "python -m unittest discover -s tests"},
                "tool_response": {"exit_code": 0, "stdout": "Ran 49 tests in 1.0s\nOK", "stderr": ""},
            }
            first = run_hook("post_tool_use.py", payload)
            second = run_hook("post_tool_use.py", payload)
            result = query_memory(tmp, "python unittest", "commands")

            self.assertTrue(first["continue"])
            self.assertEqual(second, {"continue": True})
            self.assertEqual(result["results"], [])
            self.assertEqual(len(runtime_events(tmp, "", "")), 1)

    def test_post_tool_use_replay_uses_delivery_idempotency_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            activate_recall(tmp, "session-replay", "turn-replay")
            payload = {
                "cwd": tmp,
                "session_id": "session-replay",
                "turn_id": "turn-replay",
                "tool_use_id": "tool-123",
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "python -m unittest discover -s tests"},
                "tool_response": {"exit_code": 0, "stdout": "Ran 49 tests in 1.0s\nOK", "stderr": ""},
            }
            run_hook("post_tool_use.py", payload)
            replay = {**payload, "tool_response": {"exit_code": 0, "stdout": "different replay body", "stderr": ""}}
            run_hook("post_tool_use.py", replay)
            result = query_memory(tmp, "python unittest", "commands")

            self.assertEqual(result["results"], [])
            events = runtime_events(tmp, "session-replay", "turn-replay")
            self.assertEqual(len(events), 1)
            self.assertTrue(events[0]["idempotency_key"].startswith("hook:"))

    def test_post_tool_use_links_near_duplicate_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            activate_recall(tmp)
            base = {
                "cwd": tmp,
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "python -m unittest discover -s tests"},
            }
            run_hook(
                "post_tool_use.py",
                {**base, "tool_response": {"exit_code": 0, "stdout": "1 passed", "stderr": ""}},
            )
            run_hook(
                "post_tool_use.py",
                {**base, "tool_response": {"exit_code": 0, "stdout": "2 passed", "stderr": ""}},
            )
            result = query_memory(tmp, "python unittest", "commands")

            self.assertEqual(result["results"], [])
            self.assertGreaterEqual(len(runtime_events(tmp, "", "")), 1)

    def test_post_tool_use_successful_listing_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            activate_recall(tmp)
            output = run_hook(
                "post_tool_use.py",
                {
                    "cwd": tmp,
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "Get-ChildItem -Force"},
                    "tool_response": {
                        "exit_code": 0,
                        "stdout": "\x1b[32;1mMode\x1b[0m Name\n-a--- 1000 README.md\n-a--- 2000 secrets.txt",
                        "stderr": "",
                    },
                },
            )
            self.assertEqual(output, {"continue": True})
            result = query_memory(tmp, "Get-ChildItem", "commands")
            self.assertEqual(result["results"], [])

    def test_pre_compact_uses_event_fields_not_raw_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "recall_skill.py"),
                    "--root",
                    tmp,
                    "configure-capture",
                    "standard",
                ],
                text=True,
                capture_output=True,
                check=True,
                cwd=ROOT,
            )
            activate_recall(tmp, "", "turn-123")
            output = run_hook(
                "pre_compact.py",
                {
                    "cwd": tmp,
                    "hook_event_name": "PreCompact",
                    "turn_id": "turn-123",
                    "trigger": "auto",
                    "summary": "Implemented the release smoke harness and verified plugin validation.",
                },
            )
            self.assertTrue(output["continue"])
            result = query_memory(tmp, "release smoke harness", "session_summaries")
            stored = result["results"][0]
            self.assertIn("release smoke harness", stored["content"])
            self.assertNotIn("hook_event_name", stored["content"])
            self.assertEqual(stored["metadata"]["trigger"], "auto")
            self.assertEqual(stored["metadata"]["turn_id"], "turn-123")

    def test_pre_compact_empty_payload_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "recall_skill.py"),
                    "--root",
                    tmp,
                    "configure-capture",
                    "standard",
                ],
                text=True,
                capture_output=True,
                check=True,
                cwd=ROOT,
            )
            activate_recall(tmp, "", "turn-empty")
            output = run_hook(
                "pre_compact.py",
                {"cwd": tmp, "hook_event_name": "PreCompact", "turn_id": "turn-empty", "trigger": "manual"},
            )
            self.assertEqual(output, {"continue": True})
            result = query_memory(tmp, "turn-empty", "session_summaries")
            self.assertEqual(result["results"], [])

    def test_stop_quiet_mode_hides_finalizer_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            activate_recall(tmp, "session-stop", "turn-stop")
            run_hook(
                "post_tool_use.py",
                {
                    "cwd": tmp,
                    "session_id": "session-stop",
                    "turn_id": "turn-stop",
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "python -m unittest discover -s tests"},
                    "tool_response": {"exit_code": 0, "stdout": "Ran 9 tests in 1.2s\nOK", "stderr": ""},
                },
            )
            output = run_hook(
                "stop.py",
                {
                    "cwd": tmp,
                    "session_id": "session-stop",
                    "hook_event_name": "Stop",
                    "turn_id": "turn-stop",
                    "last_assistant_message": "Completed Task 2 hook parsing and left storage healthy.",
                },
            )
            self.assertTrue(output["continue"])
            self.assertNotIn("decision", output)
            self.assertNotIn("reason", output)
            self.assertNotIn("RECALL_FINALIZER_REQUEST", json.dumps(output))
            result = query_memory(tmp, "Task 2 hook parsing", "project_state")
            self.assertEqual(result["results"], [])
            packet = recall_config.memory_dir(tmp) / "runtime" / "finalizer_requests" / "session-stop-turn-stop.json"
            self.assertFalse(packet.exists())

    def test_stop_quiet_mode_saves_explicit_prompt_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            activate_recall(
                tmp,
                "session-stop",
                "turn-requirement",
                prompt="[@recall](plugin://recall@recall-local) You must keep finalizer internals hidden from users.",
            )
            output = run_hook(
                "stop.py",
                {
                    "cwd": tmp,
                    "session_id": "session-stop",
                    "hook_event_name": "Stop",
                    "turn_id": "turn-requirement",
                    "last_assistant_message": "Implemented quiet Stop finalization.",
                },
            )
            self.assertEqual(output.get("systemMessage"), "RECALL saved 1 memory.")
            self.assertNotIn("decision", output)
            self.assertNotIn("reason", output)
            result = query_memory(tmp, "finalizer internals hidden", "requirements")
            self.assertEqual(len(result["results"]), 1)
            self.assertEqual(result["results"][0]["metadata"]["status"], "validated")

    def test_explicit_recall_requirement_stores_clean_requirement_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            activate_recall(
                tmp,
                "session-clean",
                "turn-clean",
                prompt=(
                    "Use [@recall](plugin://recall@recall-local) for this project. "
                    "We must keep generated release notes under docs/manual-release-notes.md."
                ),
            )
            output = run_hook(
                "stop.py",
                {
                    "cwd": tmp,
                    "session_id": "session-clean",
                    "hook_event_name": "Stop",
                    "turn_id": "turn-clean",
                    "last_assistant_message": "Recorded the project release notes requirement.",
                },
            )
            self.assertEqual(output.get("systemMessage"), "RECALL saved 1 memory.")
            result = query_memory(tmp, "generated release notes", "requirements")
            self.assertEqual(len(result["results"]), 1)
            stored = result["results"][0]["content"]
            self.assertEqual(stored, "We must keep generated release notes under docs/manual-release-notes.md")
            self.assertNotIn("[](-local)", stored)
            self.assertNotIn("Use RECALL", stored)

    def test_conditional_command_memory_is_not_saved_when_verification_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            activate_recall(tmp, "session-conditional", "turn-setup")
            run_hook(
                "prompt_inspector.py",
                {
                    "cwd": tmp,
                    "session_id": "session-conditional",
                    "turn_id": "turn-conditional",
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "The reusable validation command for this project is `python -m pytest`; remember it only if it actually works.",
                },
            )
            run_hook(
                "post_tool_use.py",
                {
                    "cwd": tmp,
                    "session_id": "session-conditional",
                    "turn_id": "turn-conditional",
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "python -m pytest"},
                    "tool_response": {"exit_code": 1, "stdout": "", "stderr": "ERROR: file or directory not found: tests"},
                },
            )
            output = run_hook(
                "stop.py",
                {
                    "cwd": tmp,
                    "session_id": "session-conditional",
                    "turn_id": "turn-conditional",
                    "hook_event_name": "Stop",
                    "last_assistant_message": "The command failed, so I did not remember it as reusable.",
                },
            )

            self.assertEqual(output.get("systemMessage"), "RECALL saved 1 memory.")
            self.assertEqual(query_memory(tmp, "reusable validation command", "decisions")["results"], [])
            self.assertEqual(query_memory(tmp, "python pytest reusable", "commands")["results"], [])
            failures = query_memory(tmp, "file or directory not found", "debug_history")
            self.assertEqual(len(failures["results"]), 1)
            self.assertIn("ERROR", failures["results"][0]["content"])

    def test_stop_empty_last_message_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = run_hook(
                "stop.py",
                {"cwd": tmp, "hook_event_name": "Stop", "turn_id": "turn-stop", "last_assistant_message": None},
            )
            self.assertEqual(output, {"continue": True})
            result = query_memory(tmp, "turn-stop", "project_state")
            self.assertEqual(result["results"], [])

    def test_post_tool_use_stores_compact_bash_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            activate_recall(tmp, "", "turn-bash-failure")
            output = run_hook(
                "post_tool_use.py",
                {
                    "cwd": tmp,
                    "hook_event_name": "PostToolUse",
                    "turn_id": "turn-bash-failure",
                    "tool_name": "Bash",
                    "tool_input": {"command": "python -m unittest tests.test_missing"},
                    "tool_response": {
                        "exit_code": 1,
                        "stdout": "",
                        "stderr": "FAILED tests/test_missing.py::MissingTest - AssertionError: boom",
                    },
                },
            )
            self.assertTrue(output["continue"])
            result = query_memory(tmp, "MissingTest boom", "debug_history")
            self.assertEqual(result["results"], [])
            events = runtime_events(tmp, "", "turn-bash-failure")
            self.assertEqual(len(events), 1)
            self.assertIn("AssertionError", events[0]["details"])

    def test_post_tool_use_failure_uses_project_activation_when_turn_activation_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            activate_recall(tmp, "session-project-active", "turn-setup")
            output = run_hook(
                "post_tool_use.py",
                {
                    "cwd": tmp,
                    "session_id": "session-project-active",
                    "turn_id": "turn-project-active",
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "python -m pytest tests\\does_not_exist.py"},
                    "tool_response": {
                        "exit_code": 1,
                        "stdout": "",
                        "stderr": "ERROR: file or directory not found: tests\\does_not_exist.py",
                    },
                },
            )
            self.assertTrue(output["continue"])
            events = runtime_events(tmp, "session-project-active", "turn-project-active")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["category_hint"], "debug_history")
            self.assertEqual(events[0]["record_kind"], "failure")

            stop = run_hook(
                "stop.py",
                {
                    "cwd": tmp,
                    "session_id": "session-project-active",
                    "turn_id": "turn-project-active",
                    "hook_event_name": "Stop",
                    "last_assistant_message": "The intentionally failing command failed as expected.",
                },
            )
            self.assertEqual(stop.get("systemMessage"), "RECALL saved 1 memory.")
            result = query_memory(tmp, "does_not_exist", "debug_history")
            self.assertEqual(len(result["results"]), 1)

    def test_kimi_post_tool_use_failure_payload_buffers_provider_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_hook_with_args(
                "prompt_inspector.py",
                {
                    "cwd": tmp,
                    "session_id": "kimi-session",
                    "turn_id": "kimi-turn",
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "@recall initialize this project",
                },
                "--provider",
                "kimi",
            )
            output = run_hook_with_args(
                "post_tool_use.py",
                {
                    "cwd": tmp,
                    "session_id": "kimi-session",
                    "turn_id": "kimi-turn",
                    "hook_event_name": "PostToolUseFailure",
                    "tool_name": "Bash",
                    "tool_input": {"command": "python -m pytest tests/missing.py"},
                    "error": "failed with AssertionError: missing tests",
                },
                "--provider",
                "kimi",
            )
            events = runtime_events(tmp, "kimi-session", "kimi-turn")

            self.assertEqual(output, {"continue": True})
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["origin_provider"], "kimi")
            self.assertEqual(events[0]["capture_channel"], "hook")
            self.assertEqual(events[0]["exit_code"], 1)
            self.assertEqual(events[0]["signal"], "test_fail")

    def test_post_tool_use_stores_apply_patch_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            activate_recall(tmp, "", "turn-patch")
            output = run_hook(
                "post_tool_use.py",
                {
                    "cwd": tmp,
                    "hook_event_name": "PostToolUse",
                    "turn_id": "turn-patch",
                    "tool_name": "apply_patch",
                    "tool_input": {"command": "*** Begin Patch\n*** Update File: README.md\n@@\n+ok\n*** End Patch"},
                    "tool_response": {"success": True, "stdout": "Done!"},
                },
            )
            self.assertTrue(output["continue"])
            result = query_memory(tmp, "README apply_patch", "commands")
            self.assertEqual(result["results"], [])
            events = runtime_events(tmp, "", "turn-patch")
            self.assertEqual(len(events), 1)
            self.assertIn("README.md", events[0]["summary"])

    def test_post_tool_use_redacts_secret_like_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            activate_recall(tmp)
            run_hook(
                "post_tool_use.py",
                {
                    "cwd": tmp,
                    "hook_event_name": "PostToolUse",
                    "tool_input": {"command": "deploy"},
                    "tool_response": {"exit_code": 1, "stderr": "failed with token=dummy-secret-value"},
                },
            )
            result = query_memory(tmp, "deploy failed token", "debug_history")
            self.assertEqual(result["results"], [])
            events = runtime_events(tmp, "", "")
            self.assertEqual(len(events), 1)
            self.assertIn("[REDACTED]", events[0]["details"])


if __name__ == "__main__":
    unittest.main()
