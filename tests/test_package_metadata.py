from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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

    def test_repo_marketplace_points_to_repo_root_plugin(self) -> None:
        payload = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["name"], "recall-local")
        entry = payload["plugins"][0]
        self.assertEqual(entry["name"], "recall")
        self.assertEqual(entry["source"], {"source": "local", "path": "./"})
        self.assertEqual(entry["policy"]["installation"], "AVAILABLE")
        self.assertEqual(entry["policy"]["authentication"], "ON_INSTALL")

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


if __name__ == "__main__":
    unittest.main()
