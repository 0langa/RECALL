#!/usr/bin/env python3
"""Small stdio MCP adapter for Kimi Code.

The RECALL core stays in the ordinary Python modules. This file only translates
MCP JSON-RPC calls into public RECALL operations.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

import config as recall_config
import memory_manager
from models import ContextPacketRequest, ReviewRequest
from services.context_service import build_context_packet
from services.health_service import review_memory


Json = dict[str, Any]


def resolve_root(arguments: Json) -> Path | None:
    raw = arguments.get("root") or os.environ.get("RECALL_PROJECT_ROOT")
    return Path(str(raw)).expanduser().resolve() if raw else None


def resolve_provider() -> str:
    """Identify which MCP client is running this adapter.

    This server is shared verbatim between the Kimi and Claude Code plugin
    manifests; each manifest sets RECALL_DEFAULT_PROVIDER in the server's env
    block so writes are stamped with correct provenance instead of always
    reading "kimi". Default stays "kimi" for any caller that omits the env
    var, preserving prior behavior.
    """
    raw = os.environ.get("RECALL_DEFAULT_PROVIDER", "kimi")
    provider = str(raw).strip().lower()
    return provider or "kimi"


def content_response(payload: Json) -> Json:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, indent=2, sort_keys=True),
            }
        ]
    }


def tool_schema(properties: Json, required: list[str] | None = None) -> Json:
    return {
        "type": "object",
        "properties": {
            "root": {
                "type": "string",
                "description": "Active project root. Pass the repository working directory.",
            },
            **properties,
        },
        "required": required or [],
        "additionalProperties": False,
    }


TOOLS: list[Json] = [
    {
        "name": "retrieve_memory",
        "description": "Retrieve relevant RECALL memories from the active project's shared local store.",
        "inputSchema": tool_schema(
            {
                "query_text": {"type": "string"},
                "category": {"type": "array", "items": {"type": "string"}},
                "status": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                "summary": {"type": "boolean"},
            },
            ["query_text"],
        ),
    },
    {
        "name": "context_packet",
        "description": "Build a compact context packet for injecting RECALL memory into a Kimi task.",
        "inputSchema": tool_schema(
            {
                "query_text": {"type": "string"},
                "category": {"type": "array", "items": {"type": "string"}},
                "token_budget": {"type": "integer", "minimum": 100},
            },
            ["query_text"],
        ),
    },
    {
        "name": "save_insight",
        "description": "Save a verified durable project insight to RECALL memory.",
        "inputSchema": tool_schema(
            {
                "category": {"type": "string"},
                "content": {"type": "string"},
                "summary": {"type": "string"},
                "details": {"type": "string"},
                "tag": {"type": "array", "items": {"type": "string"}},
                "status": {"type": "string"},
                "importance": {"type": "number", "minimum": 0, "maximum": 1},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "origin_agent": {"type": "string"},
                "source_session": {"type": "string"},
                "source_turn": {"type": "string"},
                "cwd": {"type": "string"},
                "branch": {"type": "string"},
                "commit": {"type": "string"},
                "applies_to_provider": {"type": "string"},
            },
            ["category", "content"],
        ),
    },
    {
        "name": "review_memory",
        "description": "Review inventory and health of the active project's RECALL memory.",
        "inputSchema": tool_schema(
            {
                "status": {"type": "array", "items": {"type": "string"}},
                "category": {"type": "array", "items": {"type": "string"}},
                "source": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            }
        ),
    },
    {
        "name": "initialize_project",
        "description": "Activate RECALL for a project and create its local memory config if needed.",
        "inputSchema": tool_schema({}, ["root"]),
    },
]


def call_retrieve_memory(arguments: Json) -> Json:
    root = resolve_root(arguments)
    return memory_manager.query(
        str(arguments["query_text"]),
        categories=list(arguments.get("category") or []),
        limit=int(arguments.get("limit") or 8),
        root=root,
        summarize=bool(arguments.get("summary")),
        statuses=list(arguments.get("status") or []),
    )


def call_context_packet(arguments: Json) -> Json:
    request = ContextPacketRequest(
        str(arguments["query_text"]),
        token_budget=int(arguments.get("token_budget") or 1200),
        categories=tuple(arguments.get("category") or []),
        root=resolve_root(arguments),
    )
    return {"packet": build_context_packet(request).to_dict()}


def call_save_insight(arguments: Json) -> Json:
    root = resolve_root(arguments)
    provider = resolve_provider()
    metadata = memory_manager.provider_metadata(
        origin_provider=provider,
        origin_agent=arguments.get("origin_agent"),
        source_session=arguments.get("source_session"),
        source_turn=arguments.get("source_turn"),
        cwd=arguments.get("cwd") or arguments.get("root"),
        branch=arguments.get("branch"),
        commit=arguments.get("commit"),
        capture_channel="mcp",
        applies_to_provider=arguments.get("applies_to_provider") or "all",
    )
    record = memory_manager.add_record(
        str(arguments["category"]),
        str(arguments["content"]),
        memory_manager.build_card_metadata(
            summary=arguments.get("summary"),
            details=arguments.get("details"),
            tags=list(arguments.get("tag") or []),
            source=f"{provider}_mcp",
            status=str(arguments.get("status") or "active"),
            importance=arguments.get("importance"),
            confidence=arguments.get("confidence"),
            base=metadata,
        ),
        root,
    )
    return {"action": "save-insight", "id": record.id, "category": record.category, "metadata": record.metadata}


def call_review_memory(arguments: Json) -> Json:
    request = ReviewRequest(
        root=resolve_root(arguments),
        statuses=tuple(arguments.get("status") or []),
        categories=tuple(arguments.get("category") or []),
        source=arguments.get("source"),
        limit=int(arguments.get("limit") or 20),
    )
    return review_memory(request).to_dict()


def call_initialize_project(arguments: Json) -> Json:
    root = resolve_root(arguments)
    if root is None:
        raise ValueError("initialize_project requires root.")
    cfg = recall_config.activate_project(root, activated_by=f"{resolve_provider()}_mcp")
    return {"action": "initialize-project", "root": str(root), "activation": cfg["activation"]}


TOOL_HANDLERS: dict[str, Callable[[Json], Json]] = {
    "retrieve_memory": call_retrieve_memory,
    "context_packet": call_context_packet,
    "save_insight": call_save_insight,
    "review_memory": call_review_memory,
    "initialize_project": call_initialize_project,
}


def send(payload: Json) -> None:
    sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def handle(request: Json) -> Json | None:
    method = request.get("method")
    request_id = request.get("id")
    try:
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "recall", "version": "1.1.0"},
            }
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = request.get("params") or {}
            name = str(params.get("name") or "")
            arguments = params.get("arguments") or {}
            if name not in TOOL_HANDLERS:
                raise ValueError(f"Unknown RECALL tool: {name}")
            if not isinstance(arguments, dict):
                raise ValueError("Tool arguments must be an object.")
            result = content_response(TOOL_HANDLERS[name](arguments))
        elif method and method.startswith("notifications/"):
            return None
        else:
            raise ValueError(f"Unsupported MCP method: {method}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except Exception as exc:  # noqa: BLE001 - MCP should return JSON-RPC errors.
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32000, "message": str(exc)},
        }


def main() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}})
            continue
        if not isinstance(request, dict):
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Request must be an object."}})
            continue
        response = handle(request)
        if response is not None:
            send(response)


if __name__ == "__main__":
    main()
