#!/usr/bin/env python3
"""Write policy decisions for automatic RECALL hook memories."""

from __future__ import annotations

import re
from typing import Any, NamedTuple

from embedder import tokenize
import memory_hygiene


SUPERSESSION_RE = re.compile(r"(?i)\b(?:supersedes|replaces|correction to)\s+memory\s+#?(\d+)\b")
LOW_SIGNAL_COMMAND_RE = re.compile(
    r"(?i)^\s*(?:Get-ChildItem|ls|dir|pwd|cd\b|git status\b|git branch\b|Get-Location\b)"
)


class WriteDecision(NamedTuple):
    action: str
    reason: str
    related_id: int | None = None
    similarity: float | None = None
    supersedes_id: int | None = None


def supersession_target(content: str) -> int | None:
    match = SUPERSESSION_RE.search(content)
    return int(match.group(1)) if match else None


def is_low_signal_command(content: str, metadata: dict[str, Any]) -> bool:
    if str(metadata.get("source", "")).lower() != "post_tool_use":
        return False
    command = str(metadata.get("command") or "").strip()
    if not command or not LOW_SIGNAL_COMMAND_RE.search(command):
        return False
    lowered = content.lower()
    if any(signal in lowered for signal in ("error", "failed", "traceback", "assertionerror")):
        return False
    return "result: completed" in lowered or "exit_code: 0" in lowered


def is_generic_checkpoint(content: str, metadata: dict[str, Any]) -> bool:
    source = str(metadata.get("source", "")).lower()
    if source not in {"pre_compact", "stop"}:
        return False
    tokens = set(tokenize(content))
    if len(tokens) <= 4:
        return True
    generic = {"completed", "done", "ok", "finished", "checkpoint", "session", "task"}
    return bool(tokens) and len(tokens - generic) <= 1


def classify_write(
    category: str,
    content: str,
    metadata: dict[str, Any] | None,
    root: str | None = None,
) -> WriteDecision:
    metadata = metadata or {}
    supersedes_id = supersession_target(content)
    if is_low_signal_command(content, metadata):
        return WriteDecision("ignore", "low_signal_command")
    if is_generic_checkpoint(content, metadata):
        return WriteDecision("ignore", "generic_checkpoint")

    related = memory_hygiene.find_related_record(category, content, metadata, root)
    if related and related.kind == "exact":
        return WriteDecision("update_existing", "exact_duplicate", related.record.id, 1.0, supersedes_id)
    if related and related.kind == "near":
        return WriteDecision("save_new", "near_duplicate", related.record.id, related.similarity, supersedes_id)
    if supersedes_id is not None:
        return WriteDecision("save_new", "explicit_supersession", supersedes_id=supersedes_id)
    return WriteDecision("save_new", "new_memory")
