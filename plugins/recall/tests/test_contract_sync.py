"""Cross-provider sync and canonical-contract consistency gates.

These tests pin the guarantees that keep Codex, Claude Code, and Kimi Code
behavior from drifting: one version everywhere, one contract everywhere, and
the Claude Code manifest actually shipped in built packages.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import contract as recall_contract  # noqa: E402
import config as recall_config  # noqa: E402


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class ManifestParityTests(unittest.TestCase):
    def test_all_provider_manifests_share_one_version(self) -> None:
        codex = load_json(ROOT / ".codex-plugin" / "plugin.json")
        claude = load_json(ROOT / ".claude-plugin" / "plugin.json")
        kimi = load_json(ROOT / "kimi.plugin.json")
        versions = {codex["version"], claude["version"], kimi["version"]}
        self.assertEqual(len(versions), 1, f"provider manifest versions drifted: {versions}")

        server_source = (ROOT / "scripts" / "kimi_mcp_server.py").read_text(encoding="utf-8")
        version = versions.pop()
        self.assertIn(
            f'"version": "{version}"',
            server_source,
            "MCP serverInfo version must move together with the plugin manifests",
        )

    def test_all_provider_manifests_share_skills_path_and_name(self) -> None:
        manifests = [
            load_json(ROOT / ".codex-plugin" / "plugin.json"),
            load_json(ROOT / ".claude-plugin" / "plugin.json"),
            load_json(ROOT / "kimi.plugin.json"),
        ]
        self.assertEqual({m["name"] for m in manifests}, {"recall"})
        self.assertEqual({m["skills"] for m in manifests}, {"./skills/"})

    def test_mcp_manifests_point_at_shared_server_with_provider_env(self) -> None:
        claude = load_json(ROOT / ".claude-plugin" / "plugin.json")["mcpServers"]["recall"]
        kimi = load_json(ROOT / "kimi.plugin.json")["mcpServers"]["recall"]
        self.assertIn("kimi_mcp_server.py", " ".join(claude["args"]))
        self.assertIn("kimi_mcp_server.py", " ".join(kimi["args"]))
        self.assertEqual(claude["env"]["RECALL_DEFAULT_PROVIDER"], "claude-code")
        self.assertEqual(kimi["env"]["RECALL_DEFAULT_PROVIDER"], "kimi")

    def test_build_and_inspection_include_claude_manifest(self) -> None:
        build_source = (ROOT / "scripts" / "build_plugin.py").read_text(encoding="utf-8")
        self.assertIn('".claude-plugin"', build_source, "built zips must ship the Claude Code manifest")
        inspect_source = (ROOT / "scripts" / "inspect_package.py").read_text(encoding="utf-8")
        self.assertIn(".claude-plugin/plugin.json", inspect_source)
        self.assertIn("scripts/contract.py", inspect_source)


class ContractConsistencyTests(unittest.TestCase):
    def test_contract_dict_exposes_full_lifecycle(self) -> None:
        payload = recall_contract.contract_dict()
        steps = [item["step"] for item in payload["lifecycle"]]
        for expected in (
            "initialize",
            "retrieve before work",
            "decide save-worthiness",
            "save durable insight",
            "update changed memory",
            "deprecate or supersede wrong memory",
            "validate memory health",
            "handoff summary",
        ):
            self.assertIn(expected, steps)
        self.assertEqual(payload["authority_order"][0], "current user instruction")
        self.assertEqual(payload["authority_order"][-1], "older conversation assumptions")
        self.assertIn("local_first", payload)

    def test_compact_contract_covers_authority_retrieval_and_secrets(self) -> None:
        text = recall_contract.compact_contract_text()
        self.assertIn("Authority order", text)
        self.assertIn("retrieve_memory", text)
        self.assertIn("Never save secrets", text)
        self.assertIn("update_memory", text)
        self.assertIn("memory_hygiene", text)
        self.assertLess(len(text), 2000, "compact contract must stay injectable")

    def test_skill_contract_reference_matches_canonical_authority_order(self) -> None:
        reference = (ROOT / "skills" / "using-recall" / "references" / "contract.md").read_text(encoding="utf-8")
        for item in recall_contract.AUTHORITY_ORDER:
            self.assertIn(item, reference, f"contract.md drifted from contract.py: missing '{item}'")

    def test_status_meanings_cover_all_card_statuses(self) -> None:
        import memory_manager

        for status in memory_manager.CARD_STATUSES:
            self.assertIn(status, recall_contract.STATUS_MEANINGS)


class CategoryGuidanceTests(unittest.TestCase):
    def test_default_categories_carry_examples_and_update_rules(self) -> None:
        for name, details in recall_config.DEFAULT_CATEGORIES.items():
            self.assertTrue(details.get("examples"), f"category {name} needs examples")
            self.assertTrue(details.get("non_examples"), f"category {name} needs non_examples")
            self.assertTrue(details.get("update_rule"), f"category {name} needs an update_rule")

    def test_required_memory_slots_exist(self) -> None:
        names = set(recall_config.DEFAULT_CATEGORIES)
        for slot in (
            "architecture",
            "commands",
            "debug_history",
            "preferences",
            "tooling_quirks",
            "integrations",
            "constraints",
            "decisions",
            "risks",
            "requirements",
        ):
            self.assertIn(slot, names)

    def test_validate_config_preserves_guidance_fields(self) -> None:
        cfg = recall_config.validate_config(recall_config.default_config())
        details = cfg["categories"]["commands"]
        self.assertIn("examples", details)
        self.assertIn("non_examples", details)
        self.assertIn("update_rule", details)


if __name__ == "__main__":
    unittest.main()
