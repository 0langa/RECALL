from __future__ import annotations

import json
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
                    self.assertIn("${PLUGIN_ROOT}", hook["command"])
                    self.assertIn("%PLUGIN_ROOT%", hook["commandWindows"])

    def test_repo_marketplace_points_to_child_plugin(self) -> None:
        payload = json.loads((REPO_ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["name"], "recall-local")
        entry = payload["plugins"][0]
        self.assertEqual(entry["name"], "recall")
        self.assertEqual(entry["source"], {"source": "local", "path": "./plugins/recall"})
        self.assertEqual(entry["policy"]["installation"], "AVAILABLE")
        self.assertEqual(entry["policy"]["authentication"], "ON_INSTALL")

    def test_manifest_public_surface_metadata_is_present(self) -> None:
        payload = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        interface = payload["interface"]
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

    def test_skills_describe_local_only_storage_and_secret_safety(self) -> None:
        for path in sorted((ROOT / "skills").glob("*/SKILL.md")):
            text = path.read_text(encoding="utf-8").lower()
            self.assertIn("local-only", text, path)
            self.assertIn("secret", text, path)
            self.assertNotIn("cloud", text, path)
            self.assertNotIn("remote api", text, path)

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
                package.writestr("hooks/hooks.json", "{}")
                package.writestr("skills/save_insight/SKILL.md", "# Save")
                package.writestr("skills/retrieve_memory/SKILL.md", "# Retrieve")
                package.writestr("skills/define_category/SKILL.md", "# Define")
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
                package.writestr("hooks/hooks.json", "{}")
                package.writestr("skills/save_insight/SKILL.md", "# Save")
                package.writestr("skills/retrieve_memory/SKILL.md", "# Retrieve")
                package.writestr("skills/define_category/SKILL.md", "# Define")
                package.writestr("scripts/memory_manager.py", "token=dummy-secret-value\n")
                package.writestr(".codex_memory/memory.sqlite", "")
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


if __name__ == "__main__":
    unittest.main()
