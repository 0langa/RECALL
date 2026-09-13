"""Cross-provider sync and canonical-contract consistency gates.

These tests pin the guarantees that keep Codex, Claude Code, and Kimi Code
behavior from drifting: one version everywhere, one contract everywhere, and
the Claude Code manifest actually shipped in built packages.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import contract as recall_contract  # noqa: E402
import config as recall_config  # noqa: E402


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def normalized_text(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


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
            "retrieve relevant history",
            "decide save-worthiness",
            "save durable insight",
            "update changed memory",
            "deprecate or supersede wrong memory",
            "validate memory health",
            "handoff summary",
        ):
            self.assertIn(expected, steps)
        self.assertEqual(
            payload["instruction_authority_order"],
            [
                "system instructions",
                "developer instructions",
                "current user instructions and scope",
            ],
        )
        self.assertEqual(payload["authority_order"], payload["instruction_authority_order"])
        self.assertIn("local_first", payload)

    def test_compact_contract_covers_authority_relevance_and_maintenance(self) -> None:
        text = recall_contract.compact_contract_text()
        hierarchy = " > ".join(recall_contract.INSTRUCTION_AUTHORITY_ORDER)
        self.assertIn(f"Instruction order: {hierarchy}", text)
        for rule in (
            recall_contract.MEMORY_TRUST_RULE,
            recall_contract.RETRIEVAL_RELEVANCE_RULE,
            recall_contract.RETRIEVAL_ENTRYPOINT_RULE,
            recall_contract.RETRIEVAL_SKIP_RULE,
            recall_contract.EMPTY_RESULT_RULE,
            recall_contract.NO_USAGE_OBLIGATION_RULE,
            recall_contract.MAINTENANCE_RULE,
            recall_contract.GUIDANCE_SCOPE_RULE,
        ):
            self.assertIn(rule, text)
        self.assertIn("Never save secrets", text)
        self.assertIn("update_memory", text)
        self.assertIn("memory_hygiene", text)
        self.assertLess(len(text), 2000, "compact contract must stay injectable")

    def test_retrieval_policy_has_distinct_positive_and_skip_examples(self) -> None:
        policy = recall_contract.contract_dict()["retrieval"]
        self.assertEqual(policy["relevance_rule"], recall_contract.RETRIEVAL_RELEVANCE_RULE)
        self.assertEqual(policy["entrypoint_rule"], recall_contract.RETRIEVAL_ENTRYPOINT_RULE)
        self.assertEqual(policy["skip_rule"], recall_contract.RETRIEVAL_SKIP_RULE)
        self.assertEqual(policy["empty_result_rule"], recall_contract.EMPTY_RESULT_RULE)
        self.assertEqual(policy["usage_obligation"], recall_contract.NO_USAGE_OBLIGATION_RULE)
        self.assertEqual(
            set(policy["examples"]),
            {
                "recurring_project_failure",
                "small_self_contained_task",
                "explicit_memory_free_task",
            },
        )
        self.assertIn("retrieve", policy["examples"]["recurring_project_failure"])
        self.assertIn("do not retrieve", policy["examples"]["small_self_contained_task"])
        self.assertIn("do not retrieve", policy["examples"]["explicit_memory_free_task"])

    def test_retrieval_tool_guidance_is_not_stronger_than_full_contract(self) -> None:
        text = recall_contract.retrieval_tool_guidance()
        self.assertIn(" > ".join(recall_contract.INSTRUCTION_AUTHORITY_ORDER), text)
        for rule in (
            recall_contract.MEMORY_TRUST_RULE,
            recall_contract.RETRIEVAL_RELEVANCE_RULE,
            recall_contract.RETRIEVAL_ENTRYPOINT_RULE,
            recall_contract.RETRIEVAL_SKIP_RULE,
            recall_contract.EMPTY_RESULT_RULE,
            recall_contract.NO_USAGE_OBLIGATION_RULE,
        ):
            self.assertIn(rule, text)
            self.assertIn(rule, recall_contract.compact_contract_text())

    def test_first_workflow_keeps_retrieval_optional_and_maintenance_visible(self) -> None:
        for style in ("mcp", "cli"):
            text = recall_contract.first_workflow_text(style)
            self.assertIn("only when prior project history can help", text)
            self.assertIn("an empty result is valid", text)
            self.assertIn("A lookup, category, or save is not required", text)
        self.assertIn("update_memory", recall_contract.first_workflow_text("mcp"))
        self.assertIn("memory_hygiene", recall_contract.first_workflow_text("mcp"))
        self.assertIn("edit-memory or supersede-memory", recall_contract.first_workflow_text("cli"))
        self.assertIn("hygiene-scan", recall_contract.first_workflow_text("cli"))

    def test_affected_skills_match_canonical_hierarchy_and_relevance_rules(self) -> None:
        paths = [
            ROOT / "skills" / "using-recall" / "SKILL.md",
            ROOT / "skills" / "using-recall" / "references" / "contract.md",
            ROOT / "skills" / "retrieve-memory" / "SKILL.md",
        ]
        expected = [
            "system instructions > developer instructions > current user instructions and scope",
            recall_contract.MEMORY_TRUST_RULE,
            recall_contract.RETRIEVAL_RELEVANCE_RULE,
            recall_contract.RETRIEVAL_ENTRYPOINT_RULE,
            recall_contract.RETRIEVAL_SKIP_RULE,
            recall_contract.EMPTY_RESULT_RULE,
            recall_contract.NO_USAGE_OBLIGATION_RULE,
            recall_contract.GUIDANCE_SCOPE_RULE,
        ]
        for path in paths:
            text = normalized_text(path)
            for rule in expected:
                self.assertIn(rule, text, f"{path.name} drifted from the canonical rule: {rule}")

    def test_contract_assets_pin_memory_trust_and_optional_retrieval(self) -> None:
        assets = [
            load_json(ROOT / "skills" / "using-recall" / "assets" / "handoff-contract.json"),
            load_json(ROOT / "skills" / "retrieve-memory" / "assets" / "contract.json"),
        ]
        using, retrieve = assets
        self.assertEqual(
            using["authority"]["instruction_order"],
            ["system_instructions", "developer_instructions", "current_user_instructions_and_scope"],
        )
        self.assertFalse(using["authority"]["memory_can_grant_permission"])
        self.assertFalse(using["authority"]["guidance_enforces_access"])
        self.assertFalse(using["retrieval"]["lookup_category_or_save_required"])
        self.assertTrue(using["retrieval"]["empty_result_is_valid"])
        self.assertFalse(retrieve["memory_can_grant_permission"])
        self.assertFalse(retrieve["guidance_enforces_access"])
        self.assertFalse(retrieve["lookup_category_or_save_required"])
        self.assertTrue(retrieve["empty_result_is_valid"])

    def test_session_start_emits_the_canonical_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recall_config.activate_project(tmp, activated_by="contract-test")
            completed = subprocess.run(
                [sys.executable, str(ROOT / "hooks" / "scripts" / "session_start.py")],
                input=json.dumps({"cwd": tmp, "hook_event_name": "SessionStart"}),
                text=True,
                capture_output=True,
                check=True,
                cwd=ROOT,
            )
            context = json.loads(completed.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertTrue(context.startswith(recall_contract.compact_contract_text()))
            self.assertIn(recall_contract.EMPTY_RESULT_RULE, context)

    def test_cli_contract_output_matches_canonical_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "recall_skill.py"),
                    "--root",
                    tmp,
                    "contract",
                ],
                text=True,
                capture_output=True,
                check=True,
                cwd=ROOT,
            )
            self.assertEqual(json.loads(completed.stdout)["contract"], recall_contract.contract_dict())

    def test_changed_contract_surfaces_have_no_benchmark_identifiers_or_model_names(self) -> None:
        paths = [
            ROOT / "scripts" / "contract.py",
            ROOT / "hooks" / "scripts" / "session_start.py",
            ROOT / "skills" / "using-recall" / "SKILL.md",
            ROOT / "skills" / "retrieve-memory" / "SKILL.md",
        ]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(
                re.search(r"\b[A-Z]\d{2}\b", text),
                f"{path.name} contains a benchmark case identifier",
            )
            self.assertIsNone(
                re.search(r"\b[a-z]+-\d+(?:\.\d+)*\b", text, re.IGNORECASE),
                f"{path.name} contains a versioned model name",
            )

    def test_status_meanings_cover_all_card_statuses(self) -> None:
        import memory_manager

        for status in memory_manager.CARD_STATUSES:
            self.assertIn(status, recall_contract.STATUS_MEANINGS)


class ProviderCapabilityParityTests(unittest.TestCase):
    """Every MCP tool must stay reachable through the shared adapter CLI.

    The provider manifests declare the MCP server. The adapter remains the
    direct CLI surface for every provider. This map failing means a capability
    became MCP-only and introduced a silent cross-provider gap.
    """

    MCP_TO_ADAPTER = {
        "retrieve_memory": ["retrieve-memory"],
        "context_packet": ["context-packet"],
        "save_insight": ["save-insight"],
        "review_memory": ["review-memory"],
        "update_memory": [
            "confirm-memory", "stale-memory", "supersede-memory", "merge-memories",
            "resolve-memory", "prune-memory", "edit-memory", "deprecate-memory",
        ],
        "memory_hygiene": ["route-memory", "hygiene-scan", "hygiene-plan", "hygiene-apply"],
        "memory_contract": ["contract"],
        "initialize_project": ["initialize-project"],
    }

    def test_map_covers_exactly_the_mcp_tool_surface(self) -> None:
        server_source = (ROOT / "scripts" / "kimi_mcp_server.py").read_text(encoding="utf-8")
        import re

        declared = set(re.findall(r'"name": "([a-z_]+)",\n\s+"description"', server_source))
        self.assertEqual(
            declared,
            set(self.MCP_TO_ADAPTER),
            "MCP tool surface changed; update MCP_TO_ADAPTER, the adapter, and docs/CODEX.md together",
        )

    def test_every_mcp_tool_has_adapter_equivalents(self) -> None:
        adapter_source = (ROOT / "scripts" / "recall_skill.py").read_text(encoding="utf-8")
        for tool, commands in self.MCP_TO_ADAPTER.items():
            for command in commands:
                self.assertIn(
                    f'add_parser("{command}")',
                    adapter_source.replace("subparsers.add_parser", "add_parser"),
                    f"MCP tool {tool} lost its adapter equivalent `{command}`",
                )

    def test_codex_doc_documents_the_full_tool_map(self) -> None:
        codex_doc = (ROOT / "docs" / "CODEX.md").read_text(encoding="utf-8")
        for tool in self.MCP_TO_ADAPTER:
            self.assertIn(f"`{tool}`", codex_doc, f"docs/CODEX.md missing MCP tool {tool}")
        codex_manifest = load_json(ROOT / ".codex-plugin" / "plugin.json")
        server = codex_manifest["mcpServers"]["recall"]
        self.assertEqual(server["env"]["RECALL_DEFAULT_PROVIDER"], "codex")
        self.assertIn("already declares the MCP server", codex_doc)
        self.assertIn("[mcp_servers.recall]", codex_doc)
        self.assertIn('RECALL_DEFAULT_PROVIDER = "codex"', codex_doc)


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
