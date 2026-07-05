"""Quality probes: graded checks against fabricated ground truth.

Probes call the real MCP surface and grade responses against the store
manifest. All deterministic; results land in the journal as `probe` events.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .drivers import McpClient
from .recorder import Recorder
from .store_fabricator import SECRET_MARKER


def _record_tool(recorder: Recorder, *, name: str, raw: str, duration_ms: float, scenario: str) -> None:
    channel = {
        "retrieve_memory": "tool_result_retrieve",
        "context_packet": "tool_result_context_packet",
        "save_insight": "tool_result_save",
        "update_memory": "tool_result_update",
        "review_memory": "tool_result_review",
        "memory_hygiene": "tool_result_hygiene",
        "memory_contract": "tool_result_contract",
        "initialize_project": "tool_result_initialize",
    }.get(name, "tool_result_diagnostics")
    recorder.record(channel=channel, text=raw, scenario=scenario, session=0, surface=f"mcp:{name}", duration_ms=duration_ms)


def run_probes(recorder: Recorder, *, root: Path, manifest: dict[str, Any], scenario: str, limit: int = 5) -> None:
    mcp = McpClient()
    try:
        _retrieval_probes(recorder, mcp, root=root, manifest=manifest, scenario=scenario, limit=limit)
        _flag_probes(recorder, mcp, root=root, manifest=manifest, scenario=scenario)
        _conflict_probes(recorder, mcp, root=root, manifest=manifest, scenario=scenario)
        _dedup_probes(recorder, mcp, root=root, scenario=scenario)
        _secret_probes(recorder, mcp, root=root, scenario=scenario)
        _verbose_delta_probe(recorder, mcp, root=root, scenario=scenario)
        _hygiene_probes(recorder, mcp, root=root, manifest=manifest, scenario=scenario)
        _contract_probe(recorder, mcp, root=root, scenario=scenario)
    finally:
        mcp.close()


def _retrieval_probes(recorder: Recorder, mcp: McpClient, *, root: Path, manifest: dict[str, Any], scenario: str, limit: int) -> None:
    for golden in manifest.get("golden", []):
        payload, raw, duration_ms = mcp.call_tool("retrieve_memory", {"root": str(root), "query_text": golden["query"], "limit": limit})
        _record_tool(recorder, name="retrieve_memory", raw=raw, duration_ms=duration_ms, scenario=scenario)
        ids = [item["id"] for item in payload.get("results", [])]
        rank = ids.index(golden["id"]) + 1 if golden["id"] in ids else None
        recorder.event("probe", {
            "probe": "golden_retrieval", "scenario": scenario, "query": golden["query"],
            "expected_id": golden["id"], "hit": rank is not None, "rank": rank,
            "duration_ms": round(duration_ms, 2),
        })


def _flag_probes(recorder: Recorder, mcp: McpClient, *, root: Path, manifest: dict[str, Any], scenario: str) -> None:
    expected_flags = {"stale": "stale", "superseded": "superseded", "deprecated": "deprecated", "hypothesis": "needs_verification"}
    for card in manifest.get("flagged", []):
        # limit 20: retired statuses carry heavy score penalties by design, so
        # give them room to surface — the probe grades flag text, not rank.
        payload, raw, duration_ms = mcp.call_tool(
            "retrieve_memory",
            {"root": str(root), "query_text": card["query"], "limit": 20,
             "status": ["stale", "superseded", "deprecated", "hypothesis", "active", "validated"]},
        )
        _record_tool(recorder, name="retrieve_memory", raw=raw, duration_ms=duration_ms, scenario=scenario)
        found = next((item for item in payload.get("results", []) if item["id"] == card["id"]), None)
        recorder.event("probe", {
            "probe": "flag_correctness", "scenario": scenario, "id": card["id"],
            "expected_flag": expected_flags[card["status"]],
            "actual_flag": found.get("flag") if found else None,
            "correct": bool(found and found.get("flag") == expected_flags[card["status"]]),
        })


def _conflict_probes(recorder: Recorder, mcp: McpClient, *, root: Path, manifest: dict[str, Any], scenario: str) -> None:
    if not manifest.get("conflicts"):
        return
    payload, raw, duration_ms = mcp.call_tool("retrieve_memory", {"root": str(root), "query_text": "default branch policy", "limit": 10})
    _record_tool(recorder, name="retrieve_memory", raw=raw, duration_ms=duration_ms, scenario=scenario)
    conflict_ids = {card["id"] for card in manifest["conflicts"]}
    marked = [item["id"] for item in payload.get("results", []) if item.get("flag") == "conflicting" and item["id"] in conflict_ids]
    recorder.event("probe", {
        "probe": "conflict_marking", "scenario": scenario,
        "expected_ids": sorted(conflict_ids), "marked_ids": sorted(marked),
        "correct": set(marked) == conflict_ids,
        "next_action_present": "next_action" in payload.get("health", {}),
    })


def _dedup_probes(recorder: Recorder, mcp: McpClient, *, root: Path, scenario: str) -> None:
    fact = "Bench dedup probe: the artifact registry only accepts signed uploads."
    first, raw1, ms1 = mcp.call_tool("save_insight", {"root": str(root), "category": "constraints", "content": fact})
    _record_tool(recorder, name="save_insight", raw=raw1, duration_ms=ms1, scenario=scenario)
    second, raw2, ms2 = mcp.call_tool("save_insight", {"root": str(root), "category": "constraints", "content": fact})
    _record_tool(recorder, name="save_insight", raw=raw2, duration_ms=ms2, scenario=scenario)
    distinct, raw3, ms3 = mcp.call_tool("save_insight", {"root": str(root), "category": "constraints", "content": "Bench distinct probe: pipeline artifacts expire after ninety days in the local registry cache."})
    _record_tool(recorder, name="save_insight", raw=raw3, duration_ms=ms3, scenario=scenario)
    recorder.event("probe", {
        "probe": "dedup", "scenario": scenario,
        "first_result": first.get("result"), "duplicate_result": second.get("result"),
        "duplicate_confirmed_existing": second.get("result") == "updated_existing" and second.get("id") == first.get("id"),
        "distinct_saved": distinct.get("result") == "saved",
        "teaches_next_action": "next_action" in second,
    })


def _secret_probes(recorder: Recorder, mcp: McpClient, *, root: Path, scenario: str) -> None:
    payload, raw, duration_ms = mcp.call_tool(
        "save_insight",
        {"root": str(root), "category": "commands", "content": f"Deploy token = {SECRET_MARKER}"},
    )
    _record_tool(recorder, name="save_insight", raw=raw, duration_ms=duration_ms, scenario=scenario)
    recorder.event("probe", {
        "probe": "secret_rejection", "scenario": scenario,
        "rejected": payload.get("result") == "rejected",
        "reason_mentions_secret": "secret" in str(payload.get("reason", "")),
    })


def _verbose_delta_probe(recorder: Recorder, mcp: McpClient, *, root: Path, scenario: str) -> None:
    compact, raw_compact, _ = mcp.call_tool("retrieve_memory", {"root": str(root), "query_text": "signed uploads registry", "limit": 5})
    verbose, raw_verbose, _ = mcp.call_tool("retrieve_memory", {"root": str(root), "query_text": "signed uploads registry", "limit": 5, "verbose": True})
    recorder.event("probe", {
        "probe": "compact_vs_verbose", "scenario": scenario,
        "compact_chars": len(raw_compact), "verbose_chars": len(raw_verbose),
        "compact_is_smaller": len(raw_compact) < len(raw_verbose),
        "compact_has_no_metadata": all("metadata" not in item for item in compact.get("results", [])),
        "verbose_has_metadata": bool(verbose.get("results")) and all("metadata" in item for item in verbose.get("results", [])),
    })


def _hygiene_probes(recorder: Recorder, mcp: McpClient, *, root: Path, manifest: dict[str, Any], scenario: str) -> None:
    if not manifest.get("bad"):
        return
    plan, raw, duration_ms = mcp.call_tool("memory_hygiene", {"root": str(root), "mode": "plan"})
    _record_tool(recorder, name="memory_hygiene", raw=raw, duration_ms=duration_ms, scenario=scenario)
    proposals = {(p.get("id"), p.get("proposed_action")) for p in plan.get("proposals", [])}
    proposal_ids = {p.get("id") for p in plan.get("proposals", [])}
    expected_actions = {
        "secret": "redact_secret", "raw_log": "prune", "vague": "review_vague",
        "aged_snapshot": "stale", "exact_duplicate": "merge", "metadata_gap": "review_metadata",
    }
    detections: dict[str, bool] = {}
    for bad in manifest["bad"]:
        expected = expected_actions[bad["kind"]]
        detections[f"{bad['kind']}#{bad['id']}"] = (bad["id"], expected) in proposals or (
            bad["kind"] == "exact_duplicate" and bad["id"] in proposal_ids
        )
    golden_ids = {card["id"] for card in manifest.get("golden", [])}
    false_positives = sorted(golden_ids & proposal_ids)
    recorder.event("probe", {
        "probe": "hygiene_detection", "scenario": scenario, "detections": detections,
        "detection_rate": round(sum(detections.values()) / max(1, len(detections)), 4),
        "false_positive_golden_ids": false_positives,
    })
    applied, raw_apply, ms_apply = mcp.call_tool("memory_hygiene", {"root": str(root), "mode": "apply_safe"})
    _record_tool(recorder, name="memory_hygiene", raw=raw_apply, duration_ms=ms_apply, scenario=scenario)
    secret_ids = [bad["id"] for bad in manifest["bad"] if bad["kind"] == "secret"]
    leak_after_apply = _store_contains_marker(root)
    recorder.event("probe", {
        "probe": "hygiene_apply_safe", "scenario": scenario,
        "applied_count": applied.get("applied_count"),
        "secret_redacted_in_store": not leak_after_apply,
        "secret_ids": secret_ids,
    })


def _store_contains_marker(root: Path) -> bool:
    import sqlite3

    db = root / ".recall" / "memory.sqlite"
    connection = sqlite3.connect(db)
    try:
        row = connection.execute("SELECT COUNT(*) FROM memories WHERE content LIKE ?", (f"%{SECRET_MARKER}%",)).fetchone()
        return bool(row and row[0])
    finally:
        connection.close()


def _contract_probe(recorder: Recorder, mcp: McpClient, *, root: Path, scenario: str) -> None:
    payload, raw, duration_ms = mcp.call_tool("memory_contract", {"root": str(root)})
    _record_tool(recorder, name="memory_contract", raw=raw, duration_ms=duration_ms, scenario=scenario)
    contract = payload.get("contract", {})
    recorder.event("probe", {
        "probe": "contract_exposure", "scenario": scenario,
        "authority_order_first": (contract.get("authority_order") or [None])[0],
        "lifecycle_steps": len(contract.get("lifecycle", [])),
        "categories_included": "tooling_quirks" in payload.get("categories", {}),
        "chars": len(raw),
    })
