from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import config as recall_config  # noqa: E402


SCRIPT_MODULES: dict[Path, object] = {}


def load_script_module(script: Path):
    cached = SCRIPT_MODULES.get(script)
    if cached is not None:
        return cached
    module_name = f"_recall_test_script_{len(SCRIPT_MODULES)}_{script.stem}"
    spec = importlib.util.spec_from_file_location(module_name, script)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    SCRIPT_MODULES[script] = module
    return module


def run_script_in_process(script: Path, args: list[str] | None = None, stdin: str = "") -> str:
    old_argv = sys.argv[:]
    old_stdin = sys.stdin
    old_cwd = Path.cwd()
    stdout = io.StringIO()
    script_dir = str(script.parent)
    inserted_path = False
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
        inserted_path = True
    try:
        sys.argv = [str(script), *(args or [])]
        sys.stdin = io.StringIO(stdin)
        os.chdir(ROOT)
        with contextlib.redirect_stdout(stdout):
            try:
                module = load_script_module(script)
                main = getattr(module, "main", None) if module is not None else None
                if callable(main):
                    main()
                else:
                    runpy.run_path(str(script), run_name="__main__")
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
                if code != 0:
                    raise
        return stdout.getvalue()
    finally:
        os.chdir(old_cwd)
        sys.stdin = old_stdin
        sys.argv = old_argv
        if inserted_path:
            try:
                sys.path.remove(script_dir)
            except ValueError:
                pass


def run_hook(script: str, payload: dict) -> dict:
    return run_hook_raw(script, json.dumps(payload))


def run_hook_with_args(script: str, payload: dict, *args: str) -> dict:
    output = run_script_in_process(ROOT / "hooks" / "scripts" / script, list(args), json.dumps(payload))
    return json.loads(output)


def run_hook_subprocess(script: str, payload: dict, *args: str) -> dict:
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
    output = run_script_in_process(ROOT / "hooks" / "scripts" / script, stdin=raw)
    return json.loads(output)


def query_memory(root: str, query: str, category: str) -> dict:
    return run_memory_manager(root, "query", query, "--category", category)


def run_memory_manager(root: str, *args: str) -> dict:
    output = run_script_in_process(ROOT / "scripts" / "memory_manager.py", ["--root", root, *args])
    text = output.strip()
    if not text:
        return {}
    if text.startswith("{") or text.startswith("["):
        return json.loads(text)
    return {"output": text}


def run_recall_skill(root: str, *args: str) -> dict:
    output = run_script_in_process(ROOT / "scripts" / "recall_skill.py", ["--root", root, *args])
    text = output.strip()
    if not text:
        return {}
    if text.startswith("{") or text.startswith("["):
        return json.loads(text)
    return {"output": text}


def runtime_events(root: str, session_id: str, turn_id: str) -> list[dict]:
    import turn_policy
    import turn_buffer
    policy = turn_policy.policy_status(root, session_id or None, turn_id or None)
    safe_session = session_id or str(policy.get("session_id") or "session")
    safe_turn = turn_id or str(policy.get("turn_id") or "turn")
    path = turn_buffer.turn_events_path(root, safe_session, safe_turn)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def activate_recall(root: str, session_id: str = "", turn_id: str = "", prompt: str | None = None) -> dict:
    recall_config.activate_project(root, activated_by="test")
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

            result = run_memory_manager(tmp, "query", "local memory", "--category", "preferences", "--summary")
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

    def test_release_notes_correction_keeps_conflicting_requirements_current(self) -> None:
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

            active_review = run_recall_skill(
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
            )["review"]
            self.assertEqual(active_review["matched"], 2)
            summaries = {memory["summary"] for memory in active_review["memories"]}
            self.assertTrue(any("docs/manual-release-notes.md" in summary for summary in summaries))
            self.assertTrue(any("docs/release/manual-notes.md" in summary for summary in summaries))

            superseded_review = run_recall_skill(
                tmp,
                "review-memory",
                "--category",
                "requirements",
                "--status",
                "superseded",
                "--limit",
                "20",
            )["review"]
            self.assertEqual(superseded_review["matched"], 0)

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
            run_memory_manager(
                tmp,
                "add",
                "project_state",
                "RECALL hook tests have a saved project state.",
                "--status",
                "active",
                "--summary",
                "RECALL hook tests have a saved project state.",
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
            run_memory_manager(tmp, "add", "project_state", "Release train is green.", "--status", "active")
            run_recall_skill(tmp, "configure-recall", "always")
            activate_recall(tmp, "always-session", "always-turn")

            output = run_hook("prompt_inspector.py", {"cwd": tmp, "prompt": "What is the release state?"})
            self.assertIn("Release train is green", output["hookSpecificOutput"]["additionalContext"])

    def test_relevant_recall_mode_ignores_unrelated_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_memory_manager(tmp, "add", "architecture", "SQLite stores project memory.")
            run_recall_skill(tmp, "configure-recall", "relevant")

            output = run_hook("prompt_inspector.py", {"cwd": tmp, "prompt": "Write a limerick about clouds."})
            self.assertEqual(output, {"continue": True})

    def test_source_blind_category_prompt_receives_project_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_recall_skill(tmp, "initialize-project")
            run_recall_skill(
                tmp,
                "save-insight",
                "requirements",
                "Generated release notes must stay in docs/manual-release-notes.md.",
                "--summary",
                "Generated release notes must stay in docs/manual-release-notes.md.",
                "--status",
                "validated",
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
            run_memory_manager(
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
            )
            run_memory_manager(
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
            run_memory_manager(
                tmp,
                "add",
                "project_state",
                "SessionStart should not inject this automatically.",
                "--summary",
                "SessionStart should not inject this automatically.",
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
            run_recall_skill(tmp, "configure-capture", "standard")
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
            run_recall_skill(tmp, "configure-capture", "standard")
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
            self.assertEqual(result["results"][0]["metadata"]["status"], "active")  # F13: asserted intent is unverified.

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

    def test_post_tool_use_failure_cannot_bypass_an_established_prompt_scope(self) -> None:
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
            self.assertEqual(output.get("memory_action"), "disabled")
            events = runtime_events(tmp, "session-project-active", "turn-project-active")
            self.assertEqual(events, [])

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
            self.assertEqual(stop.get("memory_action"), "disabled")
            result = query_memory(tmp, "does_not_exist", "debug_history")
            self.assertEqual(result["results"], [])

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

    def test_kimi_json_wrapper_failure_finalizes_as_distilled_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_hook_with_args(
                "prompt_inspector.py",
                {
                    "cwd": tmp,
                    "session_id": "kimi-json-session",
                    "turn_id": "kimi-json-turn",
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "@recall initialize this project",
                },
                "--provider",
                "kimi",
            )
            wrapper = json.dumps(
                {
                    "code": "internal",
                    "message": "error: Failed to spawn: `pytest`\n  Caused by: program not found\nCommand failed with exit code: 2.",
                    "retryable": False,
                }
            )
            run_hook_with_args(
                "post_tool_use.py",
                {
                    "cwd": tmp,
                    "session_id": "kimi-json-session",
                    "turn_id": "kimi-json-turn",
                    "hook_event_name": "PostToolUseFailure",
                    "tool_name": "Bash",
                    "tool_input": {"command": "uv run pytest -q --tb=short"},
                    "error": wrapper,
                },
                "--provider",
                "kimi",
            )
            events = runtime_events(tmp, "kimi-json-session", "kimi-json-turn")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["summary"], "error: Failed to spawn: `pytest`")
            self.assertNotIn('{"code"', events[0]["details"])

            stop = run_hook_with_args(
                "stop.py",
                {
                    "cwd": tmp,
                    "session_id": "kimi-json-session",
                    "turn_id": "kimi-json-turn",
                    "hook_event_name": "Stop",
                    "last_assistant_message": "The Kimi pytest command failed because pytest was not available.",
                },
                "--provider",
                "kimi",
            )
            self.assertEqual(stop.get("systemMessage"), "RECALL saved 1 memory.")
            result = query_memory(tmp, "pytest not available", "debug_history")
            self.assertEqual(len(result["results"]), 1)
            stored = result["results"][0]["content"]
            self.assertIn("Failed to spawn", stored)
            self.assertNotIn('{"code"', stored)
            self.assertEqual(result["results"][0]["metadata"]["source"], "finalizer")

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


class ConservativePromptAdmissionTests(unittest.TestCase):
    """Hand-reviewed contrasts exercise admission, buffering, and durable Stop writes."""

    def capture(self, root: str, prompt: str, *, explicit: bool = False) -> list:
        import storage

        recall_config.activate_project(root)
        recall_config.set_capture_mode("standard", root)
        payload = {"cwd": root, "session_id": "admission-session", "turn_id": "admission-turn"}
        submitted = run_hook("prompt_inspector.py", {
            **payload, "hook_event_name": "UserPromptSubmit", "prompt": prompt,
        })
        self.assertTrue(submitted["continue"])
        stop = run_hook("stop.py", {
            **payload, "hook_event_name": "Stop", "last_assistant_message": "I will investigate.",
        })
        self.assertNotIn("failed:", stop.get("systemMessage", ""))
        records = list(storage.iter_records(root))
        if records and not explicit:
            self.assertEqual(records[0].metadata["session_id"], "admission-session")
            self.assertEqual(records[0].metadata["turn_id"], "admission-turn")
        # Redelivery cannot add records or confirmations.
        replay = run_hook("stop.py", {**payload, "hook_event_name": "Stop"})
        if submitted.get("memory_action") == "disabled":
            self.assertEqual(replay["action"], "disabled")
            self.assertEqual(replay["reason"], "task_no_memory")
        else:
            self.assertEqual(replay, {"continue": True})
        self.assertEqual([(r.id, r.metadata) for r in storage.iter_records(root)],
                         [(r.id, r.metadata) for r in records])
        return records

    def test_unresolved_and_transient_prompts_do_not_become_project_truth(self) -> None:
        prompts = [
            "Actually, I have no idea whether the integration tests are passing. What does that failure mean?",
            "The local WSL dependency mount is no longer available. Why is that happening?",
            "The project dependency mount is no longer available. Why is that happening?",
            "Are the integration tests passing, and what does that failure mean?",
            "I agree the importer is live, but the integration tests are failing. Is that failure still relevant or what does it mean?",
            "Maybe we will use PostgreSQL instead of SQLite for this project.",
            "Maybe we should migrate. We will use JSONL for this project.",
            "Let's use PostgreSQL instead of SQLite for this project.",
            "Proposal: We will use JSONL for this project. Release notes must live in docs/example.md.",
            "Actually, should we replace SQLite with JSONL for the project",
            'Example text: "We must keep release notes at docs/example.md."',
            "'We must keep release notes at docs/example.md.\nThe project must use JSONL.'",
            "> We accepted docs/example.md as the release notes path.",
            "```text\nWe must use docs/example.md for release notes.\n```",
            "For this task, you must output only JSON.",
            "You must answer this question in one sentence.",
            "Do not save memory this turn.",
            "Actually, I must take my daughter to school tomorrow.",
            "We will discuss my career in a future interview.",
            "We have not decided to use JSONL for this project.",
        ]
        for prompt in prompts:
            with self.subTest(prompt=prompt), tempfile.TemporaryDirectory() as tmp:
                self.assertEqual(self.capture(tmp, prompt), [])

    def test_multiline_condition_is_not_detached_from_runtime_rule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.capture(tmp, "If credentials are missing,\nThe API must return HTTP 401."), [])

    def test_wrapped_approval_cannot_become_unconditional_path(self) -> None:
        text = "Release notes must live in docs/new-release.md\nif the migration is approved."
        for explicit in (False, True):
            with self.subTest(explicit=explicit), tempfile.TemporaryDirectory() as tmp:
                prompt = "@recall remember this: requirements: " + text if explicit else text
                self.assertEqual(self.capture(tmp, prompt, explicit=explicit), [])

    def test_accepted_facts_survive_without_surrounding_uncertainty(self) -> None:
        cases = [
            ("We accepted docs/release-notes.md as the release notes path.",
             "We accepted docs/release-notes.md as the release notes path", "decisions"),
            ("Correction: the release notes file should instead live at docs/release/manual-notes.md.",
             "Correction: the release notes file should instead live at docs/release/manual-notes.md", "requirements"),
            ("Actually, this project no longer uses JSONL; it uses SQLite.",
             "Actually, this project no longer uses JSONL; it uses SQLite", "decisions"),
            ("The retry logic must never exceed three attempts; that is a hard requirement.",
             "The retry logic must never exceed three attempts; that is a hard requirement", "requirements"),
            ("We accepted docs/release-notes.md as the release notes path. Should we change the test command?",
             "We accepted docs/release-notes.md as the release notes path", "decisions"),
            ("We accepted docs/release-notes.md as the release notes path. What proposal should we discuss?",
             "We accepted docs/release-notes.md as the release notes path", "decisions"),
            ("Actually, should we use JSONL? The project must keep secrets out of memory.",
             "The project must keep secrets out of memory", "requirements"),
            ("The API must preserve the literal `why?` in error messages.",
             "The API must preserve the literal `why?` in error messages", "requirements"),
            ("Do not make network calls from this project.",
             "Do not make network calls from this project", "requirements"),
            ("The parser must preserve RECALL_LITERAL_0 and `why?` verbatim.",
             "The parser must preserve RECALL_LITERAL_0 and `why?` verbatim", "requirements"),
        ]
        for prompt, content, category in cases:
            with self.subTest(prompt=prompt), tempfile.TemporaryDirectory() as tmp:
                records = self.capture(tmp, prompt)
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0].content, content)
                self.assertEqual(records[0].metadata["summary"], content)
                self.assertEqual(records[0].metadata["details"], content)
                self.assertEqual(records[0].category, category)
                self.assertEqual(records[0].metadata["status"], "active")  # F13: keep admission, require observed verification.

    def test_memory_cue_preserves_facts_but_does_not_certify_questions(self) -> None:
        cases = [
            ("@recall remember this: requirements: Release notes stay under docs/manual-release-notes.md.", True),
            ("@recall remember this: decisions: Should we replace SQLite with JSONL for this project?", False),
            ("@recall remember this: decisions: Maybe we will use JSONL for this project.", False),
            ("> @recall remember this: requirements: Release notes must live in docs/example.md.", False),
            ('Example: "@recall remember this: requirements: Release notes must live in docs/example.md."', False),
        ]
        for prompt, expected in cases:
            with self.subTest(prompt=prompt), tempfile.TemporaryDirectory() as tmp:
                self.assertEqual(bool(self.capture(tmp, prompt, explicit=True)), expected)

    def test_section_labels_are_not_prompt_facts(self) -> None:
        import capture_policy

        for level in range(1, 7):
            for label in ("Accepted policy", "Approved policy", "Required release policy"):
                with self.subTest(level=level, label=label):
                    self.assertIsNone(capture_policy.classify_prompt_event(f"{'#' * level} {label}"))

    def test_section_labels_preserve_requirement_through_stop(self) -> None:
        fact = "Release notes must live in docs/accepted.md."
        section = "## Accepted policy\n\n" + fact
        prompts = [
            section,
            "## Accepted policy\n" + fact,
            "# Approved policy #\n\n" + fact,
            "###### Required release policy\n\n" + fact,
            "Here are example instructions:\n\nRelease notes must live in docs/example.md.\n\n" + section,
            "## Example instructions\n\nRelease notes must live in docs/example.md.\n\n" + section,
            "### Example instructions\n\n#### Accepted policy\n"
            "@recall remember this: requirements: Release notes must live in docs/example.md.\n\n" + section,
        ]
        for prompt in prompts:
            with self.subTest(prompt=prompt), tempfile.TemporaryDirectory() as tmp:
                records = self.capture(tmp, prompt)
                self.assertEqual(len(records), 1)
                record = records[0]
                self.assertEqual(record.category, "requirements")
                self.assertEqual(record.content, fact.rstrip("."))
                self.assertEqual(record.metadata["summary"], fact.rstrip("."))
                self.assertEqual(record.metadata["details"], fact.rstrip("."))
                self.assertEqual(record.metadata["status"], "active")  # F13: accepted user text alone cannot validate.
                self.assertEqual(record.metadata["claim_key"], "release_notes.path")
                self.assertEqual(record.metadata["claim_value"], "docs/accepted.md")

    def test_section_labels_do_not_promote_uncommitted_bodies(self) -> None:
        bodies = [
            "",
            "Should release notes live in docs/accepted.md?",
            "Maybe release notes must live in docs/accepted.md.",
            "Release notes must live in docs/accepted.md if the migration is approved.",
            "Release notes must live in docs/accepted.md\nif the migration is approved.",
            "For this session only, the project must use JSONL.",
        ]
        prompts = ["## Accepted policy\n\n" + body for body in bodies]
        prompts.append("## Example instructions\n\n### Accepted policy\n\n"
                       "Release notes must live in docs/example.md.")
        for prompt in prompts:
            with self.subTest(prompt=prompt), tempfile.TemporaryDirectory() as tmp:
                self.assertEqual(self.capture(tmp, prompt), [])

    def test_followup_conditional_choices_and_example_scope_through_stop(self) -> None:
        # Fixed review set plus contrasts hand-reviewed before target execution.
        cases = [
            ('accepted_path', 'We accepted docs/release-notes.md as the release notes path.', True, None),
            ('path_correction', 'Correction: the release notes file should instead live at docs/release/manual-notes.md.', True, None),
            ('durable_requirement', 'The retry logic must never exceed 3 attempts; this is a hard requirement.', True, None),
            ('question_correction', 'Actually, I have no idea whether the integration tests are passing. What does that failure mean?', False, None),
            ('question_mount', 'The local WSL dependency mount is no longer available. Why is that happening?', False, None),
            ('ordinary_question', 'Are the integration tests passing, and what does that failure mean?', False, None),
            ('proposal', 'Maybe we will use PostgreSQL instead of SQLite for this project.', False, None),
            ('quoted_example', 'Example text: "We must keep release notes at docs/example.md."', False, None),
            ('turn_format', 'For this task, you must output only JSON.', False, None),
            ('personal', 'Actually, I must take my daughter to school tomorrow.', False, None),
            ('inline_literal', 'The API must preserve the literal `why?` in error messages.', True, None),
            ('fact_then_question', 'We accepted docs/release-notes.md as the release notes path. Should we change the build command?', True, None),
            ('explicit_fact', '@recall remember this: requirements: Release notes stay under docs/manual-release-notes.md.', True, None),
            ('explicit_question', '@recall remember this: decisions: Should we use SQLite for this project?', False, None),
            ('conditional_leading', 'If the benchmark passes, we will use SQLite for this project.', False, None),
            ('conditional_trailing', 'We will use SQLite for this project if the benchmark passes.', False, None),
            ('conditional_path', 'Release notes must live in docs/new-release.md if the migration is approved.', False, None),
            ('conditional_explicit', '@recall remember this: decisions: We will use SQLite for this project if the benchmark passes.', False, None),
            ('example_header', 'Here are example instructions:\nRelease notes must live in docs/example.md.', False, None),
            ('example_blank_line', 'Example instructions:\n\nRelease notes must live in docs/example.md.', False, None),
            ('fenced_example', 'Here are example instructions:\n```text\nRelease notes must live in docs/example.md.\n```', False, None),
            ('session_control', 'For this session only, the project must use JSONL.', False, None),
            ('accepted_database', 'We will use SQLite for this project.', True, None),
            ('accepted_project_correction', 'Actually, this project no longer uses JSONL; it uses SQLite.', True, None),
            ('explicit_verified_command', '@recall remember this: commands: The verified test command is `npm test`.', True, None),
            ('quoted_explicit', '> @recall remember this: requirements: Release notes must live in docs/example.md.', False, None),
            ('migration_leading', 'If the migration is approved, release notes must live in docs/new-release.md.', False, None),
            ('migration_explicit', '@recall remember this: requirements: Release notes must live in docs/new-release.md if the migration is approved.', False, None),
            ('runtime_trailing', 'The API must return HTTP 401 if credentials are missing.', True, None),
            ('runtime_leading', 'If credentials are missing, the API must return HTTP 401.', True, None),
            ('runtime_explicit', '@recall remember this: requirements: The API must return HTTP 401 if credentials are missing.', True, None),
            ('runtime_pending_approval', 'The API must return HTTP 401 if the migration is approved.', False, None),
            ('fact_before_example', 'Release notes must live in docs/accepted.md.\n\nHere are example instructions:\n\nRelease notes must live in docs/example.md.', True, 'Release notes must live in docs/accepted.md'),
            ('fact_after_example', 'Example instructions:\n\nRelease notes must live in docs/example.md.\nEnd example.\n\nRelease notes must live in docs/accepted.md.', True, 'Release notes must live in docs/accepted.md'),
            ('markdown_example_scope', '## Example instructions\n\nRelease notes must live in docs/example.md.\n\n## Accepted requirements\n\nRelease notes must live in docs/accepted.md.', True, 'Release notes must live in docs/accepted.md'),
            ('nested_example_heading', '## Example instructions\n\n### Storage\n\nThe project must use JSONL.', False, None),
            ('example_explicit_cue', 'Here are example instructions:\n\n@recall remember this: requirements: Release notes must live in docs/example.md.', False, None),
            ('session_explicit', '@recall remember this: requirements: For this session only, the project must use JSONL.', False, None),
            ('inline_if_literal', 'The parser must preserve the literal `if the benchmark passes` in error messages.', True, None),
            ('quoted_then_fact', '> Release notes must live in docs/example.md.\n\nRelease notes must live in docs/accepted.md.', True, 'Release notes must live in docs/accepted.md'),
            ('fenced_then_fact', '```text\nRelease notes must live in docs/example.md.\n```\n\nRelease notes must live in docs/accepted.md.', True, 'Release notes must live in docs/accepted.md'),
            ('conditional_then_fact', 'We will use SQLite for this project if the benchmark passes.\n\nRelease notes must live in docs/accepted.md.', True, 'Release notes must live in docs/accepted.md'),
        ]
        for name, prompt, expected, expected_content in cases:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmp:
                explicit = prompt.startswith("@recall")
                records = self.capture(tmp, prompt, explicit=explicit)
                self.assertEqual(bool(records), expected)
                if not expected:
                    continue
                self.assertEqual(len(records), 1)
                record = records[0]
                self.assertEqual(record.metadata["status"], "active")  # F13: preserve all content and claim checks below.
                if expected_content:
                    self.assertEqual(record.content, expected_content)
                    self.assertEqual(record.metadata["summary"], expected_content)
                    self.assertEqual(record.metadata["details"], expected_content)
                    self.assertEqual(record.metadata["claim_key"], "release_notes.path")
                    self.assertEqual(record.metadata["claim_value"], "docs/accepted.md")
                if name.startswith("runtime"):
                    self.assertIn("credentials are missing", record.content)
                    self.assertNotIn("claim_key", record.metadata)

    def test_stop_rechecks_conditional_and_framed_legacy_candidates(self) -> None:
        import storage
        import turn_buffer

        prompts = [
            "Release notes must live in docs/new-release.md if the migration is approved.",
            "If the migration is approved, release notes must live in docs/new-release.md.",
            "We will use SQLite for this project if the benchmark passes.",
            "Here are example instructions:\nRelease notes must live in docs/example.md.",
            "Example instructions:\n\nRelease notes must live in docs/example.md.",
            "For this session only, the project must use JSONL.",
        ]
        for prompt in prompts:
            with self.subTest(prompt=prompt), tempfile.TemporaryDirectory() as tmp:
                recall_config.activate_project(tmp)
                turn_buffer.mark_active(tmp, "legacy", "followup", "legacy prompt")
                turn_buffer.append_event(tmp, "legacy", "followup", {
                    "durable_candidate": True, "signal": "explicit_requirement",
                    "summary": prompt, "details": prompt, "category_hint": "requirements",
                    "explicit_user_evidence": True, "confidence": 1.0,
                    "claim_key": "release_notes.path", "claim_value": "docs/new-release.md",
                })
                result = run_hook("stop.py", {"cwd": tmp, "session_id": "legacy", "turn_id": "followup", "hook_event_name": "Stop"})
                self.assertNotIn("failed:", result.get("systemMessage", ""))
                self.assertEqual(list(storage.iter_records(tmp)), [])

    def test_stop_rechecks_legacy_prompt_candidates_before_validation(self) -> None:
        import storage
        import turn_buffer

        with tempfile.TemporaryDirectory() as tmp:
            recall_config.activate_project(tmp)
            turn_buffer.mark_active(tmp, "legacy", "candidate", "legacy prompt")
            turn_buffer.append_event(tmp, "legacy", "candidate", {
                "durable_candidate": True, "signal": "explicit_correction",
                "summary": "Actually, should the project replace SQLite?",
                "details": "Actually, should the project replace SQLite?",
                "category_hint": "decisions", "explicit_user_evidence": True,
                "confidence": 1.0,
            })
            run_hook("stop.py", {"cwd": tmp, "session_id": "legacy", "turn_id": "candidate", "hook_event_name": "Stop"})
            self.assertEqual(list(storage.iter_records(tmp)), [])

    def test_stop_does_not_invent_explicit_user_evidence(self) -> None:
        stop = load_script_module(ROOT / "hooks/scripts/stop.py")
        card = stop.quiet_card_from_event({
            "signal": "explicit_requirement", "category_hint": "requirements",
            "summary": "The project must preserve release notes.",
            "details": "The project must preserve release notes.",
            "explicit_user_evidence": False, "confidence": 1.0,
        }, session_id="session", turn_id="turn")
        self.assertIsNotNone(card)
        self.assertEqual(card["status"], "active")
        self.assertFalse(card["explicit_user_evidence"])


if __name__ == "__main__":
    unittest.main()
