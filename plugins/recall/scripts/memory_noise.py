#!/usr/bin/env python3
"""Find and archive low-value automatic memories."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import memory_lifecycle
import storage


READ_ONLY_RE = re.compile(
    r"(?i)\b("
    r"Get-Content|Get-ChildItem|Select-String|Select-Object|Get-Location|"
    r"rg\b|git\s+status\b|git\s+log\b|git\s+show\b|dir\b|ls\b|pwd\b|cat\b|type\b|"
    r"review-memory|retrieve-memory|codex\s+plugin\s+(?:marketplace\s+list|remove\s+--help)"
    r")"
)
GENERIC_SUMMARY_RE = re.compile(
    r"(?i)^(?:bash result captured\.?|tool result captured\.?|result: completed|tool:\s*bash\s+command:.*result:\s*completed)$"
)


def _metadata(record: storage.MemoryRecord) -> dict[str, Any]:
    return record.metadata if isinstance(record.metadata, dict) else {}


def archive_reason(record: storage.MemoryRecord) -> str | None:
    metadata = _metadata(record)
    status = str(metadata.get("status", "active")).lower()
    if status in {"archived", "superseded", "resolved"}:
        return None
    source = str(metadata.get("source", "")).lower()
    if source != "post_tool_use":
        return None

    text = " ".join(
        value
        for value in [
            record.content,
            str(metadata.get("summary", "")),
            str(metadata.get("details", "")),
        ]
        if value
    )
    lowered = text.lower()
    if "failed" in lowered or "traceback" in lowered or "exception" in lowered or "error" in lowered:
        return None
    if record.category == "commands" and (
        GENERIC_SUMMARY_RE.search(str(metadata.get("summary", "")).strip())
        or GENERIC_SUMMARY_RE.search(record.content.strip())
        or READ_ONLY_RE.search(text)
    ):
        return "Archived low-value automatic post_tool_use command memory."
    return None


def archive_noise(
    root: str | Path | None = None,
    *,
    apply: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    archived: list[dict[str, Any]] = []
    for record in storage.iter_records(root):
        reason = archive_reason(record)
        if reason is None:
            continue
        metadata = _metadata(record)
        item = {
            "id": record.id,
            "category": record.category,
            "summary": metadata.get("summary") or record.content[:180],
            "reason": reason,
        }
        matches.append(item)
        if apply:
            updated = memory_lifecycle.prune(record.id, root, reason)
            archived.append(
                {
                    "id": updated.id,
                    "status": updated.metadata.get("status"),
                    "archived_at": updated.metadata.get("archived_at"),
                }
            )
        if limit is not None and len(matches) >= limit:
            break
    return {
        "action": "archive-noise",
        "mode": "apply" if apply else "dry-run",
        "matched": len(matches),
        "archived": len(archived),
        "memories": archived if apply else matches,
    }
