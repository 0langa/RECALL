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
import contract as recall_contract
import memory_hygiene
import memory_manager
import security
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
        "description": (
            "Retrieve relevant RECALL memories from the project's local store. Call this BEFORE starting "
            "work on bug fixes, unfamiliar code, repeated failures, provider/plugin tasks, security-sensitive "
            "changes, or after context loss. Results carry a `flag` (current/stale/superseded/deprecated/"
            "needs_verification/conflicting); treat anything not `current` as unverified."
        ),
        "inputSchema": tool_schema(
            {
                "query_text": {"type": "string"},
                "category": {"type": "array", "items": {"type": "string"}},
                "status": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                "summary": {"type": "boolean"},
                "verbose": {
                    "type": "boolean",
                    "description": "Include full metadata per result. Default false: compact, token-lean results.",
                },
            },
            ["query_text"],
        ),
    },
    {
        "name": "context_packet",
        "description": (
            "Build a compact, token-budgeted packet of the most relevant project memories. Best first call "
            "when starting a new session or continuing after context loss."
        ),
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
        "description": (
            "Save a verified, durable, project-specific insight to RECALL memory. Do NOT save secrets, raw "
            "logs, transient status, drafts, or facts already in repo docs. Duplicate-shaped saves are "
            "detected: the response may confirm an existing memory instead of appending. When a stored fact "
            "changed, prefer update_memory over saving a near-duplicate."
        ),
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
                "claim_key": {
                    "type": "string",
                    "description": "Stable key for a single-truth claim (enables conflict detection).",
                },
                "claim_value": {"type": "string"},
                "preference_key": {
                    "type": "string",
                    "description": "Required for category=preferences: stable key naming the preference.",
                },
                "preference_evidence_type": {
                    "type": "string",
                    "description": (
                        "Required for category=preferences. Use explicit_declaration when the user stated the "
                        "preference; approved_plan/accepted_edit/rejected_edit etc. for observed evidence."
                    ),
                },
                "decision_id": {"type": "string"},
            },
            ["category", "content"],
        ),
    },
    {
        "name": "review_memory",
        "description": (
            "Inspect inventory and health of the project's RECALL memory (read-only). Use to gather memory "
            "IDs before update_memory or memory_hygiene operations."
        ),
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
        "name": "update_memory",
        "description": (
            "Change the lifecycle state or content of an existing memory. Use op=update to correct content, "
            "op=confirm when a memory was re-verified, op=stale when its source changed, op=deprecate when "
            "it is wrong or retired, op=supersede (old id + new_id) when a new memory replaces an old one, "
            "op=merge (id + secondary_ids) to fold duplicates into one card, op=resolve to close an open "
            "issue, op=prune to archive noise. Wrong memory must never stay silently authoritative."
        ),
        "inputSchema": tool_schema(
            {
                "op": {
                    "type": "string",
                    "enum": ["update", "confirm", "stale", "deprecate", "supersede", "merge", "resolve", "prune"],
                },
                "id": {"type": "integer", "minimum": 1},
                "new_id": {"type": "integer", "minimum": 1, "description": "Replacement memory id for op=supersede."},
                "secondary_ids": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 1},
                    "description": "Duplicate memory ids folded into `id` for op=merge.",
                },
                "content": {"type": "string", "description": "Corrected content for op=update."},
                "summary": {"type": "string"},
                "category": {"type": "string"},
                "status": {"type": "string"},
                "note": {"type": "string", "description": "Why this lifecycle change is happening."},
            },
            ["op", "id"],
        ),
    },
    {
        "name": "memory_hygiene",
        "description": (
            "Keep the memory store trustworthy. mode=route decides whether candidate text belongs in memory, "
            "repo docs, provider config, or nowhere (call before uncertain saves). mode=scan audits the store "
            "for duplicates, conflicts, stale/source-drifted cards, secret-shaped content, raw logs, and vague "
            "memories. mode=plan lists concrete repair proposals. mode=apply_safe applies only safe, "
            "non-destructive repairs; risky ones stay proposals for review."
        ),
        "inputSchema": tool_schema(
            {
                "mode": {"type": "string", "enum": ["route", "scan", "plan", "apply_safe"]},
                "text": {"type": "string", "description": "Candidate text for mode=route."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                "claim_key": {"type": "string", "description": "Optional claim to reconcile in mode=plan."},
            },
            ["mode"],
        ),
    },
    {
        "name": "memory_contract",
        "description": (
            "Return RECALL's memory lifecycle contract: source authority order, when to retrieve, what to "
            "save vs skip, status meanings, and category guidance. Call after context loss or when unsure "
            "how to use memory correctly."
        ),
        "inputSchema": tool_schema({}),
    },
    {
        "name": "initialize_project",
        "description": (
            "Activate RECALL for a project: creates .recall/ config with category definitions and returns "
            "the lifecycle contract plus first-workflow guidance. Safe to re-run."
        ),
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
        verbose=bool(arguments.get("verbose")),
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
    content = str(arguments["content"])
    summary = arguments.get("summary")
    details = arguments.get("details")
    if security.contains_secret(content, summary, details):
        return {
            "action": "save-insight",
            "result": "rejected",
            "reason": "secret-like content must not be stored",
            "next_action": (
                "Remove the secret value and save only the non-sensitive insight "
                "(for example where the credential is configured, never its value)."
            ),
        }
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
    for extra_key in ("claim_key", "claim_value", "preference_key", "preference_evidence_type", "decision_id"):
        value = arguments.get(extra_key)
        if value is not None and str(value).strip():
            metadata[extra_key] = str(value).strip()
    outcome = memory_manager.add_record_if_useful(
        str(arguments["category"]),
        content,
        memory_manager.build_card_metadata(
            summary=summary,
            details=details,
            tags=list(arguments.get("tag") or []),
            source=f"{provider}_mcp",
            status=str(arguments.get("status") or "active"),
            importance=arguments.get("importance"),
            confidence=arguments.get("confidence"),
            base=metadata,
        ),
        root,
    )
    record = outcome.get("record")
    response: Json = {"action": "save-insight", "result": outcome.get("action")}
    if outcome.get("reason"):
        response["reason"] = outcome["reason"]
    if record is not None:
        response.update({"id": record.id, "category": record.category, "metadata": record.metadata})
    if outcome.get("action") == "updated_existing" and record is not None:
        response["next_action"] = (
            f"Existing memory #{record.id} covered this insight and was confirmed instead of duplicated. "
            f"If the fact changed, call update_memory with op=update and id={record.id}."
        )
    elif outcome.get("action") == "saved_related" and record is not None:
        related = (record.metadata or {}).get("related_memory_id")
        response["next_action"] = (
            f"Saved, but memory #{related} is similar. If they describe the same fact, call update_memory "
            f"with op=merge, id={record.id}, secondary_ids=[{related}]."
        )
    elif outcome.get("action") == "ignored":
        if "preference" in str(outcome.get("reason") or ""):
            response["next_action"] = (
                "Preferences need evidence: retry with preference_key and preference_evidence_type="
                "explicit_declaration when the user stated it directly, or a durable decision type plus decision_id."
            )
        else:
            response["next_action"] = (
                "Nothing was stored. If this insight is genuinely durable and new, rephrase it as a specific, "
                "verifiable fact and retry; otherwise keep it out of memory."
            )
    return response


def call_review_memory(arguments: Json) -> Json:
    request = ReviewRequest(
        root=resolve_root(arguments),
        statuses=tuple(arguments.get("status") or []),
        categories=tuple(arguments.get("category") or []),
        source=arguments.get("source"),
        limit=int(arguments.get("limit") or 20),
    )
    return review_memory(request).to_dict()


def _record_summary(record: Any) -> Json:
    return {"id": record.id, "category": record.category, "status": (record.metadata or {}).get("status"), "metadata": record.metadata}


def call_update_memory(arguments: Json) -> Json:
    from services import lifecycle_service

    root = resolve_root(arguments)
    op = str(arguments["op"]).strip().lower()
    record_id = int(arguments["id"])
    note = arguments.get("note")
    if op == "update":
        content = arguments.get("content")
        summary = arguments.get("summary")
        if security.contains_secret(content, summary):
            return {
                "action": "update-memory",
                "op": op,
                "result": "rejected",
                "reason": "secret-like content must not be stored",
                "next_action": "Remove the secret value and retry with only the non-sensitive fact.",
            }
        record = memory_manager.edit_record(
            record_id,
            root,
            category=arguments.get("category"),
            content=content,
            summary=summary,
            status=arguments.get("status"),
        )
    elif op == "confirm":
        record = memory_manager.confirm_record(record_id, root)
    elif op == "stale":
        record = memory_manager.mark_record_stale(record_id, root, note)
    elif op == "deprecate":
        record = lifecycle_service.deprecate(record_id, root, note)
    elif op == "resolve":
        record = memory_manager.resolve_record(record_id, root, note)
    elif op == "prune":
        record = memory_manager.prune_record(record_id, root, note)
    elif op == "supersede":
        new_id = arguments.get("new_id")
        if new_id is None:
            raise ValueError("op=supersede requires new_id (the replacement memory). Save the replacement first with save_insight.")
        result = memory_manager.supersede_record(record_id, int(new_id), root, note)
        return {
            "action": "update-memory",
            "op": op,
            "result": "superseded",
            "old": _record_summary(result["old"]),
            "new": _record_summary(result["new"]),
        }
    elif op == "merge":
        secondary_ids: list[int | str] = [int(value) for value in (arguments.get("secondary_ids") or [])]
        if not secondary_ids:
            raise ValueError("op=merge requires secondary_ids (the duplicate memories to fold into id).")
        result = memory_manager.merge_records(record_id, secondary_ids, root, note)
        return {"action": "update-memory", "op": op, "result": "merged", "primary": _record_summary(result["primary"]), "merged_ids": secondary_ids}
    else:
        raise ValueError(f"Unknown update_memory op: {op}")
    return {"action": "update-memory", "op": op, "result": "ok", "record": _record_summary(record)}


def call_memory_hygiene(arguments: Json) -> Json:
    root = resolve_root(arguments)
    mode = str(arguments["mode"]).strip().lower()
    limit = int(arguments["limit"]) if arguments.get("limit") is not None else None
    if mode == "route":
        text = str(arguments.get("text") or "").strip()
        if not text:
            raise ValueError("mode=route requires text (the candidate fact to route).")
        return memory_hygiene.route_memory(text)
    if mode == "scan":
        return memory_hygiene.hygiene_scan(root, limit=limit)
    if mode == "plan":
        claim_key = arguments.get("claim_key")
        if claim_key:
            return memory_hygiene.reconcile_current_truth(root, claim_key=str(claim_key))
        return memory_hygiene.hygiene_plan(root, limit=limit)
    if mode == "apply_safe":
        return memory_hygiene.hygiene_apply(root, safe=True, limit=limit)
    raise ValueError(f"Unknown memory_hygiene mode: {mode}")


def call_memory_contract(arguments: Json) -> Json:
    cfg = recall_config.load_config_if_present(resolve_root(arguments))
    return {
        "action": "memory-contract",
        "contract": recall_contract.contract_dict(),
        "categories": cfg.get("categories", {}),
    }


def call_initialize_project(arguments: Json) -> Json:
    root = resolve_root(arguments)
    if root is None:
        raise ValueError("initialize_project requires root.")
    cfg = recall_config.activate_project(root, activated_by=f"{resolve_provider()}_mcp")
    gitignore = recall_config.ensure_gitignore_entries(root)
    return {
        "action": "initialize-project",
        "root": str(root),
        "activation": cfg["activation"],
        "gitignore": gitignore,
        "categories": sorted(cfg.get("categories", {})),
        "contract": recall_contract.compact_contract_text(),
        "first_workflow": (
            "1) retrieve_memory or context_packet before starting work; 2) work normally; "
            "3) save_insight only for durable verified facts; 4) update_memory when stored facts change; "
            "5) memory_hygiene mode=scan periodically."
        ),
    }


TOOL_HANDLERS: dict[str, Callable[[Json], Json]] = {
    "retrieve_memory": call_retrieve_memory,
    "context_packet": call_context_packet,
    "save_insight": call_save_insight,
    "review_memory": call_review_memory,
    "update_memory": call_update_memory,
    "memory_hygiene": call_memory_hygiene,
    "memory_contract": call_memory_contract,
    "initialize_project": call_initialize_project,
}


def send(payload: Json) -> None:
    sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def handle(request: Json) -> Json | None:
    method = request.get("method")
    request_id = request.get("id")
    try:
        result: Json
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "recall", "version": "1.5.2"},
                "instructions": recall_contract.compact_contract_text(),
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
