"""MCP surface: lifecycle tools, hygiene tool, contract exposure, save teaching."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import kimi_mcp_server as server  # noqa: E402


def call_tool(name: str, arguments: dict) -> dict:
    response = server.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    )
    if "error" in response:
        raise AssertionError(f"tool {name} errored: {response['error']}")
    return json.loads(response["result"]["content"][0]["text"])


class McpSurfaceTests(unittest.TestCase):
    def test_tools_list_exposes_full_lifecycle(self) -> None:
        response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertEqual(
            names,
            {
                "retrieve_memory",
                "context_packet",
                "save_insight",
                "review_memory",
                "update_memory",
                "memory_hygiene",
                "memory_contract",
                "initialize_project",
            },
        )

    def test_initialize_returns_contract_instructions(self) -> None:
        response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        result = response["result"]
        self.assertIn("Authority order", result["instructions"])
        self.assertIn("retrieve_memory", result["instructions"])

    def test_memory_contract_tool_returns_lifecycle_and_categories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = call_tool("memory_contract", {"root": tmp})
            self.assertEqual(payload["contract"]["authority_order"][0], "current user instruction")
            self.assertIn("tooling_quirks", payload["categories"])
            self.assertIn("update_rule", payload["categories"]["commands"])


class McpSaveTests(unittest.TestCase):
    def test_save_insight_rejects_secret_shaped_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = call_tool(
                "save_insight",
                {
                    "root": tmp,
                    "category": "commands",
                    "content": "Deploy token = sk-proj-ABCDEFGHIJKLMNOPQRSTUVWX",
                },
            )
            self.assertEqual(payload["result"], "rejected")
            self.assertIn("secret", payload["reason"])
            self.assertIn("next_action", payload)
            retrieved = call_tool("retrieve_memory", {"root": tmp, "query_text": "deploy token"})
            self.assertEqual(retrieved["results"], [])

    def test_duplicate_save_confirms_existing_instead_of_appending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = call_tool(
                "save_insight",
                {"root": tmp, "category": "decisions", "content": "Use SQLite as the default backend."},
            )
            self.assertEqual(first["result"], "saved")
            second = call_tool(
                "save_insight",
                {"root": tmp, "category": "decisions", "content": "Use SQLite as the default backend."},
            )
            self.assertEqual(second["result"], "updated_existing")
            self.assertEqual(second["id"], first["id"])
            self.assertIn("update_memory", second["next_action"])

    def test_preference_save_without_evidence_teaches_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ignored = call_tool(
                "save_insight",
                {"root": tmp, "category": "preferences", "content": "User prefers tabs over spaces."},
            )
            self.assertEqual(ignored["result"], "ignored")
            self.assertIn("preference_evidence_type", ignored["next_action"])

            saved = call_tool(
                "save_insight",
                {
                    "root": tmp,
                    "category": "preferences",
                    "content": "User prefers tabs over spaces.",
                    "preference_key": "indentation",
                    "preference_evidence_type": "explicit_declaration",
                },
            )
            self.assertEqual(saved["result"], "saved")


class McpLifecycleTests(unittest.TestCase):
    def test_update_memory_supports_deprecate_supersede_and_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old = call_tool(
                "save_insight",
                {"root": tmp, "category": "architecture", "content": "Hooks poll for changes every second."},
            )
            new = call_tool(
                "save_insight",
                {"root": tmp, "category": "architecture", "content": "Hooks are event-driven via provider events."},
            )
            superseded = call_tool(
                "update_memory",
                {"root": tmp, "op": "supersede", "id": old["id"], "new_id": new["id"], "note": "Design changed."},
            )
            self.assertEqual(superseded["old"]["status"], "superseded")

            wrong = call_tool(
                "save_insight",
                {"root": tmp, "category": "commands", "content": "Run build with make all."},
            )
            deprecated = call_tool(
                "update_memory",
                {"root": tmp, "op": "deprecate", "id": wrong["id"], "note": "Makefile was removed."},
            )
            self.assertEqual(deprecated["record"]["status"], "deprecated")

            confirmed = call_tool("update_memory", {"root": tmp, "op": "confirm", "id": new["id"]})
            self.assertEqual(confirmed["result"], "ok")

    def test_update_memory_update_rejects_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = call_tool(
                "save_insight",
                {"root": tmp, "category": "commands", "content": "Deploy runs through the CI pipeline."},
            )
            rejected = call_tool(
                "update_memory",
                {
                    "root": tmp,
                    "op": "update",
                    "id": record["id"],
                    "content": "Deploy with password = hunter2secret",
                },
            )
            self.assertEqual(rejected["result"], "rejected")

    def test_update_memory_supersede_without_new_id_explains_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = call_tool(
                "save_insight",
                {"root": tmp, "category": "decisions", "content": "Old decision to replace."},
            )
            response = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 9,
                    "method": "tools/call",
                    "params": {"name": "update_memory", "arguments": {"root": tmp, "op": "supersede", "id": record["id"]}},
                }
            )
            self.assertIn("error", response)
            self.assertIn("save_insight", response["error"]["message"])


class McpHygieneTests(unittest.TestCase):
    def test_hygiene_route_scan_and_apply_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            routed = call_tool(
                "memory_hygiene",
                {"root": tmp, "mode": "route", "text": "temporary scratch note for this task only"},
            )
            self.assertEqual(routed["route"], "current_chat_only")

            secret_route = call_tool(
                "memory_hygiene",
                {"root": tmp, "mode": "route", "text": "api_key = sk-proj-ABCDEFGHIJKLMNOPQRSTUVWX"},
            )
            self.assertEqual(secret_route["route"], "reject")

            call_tool("save_insight", {"root": tmp, "category": "decisions", "content": "Keep memory local-first."})
            scan = call_tool("memory_hygiene", {"root": tmp, "mode": "scan"})
            self.assertEqual(scan["action"], "hygiene-scan")
            applied = call_tool("memory_hygiene", {"root": tmp, "mode": "apply_safe"})
            self.assertEqual(applied["action"], "hygiene-apply")


class McpInitTests(unittest.TestCase):
    def test_initialize_project_creates_config_gitignore_and_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".git").mkdir()
            payload = call_tool("initialize_project", {"root": tmp})
            self.assertTrue(payload["activation"]["enabled"])
            self.assertIn(".recall/", payload["gitignore"]["added"])
            self.assertIn("tooling_quirks", payload["categories"])
            self.assertIn("Authority order", payload["contract"])
            self.assertIn("retrieve_memory", payload["first_workflow"])
            gitignore = (Path(tmp) / ".gitignore").read_text(encoding="utf-8")
            self.assertIn(".recall/", gitignore)

            # Re-run is idempotent for gitignore entries.
            payload_again = call_tool("initialize_project", {"root": tmp})
            self.assertEqual(payload_again["gitignore"]["added"], [])


if __name__ == "__main__":
    unittest.main()
