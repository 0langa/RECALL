"""Prompt construction for the RECALL Stop-hook finalizer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def compact_packet(packet: dict[str, Any]) -> dict[str, Any]:
    signal_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    for item in packet.get("candidate_summary", []):
        if isinstance(item, dict):
            signal = str(item.get("signal") or "unknown")
            category = str(item.get("category_hint") or "unknown")
            signal_counts[signal] = signal_counts.get(signal, 0) + 1
            category_counts[category] = category_counts.get(category, 0) + 1
    packet_path = packet.get("packet_path")
    cwd = packet.get("cwd")
    if isinstance(packet_path, str) and isinstance(cwd, str):
        try:
            packet_path = str(Path(packet_path).resolve().relative_to(Path(cwd).resolve()))
        except (OSError, ValueError):
            pass
    return {
        "schema": packet.get("schema"),
        "session_id": packet.get("session_id"),
        "turn_id": packet.get("turn_id"),
        "packet_path": packet_path,
        "candidate_count": packet.get("candidate_count"),
        "signal_counts": signal_counts,
        "category_counts": category_counts,
    }


def build_finalizer_prompt(packet_path: str, packet: dict[str, Any] | None = None) -> str:
    inline_packet = ""
    if packet is not None:
        payload = dict(packet)
        payload["packet_path"] = packet_path
        inline_packet = json.dumps(compact_packet(payload), sort_keys=True)
    return "\n".join(
        [
            "RECALL_FINALIZER_REQUEST",
            "Run one memory pass, then stop.",
            "Read packet_path only if needed. Use only the adapter named inside that packet. No source edits. No secrets.",
            "Max 3 new cards and 8 total operations.",
            "Submit exactly one recall.finalizer_batch.v1 object with apply-finalizer-batch --stdin.",
            "Store only future-useful decisions, requirements, risks, commands, architecture, lessons, or project state.",
            "If nothing durable changed, store nothing.",
            f"PACKET={inline_packet or json.dumps({'packet_path': packet_path}, sort_keys=True)}",
            "Steps: review-memory/retrieve-memory, decide, apply one atomic batch, short summary.",
        ]
    )
