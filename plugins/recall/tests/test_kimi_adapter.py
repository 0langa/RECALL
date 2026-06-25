from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class KimiAdapterTests(unittest.TestCase):
    def test_kimi_manifest_declares_session_skill_and_mcp_server(self) -> None:
        manifest = json.loads((ROOT / "kimi.plugin.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["name"], "recall")
        self.assertEqual(manifest["sessionStart"]["skill"], "using-recall")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertNotIn("hooks", manifest)
        self.assertIn("recall", manifest["mcpServers"])
        server = manifest["mcpServers"]["recall"]
        self.assertEqual(server["cwd"], "./")
        self.assertEqual(server["args"], ["./scripts/kimi_mcp_server.py"])
        self.assertEqual(server["env"]["RECALL_DEFAULT_PROVIDER"], "kimi")
        self.assertTrue((ROOT / "skills" / "using-recall" / "SKILL.md").exists())

    def test_kimi_mcp_save_and_retrieve_share_neutral_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "initialize_project",
                        "arguments": {"root": tmp},
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "save_insight",
                        "arguments": {
                            "root": tmp,
                            "category": "decisions",
                            "content": "Kimi and Codex share the same RECALL memory store.",
                            "summary": "Shared provider-neutral store.",
                            "source_session": "kimi-session",
                        },
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "retrieve_memory",
                        "arguments": {
                            "root": tmp,
                            "query_text": "shared provider neutral store",
                            "category": ["decisions"],
                            "summary": True,
                        },
                    },
                },
            ]
            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "kimi_mcp_server.py")],
                input="\n".join(json.dumps(request) for request in requests) + "\n",
                text=True,
                capture_output=True,
                check=True,
                cwd=ROOT,
            )
            responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]

            self.assertEqual([response["id"] for response in responses], [1, 2, 3, 4])
            save_text = responses[2]["result"]["content"][0]["text"]
            save_payload = json.loads(save_text)
            self.assertEqual(save_payload["metadata"]["origin_provider"], "kimi")
            self.assertEqual(save_payload["metadata"]["capture_channel"], "mcp")
            self.assertEqual(save_payload["metadata"]["applies_to_provider"], "all")
            self.assertTrue((Path(tmp) / ".recall" / "memory.sqlite").exists())
            self.assertFalse((Path(tmp) / ".codex_memory").exists())

            retrieve_text = responses[3]["result"]["content"][0]["text"]
            retrieve_payload = json.loads(retrieve_text)
            self.assertGreaterEqual(len(retrieve_payload["results"]), 1)


if __name__ == "__main__":
    unittest.main()
