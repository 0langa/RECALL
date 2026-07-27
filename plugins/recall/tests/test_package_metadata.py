from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]


class PackageMetadataTests(unittest.TestCase):
    def test_hooks_json_uses_default_plugin_hook_path_shape(self) -> None:
        payload = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        hooks = payload["hooks"]
        self.assertIn("SessionStart", hooks)
        self.assertIn("UserPromptSubmit", hooks)
        self.assertIn("PostToolUse", hooks)
        self.assertIn("PreCompact", hooks)
        self.assertIn("Stop", hooks)

        for matcher_groups in hooks.values():
            for group in matcher_groups:
                for hook in group["hooks"]:
                    self.assertEqual(hook["type"], "command")
                    # Claude Code sets ${CLAUDE_PLUGIN_ROOT}, not ${PLUGIN_ROOT}
                    # (Codex's convention) — Claude Code leaves PLUGIN_ROOT
                    # unset entirely, which previously caused hook commands to
                    # resolve to a bogus path (confirmed live: an unset
                    # ${PLUGIN_ROOT} expanded to empty in Git Bash, and MSYS
                    # path translation turned the resulting leading "/" into
                    # the Git-for-Windows install root). Both variables must
                    # be supported so Codex (sets PLUGIN_ROOT) and Claude Code
                    # (sets CLAUDE_PLUGIN_ROOT) both resolve correctly from
                    # this one shared file.
                    self.assertIn("${CLAUDE_PLUGIN_ROOT:-$PLUGIN_ROOT}", hook["command"])
                    self.assertIn("os.environ.get('CLAUDE_PLUGIN_ROOT')", hook["commandWindows"])
                    self.assertIn("os.environ['PLUGIN_ROOT']", hook["commandWindows"])
                    self.assertNotIn("%PLUGIN_ROOT%", hook["commandWindows"])

    def test_no_unsupported_update_categories_hook_surface(self) -> None:
        payload = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        self.assertNotIn("UpdateCategories", payload["hooks"])
        self.assertFalse((ROOT / "hooks" / "scripts" / "update_categories.py").exists())
        self.assertTrue((ROOT / "scripts" / "update_categories.py").is_file())

    def test_repo_does_not_ship_local_marketplace_manifest(self) -> None:
        self.assertFalse((REPO_ROOT / ".agents" / "plugins" / "marketplace.json").exists())

    def test_manifest_public_surface_metadata_is_present(self) -> None:
        payload = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        interface = payload["interface"]
        self.assertEqual(payload["version"], "1.5.3")
        self.assertEqual(payload["homepage"], "https://github.com/0langa/RECALL")
        self.assertEqual(payload["repository"], "https://github.com/0langa/RECALL")
        self.assertEqual(interface["websiteURL"], "https://github.com/0langa/RECALL")
        self.assertEqual(
            interface["privacyPolicyURL"],
            "https://github.com/0langa/RECALL/blob/main/plugins/recall/docs/PRIVACY.md",
        )
        self.assertEqual(
            interface["termsOfServiceURL"],
            "https://github.com/0langa/RECALL/blob/main/plugins/recall/docs/TERMS.md",
        )
        self.assertEqual(interface["composerIcon"], "./assets/icon.png")
        self.assertEqual(interface["logo"], "./assets/logo.png")
        self.assertTrue((ROOT / "assets" / "icon.png").is_file())
        self.assertTrue((ROOT / "assets" / "logo.png").is_file())
        self.assertTrue((ROOT / "docs" / "PRIVACY.md").is_file())
        self.assertTrue((ROOT / "docs" / "TERMS.md").is_file())

    def test_kimi_manifest_declares_supported_runtime_surface(self) -> None:
        payload = json.loads((ROOT / "kimi.plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["name"], "recall")
        self.assertEqual(payload["skills"], "./skills/")
        self.assertEqual(payload["sessionStart"]["skill"], "using-recall")
        self.assertNotIn("hooks", payload)
        self.assertNotIn("tools", payload)
        self.assertNotIn("commands", payload)
        self.assertIn("recall", payload["mcpServers"])
        server = payload["mcpServers"]["recall"]
        self.assertEqual(server["cwd"], "./")
        self.assertEqual(server["args"], ["./scripts/kimi_mcp_server.py"])
        self.assertTrue((ROOT / "scripts" / "kimi_mcp_server.py").is_file())

    def test_claude_code_manifest_reuses_shared_skills_hooks_and_mcp(self) -> None:
        # Full manifest field assertions (mcpServers path shape, provider env)
        # live in tests/test_claude_code_adapter.py to avoid duplicate,
        # divergence-prone assertions across two files.
        payload = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["name"], "recall")
        self.assertEqual(payload["skills"], "./skills/")
        # hooks/hooks.json is intentionally NOT declared: Claude Code loads
        # it automatically by convention, and an explicit "hooks" field
        # pointing at the same path fails plugin load with "Duplicate hooks
        # file detected" (verified via `claude plugin install`).
        self.assertNotIn("hooks", payload)
        self.assertNotIn("commands", payload)
        self.assertIn("recall", payload["mcpServers"])
        self.assertTrue((ROOT / "scripts" / "kimi_mcp_server.py").is_file())
        self.assertTrue((ROOT / "hooks" / "hooks.json").is_file())
        self.assertTrue((ROOT / "docs" / "CLAUDE_CODE.md").is_file())

    def test_install_docs_pin_ref_to_current_version(self) -> None:
        """READMEs/INSTALL.md tell users to `--ref vX.Y.Z` a specific tag —
        that string isn't covered by the manifest-version parity test above,
        so it silently drifted to a stale tag once already (v1.4.0 install
        docs survived the v1.5.0 bump undetected until this test)."""

        version = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
        expected_ref = f"--ref v{version}"
        for path in (
            REPO_ROOT / "README.md",
            ROOT / "README.md",
            ROOT / "docs" / "INSTALL.md",
        ):
            text = path.read_text(encoding="utf-8")
            if "--ref v" not in text:
                continue
            self.assertIn(expected_ref, text, path)
            for stale in ("--ref v1.4.0", "--ref v1.3.0", "--ref v1.2.0", "--ref v1.1.0"):
                if stale == expected_ref:
                    continue
                self.assertNotIn(stale, text, path)

    def test_cross_platform_python_builder_is_present(self) -> None:
        self.assertTrue((REPO_ROOT / "build_plugin.py").is_file())
        self.assertTrue((ROOT / "scripts" / "build_plugin.py").is_file())

    def test_skills_describe_local_only_storage_and_secret_safety(self) -> None:
        for path in sorted((ROOT / "skills").glob("*/SKILL.md")):
            text = path.read_text(encoding="utf-8").lower()
            self.assertIn("local", text, path)
            self.assertIn("secret", text, path)
            if path.parent.name != "using-recall":
                self.assertIn("recall_skill.py", text, path)
            self.assertNotIn("memory_manager.py", text, path)
            self.assertNotIn("cloud", text, path)
            self.assertNotIn("remote api", text, path)

    def test_memory_management_skill_surface_is_discoverable(self) -> None:
        skill_names = {path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")}
        expected = {
            "define-category",
            "manage-memory",
            "memory-hygiene",
            "retrieve-memory",
            "review-memory",
            "save-insight",
            "using-recall",
        }
        self.assertEqual(len(skill_names), 7)
        self.assertEqual(skill_names, expected)

    def test_workflow_examples_cover_core_memory_cards(self) -> None:
        text = (ROOT / "examples" / "workflows.md").read_text(encoding="utf-8").lower()
        for category in ("requirements", "risks", "commands", "session_summaries"):
            self.assertIn(category, text)
        for flag in ("--summary", "--details", "--tag", "--status"):
            self.assertIn(flag, text)

    def test_package_inspector_accepts_minimal_valid_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "recall.zip"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr(".codex-plugin/plugin.json", json.dumps({"name": "recall", "skills": "./skills/"}))
                package.writestr(".claude-plugin/plugin.json", json.dumps({"name": "recall", "skills": "./skills/"}))
                package.writestr("kimi.plugin.json", json.dumps({"name": "recall", "skills": "./skills/"}))
                package.writestr("scripts/contract.py", "print('ok')\n")
                package.writestr("hooks/hooks.json", "{}")
                package.writestr("skills/save-insight/SKILL.md", "# Save")
                package.writestr("skills/retrieve-memory/SKILL.md", "# Retrieve")
                package.writestr("skills/define-category/SKILL.md", "# Define")
                package.writestr("skills/using-recall/SKILL.md", "# Using")
                package.writestr("scripts/kimi_mcp_server.py", "print('ok')\n")
                package.writestr("scripts/hook_events.py", "print('ok')\n")
                package.writestr("scripts/recall_skill.py", "print('ok')\n")
                package.writestr("scripts/memory_manager.py", "print('ok')\n")
            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "inspect_package.py"), str(archive)],
                text=True,
                capture_output=True,
                check=True,
                cwd=ROOT,
            )
            self.assertEqual(json.loads(completed.stdout)["status"], "pass")

    def test_package_inspector_rejects_runtime_and_secret_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "recall.zip"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr(".codex-plugin/plugin.json", json.dumps({"name": "recall", "skills": "./skills/"}))
                package.writestr(".claude-plugin/plugin.json", json.dumps({"name": "recall", "skills": "./skills/"}))
                package.writestr("kimi.plugin.json", json.dumps({"name": "recall", "skills": "./skills/"}))
                package.writestr("scripts/contract.py", "print('ok')\n")
                package.writestr("hooks/hooks.json", "{}")
                package.writestr("skills/save-insight/SKILL.md", "# Save")
                package.writestr("skills/retrieve-memory/SKILL.md", "# Retrieve")
                package.writestr("skills/define-category/SKILL.md", "# Define")
                package.writestr("skills/using-recall/SKILL.md", "# Using")
                package.writestr("scripts/kimi_mcp_server.py", "print('ok')\n")
                package.writestr("scripts/hook_events.py", "print('ok')\n")
                package.writestr("scripts/recall_skill.py", "print('ok')\n")
                package.writestr("scripts/memory_manager.py", "token=dummy-secret-value\n")
                package.writestr(".codex_memory/memory.sqlite", "")
                package.writestr(".recall/memory.sqlite", "")
            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "inspect_package.py"), str(archive)],
                text=True,
                capture_output=True,
                cwd=ROOT,
            )
            self.assertNotEqual(completed.returncode, 0)
            report = json.loads(completed.stdout)
            self.assertEqual(report["status"], "fail")
            self.assertTrue(any("Forbidden package path" in error for error in report["errors"]))
            self.assertTrue(any("Secret-like string" in error for error in report["errors"]))

    @unittest.skipUnless(os.name == "nt", "Windows hook command regression only runs on Windows.")
    def test_windows_hook_commands_run_through_powershell(self) -> None:
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        payloads = {
            "SessionStart": {"hook_event_name": "SessionStart"},
            "UserPromptSubmit": {
                "hook_event_name": "UserPromptSubmit",
                "prompt": "remember this: commandWindows regression test",
            },
            "PostToolUse": {
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "python -m unittest discover -s tests"},
                "tool_response": {"exit_code": 0, "stdout": "Ran 1 test in 0.1s\nOK", "stderr": ""},
            },
            "PreCompact": {
                "hook_event_name": "PreCompact",
                "trigger": "manual",
                "turn_id": "windows-command-regression",
                "summary": "Windows command hook regression checkpoint.",
            },
            "Stop": {
                "hook_event_name": "Stop",
                "turn_id": "windows-command-regression",
                "last_assistant_message": "Windows command hook regression completed.",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["PLUGIN_ROOT"] = str(ROOT)
            for event_name, matcher_groups in hooks.items():
                command = matcher_groups[0]["hooks"][0]["commandWindows"]
                payload = {**payloads[event_name], "cwd": tmp}
                completed = subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-Command",
                        command,
                    ],
                    input=json.dumps(payload),
                    text=True,
                    capture_output=True,
                    cwd=ROOT,
                    env=env,
                )
                self.assertEqual(completed.returncode, 0, f"{event_name}: {completed.stderr}")
                output = json.loads(completed.stdout)
                self.assertTrue(output["continue"], event_name)

    @unittest.skipUnless(os.name == "nt", "Windows hook command regression only runs on Windows.")
    def test_windows_hook_commands_run_with_claude_plugin_root_and_no_plugin_root(self) -> None:
        """Regression test for a live bug: Claude Code sets CLAUDE_PLUGIN_ROOT,
        not PLUGIN_ROOT (Codex's variable). With PLUGIN_ROOT left completely
        unset (as Claude Code actually leaves it), hooks must still resolve
        correctly using CLAUDE_PLUGIN_ROOT alone.
        """
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        payloads = {
            "SessionStart": {"hook_event_name": "SessionStart"},
            "UserPromptSubmit": {
                "hook_event_name": "UserPromptSubmit",
                "prompt": "remember this: commandWindows regression test",
            },
            "PostToolUse": {
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "python -m unittest discover -s tests"},
                "tool_response": {"exit_code": 0, "stdout": "Ran 1 test in 0.1s\nOK", "stderr": ""},
            },
            "PreCompact": {
                "hook_event_name": "PreCompact",
                "trigger": "manual",
                "turn_id": "claude-plugin-root-regression",
                "summary": "Claude Code plugin root regression checkpoint.",
            },
            "Stop": {
                "hook_event_name": "Stop",
                "turn_id": "claude-plugin-root-regression",
                "last_assistant_message": "Claude Code plugin root regression completed.",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env.pop("PLUGIN_ROOT", None)
            env["CLAUDE_PLUGIN_ROOT"] = str(ROOT)
            for event_name, matcher_groups in hooks.items():
                command = matcher_groups[0]["hooks"][0]["commandWindows"]
                payload = {**payloads[event_name], "cwd": tmp}
                completed = subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-Command",
                        command,
                    ],
                    input=json.dumps(payload),
                    text=True,
                    capture_output=True,
                    cwd=ROOT,
                    env=env,
                )
                self.assertEqual(completed.returncode, 0, f"{event_name}: {completed.stderr}")
                output = json.loads(completed.stdout)
                self.assertTrue(output["continue"], event_name)


if __name__ == "__main__":
    unittest.main()
