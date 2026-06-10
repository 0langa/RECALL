"""Prompt construction for the RECALL Stop-hook finalizer."""

from __future__ import annotations

import json
from typing import Any


def compact_packet(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": packet.get("schema"),
        "session_id": packet.get("session_id"),
        "turn_id": packet.get("turn_id"),
        "cwd": packet.get("cwd"),
        "adapter": packet.get("adapter"),
        "packet_path": packet.get("packet_path"),
        "candidate_count": packet.get("candidate_count"),
        "candidate_summary": packet.get("candidate_summary", [])[:8],
        "policy": packet.get("policy", {}),
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
            "Use only the adapter in PACKET. No source edits. No secrets. Max 5 new cards.",
            "Prefer lifecycle updates or pruning over duplicates. Use save-turn-card only for new durable facts.",
            "Store only future-useful decisions, requirements, risks, commands, architecture, lessons, or project state.",
            "If nothing durable changed, store nothing.",
            f"PACKET={inline_packet or json.dumps({'packet_path': packet_path}, sort_keys=True)}",
            "Steps: review-memory/retrieve-memory, decide, smallest useful write/update, short summary.",
        ]
    )
