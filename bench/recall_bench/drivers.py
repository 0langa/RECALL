"""Drive RECALL exactly like providers do.

Hooks: subprocess with the event JSON on stdin (same as Codex/Claude/Kimi).
MCP: JSON-RPC over stdio to the real kimi_mcp_server.py process.
Adapter: recall_skill.py CLI.

Nothing here fakes engine behavior; only the *caller* is synthetic.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "recall"
HOOKS_DIR = PLUGIN_ROOT / "hooks" / "scripts"
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"


class HookDriver:
    def run(self, script: str, payload: dict[str, Any]) -> tuple[dict[str, Any], float]:
        start = time.perf_counter()
        completed = subprocess.run(
            [sys.executable, str(HOOKS_DIR / script)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=PLUGIN_ROOT,
        )
        duration_ms = (time.perf_counter() - start) * 1000.0
        if completed.returncode != 0:
            raise RuntimeError(f"hook {script} failed: {completed.stderr[:500]}")
        return json.loads(completed.stdout), duration_ms


class AdapterDriver:
    def run(self, root: Path, *args: str) -> tuple[dict[str, Any], float]:
        start = time.perf_counter()
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "recall_skill.py"), "--root", str(root), *args],
            text=True,
            capture_output=True,
            cwd=PLUGIN_ROOT,
        )
        duration_ms = (time.perf_counter() - start) * 1000.0
        if completed.returncode != 0:
            raise RuntimeError(f"adapter {' '.join(args[:2])} failed: {completed.stderr[:500]}")
        return json.loads(completed.stdout), duration_ms


class McpClient:
    """Minimal stdio JSON-RPC client against the real MCP server process."""

    def __init__(self, provider_env: str = "claude-code") -> None:
        import os

        env = dict(os.environ)
        env["RECALL_DEFAULT_PROVIDER"] = provider_env
        self._process = subprocess.Popen(
            [sys.executable, str(SCRIPTS_DIR / "kimi_mcp_server.py")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=PLUGIN_ROOT,
            env=env,
        )
        self._id = 0

    def request(self, method: str, params: dict[str, Any] | None = None) -> tuple[dict[str, Any], float]:
        self._id += 1
        message = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            message["params"] = params
        assert self._process.stdin and self._process.stdout
        start = time.perf_counter()
        self._process.stdin.write(json.dumps(message) + "\n")
        self._process.stdin.flush()
        line = self._process.stdout.readline()
        duration_ms = (time.perf_counter() - start) * 1000.0
        if not line:
            raise RuntimeError("MCP server closed the pipe")
        return json.loads(line), duration_ms

    def initialize(self) -> tuple[dict[str, Any], float]:
        return self.request("initialize")

    def tools_list(self) -> tuple[dict[str, Any], float]:
        return self.request("tools/list")

    def call_tool(self, name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], str, float]:
        """Returns (parsed payload, raw result text as the agent sees it, ms)."""
        response, duration_ms = self.request("tools/call", {"name": name, "arguments": arguments})
        if "error" in response:
            raw = json.dumps(response["error"], sort_keys=True)
            return {"_error": response["error"]}, raw, duration_ms
        raw = response["result"]["content"][0]["text"]
        return json.loads(raw), raw, duration_ms

    def close(self) -> None:
        if self._process.stdin:
            self._process.stdin.close()
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
