from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ClaudeCodeAdapterTests(unittest.TestCase):
    def test_claude_plugin_manifest_declares_provider_env_and_reuses_kimi_server(self) -> None:
        manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["name"], "recall")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertIn("recall", manifest["mcpServers"])
        server = manifest["mcpServers"]["recall"]
        # Must use ${CLAUDE_PLUGIN_ROOT} explicitly, not a bare relative path:
        # a relative "./scripts/..." path resolves against Claude Code's own
        # process cwd, not the plugin directory, and silently fails to start
        # the server (confirmed live via `claude plugin details recall`
        # reporting "MCP servers (0)" before this fix).
        self.assertEqual(server["cwd"], "${CLAUDE_PLUGIN_ROOT}")
        self.assertEqual(server["args"], ["${CLAUDE_PLUGIN_ROOT}/scripts/kimi_mcp_server.py"])
        self.assertEqual(server["env"]["RECALL_DEFAULT_PROVIDER"], "claude-code")
        # startupTimeoutMs/toolTimeoutMs are Kimi-specific config extensions
        # (copied from kimi.plugin.json originally) and are NOT part of
        # Claude Code's MCP server schema. Including them silently dropped
        # the entire server entry (`claude plugin details recall` reported
        # "MCP servers (0)" until these were removed) rather than raising a
        # validation error — `claude plugin validate` does not catch this.
        self.assertNotIn("startupTimeoutMs", server)
        self.assertNotIn("toolTimeoutMs", server)

    def test_claude_code_mcp_writes_are_stamped_with_correct_provenance(self) -> None:
        """Regression test: kimi_mcp_server.py used to hardcode origin_provider="kimi"
        regardless of caller. Since the Claude Code manifest reuses this exact
        script (no duplicated adapter), an unstamped write would silently
        mislabel Claude Code-originated memory as Kimi-originated. This drives
        the same script the way the Claude Code manifest's env block does and
        asserts real provenance, not just that a value round-trips.
        """
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
                            "content": "Claude Code and Kimi share the same RECALL memory store.",
                            "summary": "Shared provider-neutral store.",
                            "source_session": "claude-code-session",
                        },
                    },
                },
            ]
            env = os.environ.copy()
            env["RECALL_DEFAULT_PROVIDER"] = "claude-code"
            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "kimi_mcp_server.py")],
                input="\n".join(json.dumps(request) for request in requests) + "\n",
                text=True,
                capture_output=True,
                check=True,
                cwd=ROOT,
                env=env,
            )
            responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
            self.assertEqual([response["id"] for response in responses], [1, 2, 3])

            init_text = responses[1]["result"]["content"][0]["text"]
            init_payload = json.loads(init_text)
            self.assertEqual(init_payload["activation"]["activated_by"], "claude-code_mcp")

            save_text = responses[2]["result"]["content"][0]["text"]
            save_payload = json.loads(save_text)
            self.assertEqual(save_payload["metadata"]["origin_provider"], "claude-code")
            self.assertEqual(save_payload["metadata"]["capture_channel"], "mcp")

    def test_provider_env_defaults_to_kimi_when_unset(self) -> None:
        """Guards against regressing Kimi's existing, unset-env-var behavior."""
        with tempfile.TemporaryDirectory() as tmp:
            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "save_insight",
                        "arguments": {
                            "root": tmp,
                            "category": "decisions",
                            "content": "Default provider stays kimi when RECALL_DEFAULT_PROVIDER is unset.",
                        },
                    },
                },
            ]
            env = os.environ.copy()
            env.pop("RECALL_DEFAULT_PROVIDER", None)
            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "kimi_mcp_server.py")],
                input="\n".join(json.dumps(request) for request in requests) + "\n",
                text=True,
                capture_output=True,
                check=True,
                cwd=ROOT,
                env=env,
            )
            responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
            save_payload = json.loads(responses[1]["result"]["content"][0]["text"])
            self.assertEqual(save_payload["metadata"]["origin_provider"], "kimi")


if __name__ == "__main__":
    unittest.main()
