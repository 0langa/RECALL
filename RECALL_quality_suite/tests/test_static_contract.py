from __future__ import annotations

import json
import unittest
from pathlib import Path

from _harness import plugin_root


class StaticPluginContractTests(unittest.TestCase):
    def test_manifest_has_required_public_shape(self) -> None:
        root = plugin_root()
        manifest = json.loads((root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["name"], "recall")
        self.assertIn("version", manifest)
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertIn("interface", manifest)
        self.assertEqual(manifest["interface"]["displayName"], "RECALL")
        self.assertIn("Local", manifest["interface"]["capabilities"])
        self.assertIn("privacyPolicyURL", manifest["interface"])
        self.assertIn("termsOfServiceURL", manifest["interface"])

    def test_required_files_exist(self) -> None:
        root = plugin_root()
        required = [
            ".codex-plugin/plugin.json",
            "README.md",
            "docs/INSTALL.md",
            "docs/PRIVACY.md",
            "docs/TERMS.md",
            "docs/RELEASE_CHECKLIST.md",
            "hooks/hooks.json",
            "hooks/scripts/session_start.py",
            "hooks/scripts/prompt_inspector.py",
            "hooks/scripts/post_tool_use.py",
            "hooks/scripts/pre_compact.py",
            "hooks/scripts/stop.py",
            "scripts/recall_skill.py",
            "scripts/memory_manager.py",
            "scripts/config.py",
            "scripts/storage.py",
            "scripts/retrieval.py",
            "scripts/smoke_recall.py",
            "skills/save-insight/SKILL.md",
            "skills/retrieve-memory/SKILL.md",
            "skills/define-category/SKILL.md",
        ]
        missing = [path for path in required if not (root / path).exists()]
        self.assertEqual(missing, [])

    def test_hooks_json_declares_expected_lifecycle_events(self) -> None:
        root = plugin_root()
        hooks = json.loads((root / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        expected = {"SessionStart", "UserPromptSubmit", "PostToolUse", "PreCompact", "Stop"}
        self.assertTrue(expected.issubset(set(hooks)))

        for event_name in expected:
            entries = hooks[event_name]
            self.assertTrue(entries, f"{event_name} has no entries")
            for entry in entries:
                self.assertIn("hooks", entry)
                for hook in entry["hooks"]:
                    self.assertEqual(hook["type"], "command")
                    self.assertIn("command", hook)
                    self.assertIn("commandWindows", hook)
                    self.assertLessEqual(int(hook.get("timeout", 999)), 30)

    def test_runtime_data_is_gitignored_at_repo_or_plugin_level(self) -> None:
        root = plugin_root()
        candidates = [root / ".gitignore", root.parents[1] / ".gitignore" if len(root.parents) > 1 else root / ".gitignore"]
        contents = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in candidates if path.exists())
        self.assertIn(".codex_memory", contents)


class QualitySuiteDocumentationContractTests(unittest.TestCase):
    def test_required_quality_suite_docs_exist(self) -> None:
        suite_root = Path(__file__).resolve().parents[1]
        required = [
            "README.md",
            "RUNBOOK.md",
            "docs/TEST_PLAN.md",
            "docs/EXTENDING.md",
            "docs/DEVELOPMENT_WORKFLOW.md",
            "docs/TDD_PROCESS.md",
            "docs/RELEASE_ROADMAP_GATES.md",
            "docs/MEMORY_QUALITY_EVOLUTION_PLAN.md",
            "docs/AGENT_IMPLEMENTATION_PROTOCOL.md",
            "rubrics/production_release_criteria.md",
            "rubrics/source_blind_quality_gate.md",
        ]
        missing = [path for path in required if not (suite_root / path).exists()]
        self.assertEqual(missing, [])

    def test_readme_links_development_control_docs(self) -> None:
        suite_root = Path(__file__).resolve().parents[1]
        readme = (suite_root / "README.md").read_text(encoding="utf-8")
        expected_links = [
            "RUNBOOK.md",
            "docs/TEST_PLAN.md",
            "docs/EXTENDING.md",
            "docs/DEVELOPMENT_WORKFLOW.md",
            "docs/TDD_PROCESS.md",
            "docs/RELEASE_ROADMAP_GATES.md",
            "docs/MEMORY_QUALITY_EVOLUTION_PLAN.md",
            "docs/AGENT_IMPLEMENTATION_PROTOCOL.md",
            "rubrics/production_release_criteria.md",
            "rubrics/source_blind_quality_gate.md",
        ]
        for link in expected_links:
            self.assertIn(link, readme)

    def test_runbook_points_to_development_workflow_entrypoint(self) -> None:
        suite_root = Path(__file__).resolve().parents[1]
        runbook = (suite_root / "RUNBOOK.md").read_text(encoding="utf-8")
        self.assertIn("docs/DEVELOPMENT_WORKFLOW.md", runbook)
        self.assertIn("docs/TDD_PROCESS.md", runbook)

    def test_release_criteria_define_alpha_to_final_path(self) -> None:
        suite_root = Path(__file__).resolve().parents[1]
        criteria = (suite_root / "rubrics" / "production_release_criteria.md").read_text(encoding="utf-8")
        required_phrases = [
            "alpha-stage",
            "Alpha",
            "Beta",
            "Release Candidate",
            "Final Product",
            "source-blind",
        ]
        for phrase in required_phrases:
            self.assertIn(phrase, criteria)
        self.assertNotIn("No blockers recorded yet", criteria)
        self.assertIn("Blocks Final Product", criteria)

    def test_source_blind_gate_is_mandatory_for_final_release(self) -> None:
        suite_root = Path(__file__).resolve().parents[1]
        rubric = (suite_root / "rubrics" / "source_blind_quality_gate.md").read_text(encoding="utf-8")
        self.assertIn("final release", rubric.lower())
        self.assertTrue(
            "mandatory" in rubric.lower() or "required" in rubric.lower(),
            "Source-blind gate must be described as mandatory for final release.",
        )

    def test_new_control_docs_cover_required_topics(self) -> None:
        suite_root = Path(__file__).resolve().parents[1]
        expectations = {
            "docs/DEVELOPMENT_WORKFLOW.md": [
                "classify",
                "validation",
                "source-blind",
                "release blocker",
                "memory discipline",
            ],
            "docs/TDD_PROCESS.md": [
                "failing test",
                "bug",
                "refactor",
                "docs-only",
                "forbidden",
                "done",
            ],
            "docs/RELEASE_ROADMAP_GATES.md": [
                "Alpha",
                "Beta",
                "Release Candidate",
                "Final Product",
                "current project should be treated as alpha-stage",
            ],
            "docs/MEMORY_QUALITY_EVOLUTION_PLAN.md": [
                "stale",
                "superseded",
                "contradiction",
                "long-session",
                "cross-agent",
                "missing-information honesty",
            ],
            "docs/AGENT_IMPLEMENTATION_PROTOCOL.md": [
                "read first",
                "plan work",
                "run validation",
                "update docs",
                "never",
                "final status",
            ],
        }
        for relative_path, required_phrases in expectations.items():
            content = (suite_root / relative_path).read_text(encoding="utf-8")
            for phrase in required_phrases:
                self.assertIn(phrase, content, f"Missing '{phrase}' in {relative_path}")


if __name__ == "__main__":
    unittest.main()
