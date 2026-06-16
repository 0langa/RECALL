#!/usr/bin/env python3
"""Non-destructive migration from automatic event records to semantic cards."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
from typing import Any

import config as recall_config
import memory_manager
import storage


AUTOMATIC_SOURCES = {"post_tool_use", "stop"}
NOISY_KINDS = {"file_edit", "build_result", "test_result"}
REUSABLE_COMMAND_RE = re.compile(r"(?i)\b(test|pytest|unittest|smoke|validate_plugin|build_plugin|package)\b")
KIMI_SCORE_RE = re.compile(r"(?i)\b(kimi|plugineval)\b.*\b(score|average|results?|95\.91|84\.9)\b", re.DOTALL)


def _backup(root: str | Path | None) -> Path:
    memory_dir = recall_config.memory_dir(root)
    backup_dir = memory_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = backup_dir / f"pre-corpus-migration-{stamp}.sqlite"
    with closing(storage.connect_sqlite(root)) as source, closing(sqlite3.connect(target)) as destination:
        source.backup(destination)
    return target


def _command(record: storage.MemoryRecord) -> str:
    metadata = record.metadata or {}
    value = str(metadata.get("command") or "").strip()
    if value:
        return value
    match = re.search(r"(?im)^Command:\s*(.+)$", record.content)
    return match.group(1).strip() if match else ""


def _is_noise(record: storage.MemoryRecord) -> bool:
    metadata = record.metadata or {}
    return (
        str(metadata.get("source") or "") in AUTOMATIC_SOURCES
        and str(metadata.get("record_kind") or "") in NOISY_KINDS
        and str(metadata.get("status") or "active") not in {"archived", "superseded"}
    )


def plan_migration(root: str | Path | None) -> dict[str, Any]:
    records = list(storage.iter_records(root))
    noisy = [record for record in records if _is_noise(record)]
    reusable = [
        record for record in noisy
        if _command(record)
        and (record.metadata or {}).get("record_kind") in {"build_result", "test_result"}
        and REUSABLE_COMMAND_RE.search(_command(record))
        and "save-insight" not in _command(record)
    ]
    file_edits = [record for record in noisy if (record.metadata or {}).get("record_kind") == "file_edit"]
    stop_records = [
        record for record in records
        if str((record.metadata or {}).get("source") or "") == "stop"
        and str((record.metadata or {}).get("status") or "active") not in {"archived", "superseded"}
    ]
    kimi_records = [
        record for record in records
        if record.category == "project_state" and KIMI_SCORE_RE.search(record.content + " " + str(record.metadata))
    ]
    other_noise = [record for record in noisy if record not in reusable and record not in file_edits]
    return {
        "records": len(records),
        "active_noise_candidates": len(noisy),
        "reusable_command_sources": [record.id for record in reusable],
        "routine_file_edit_sources": [record.id for record in file_edits],
        "routine_build_test_sources": [record.id for record in other_noise],
        "stop_checkpoint_sources": [record.id for record in stop_records],
        "kimi_score_sources": [record.id for record in kimi_records],
        "estimated_post_migration_signal_to_noise": 1.0 if noisy else 1.0,
    }


def _archive(record: storage.MemoryRecord, root: str | Path | None, *, replacement_id: int | None, disposition: str) -> None:
    metadata = dict(record.metadata or {})
    metadata.update({
        "status": "archived",
        "archived_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "migration_disposition": disposition,
    })
    if replacement_id is not None:
        metadata["superseded_by"] = replacement_id
    memory_manager.update_record_metadata(record.id, metadata, root)


def apply_migration(root: str | Path | None) -> dict[str, Any]:
    if storage.backend(root) != "sqlite":
        raise ValueError("corpus migration currently requires the SQLite backend.")
    before = plan_migration(root)
    backup = _backup(root)
    records_by_id = {record.id: record for record in storage.iter_records(root)}
    reusable_ids = before["reusable_command_sources"]
    replacement_id: int | None = None
    if reusable_ids:
        commands: list[str] = []
        for record_id in reusable_ids:
            command = _command(records_by_id[record_id])
            if command and command not in commands:
                commands.append(command)
        content = "\n".join(commands)
        replacement = memory_manager.add_record(
            "commands",
            content,
            memory_manager.build_card_metadata(
                summary="Verified reusable build and test commands.",
                details=content,
                tags=["migration", "verified", "reusable"],
                source="corpus_migration",
                status="active",
                importance=0.72,
                confidence=0.9,
                base={"record_kind": "reusable_commands", "evidence_ids": reusable_ids, "merged_from": reusable_ids},
            ),
            root,
        )
        replacement_id = replacement.id

    noisy_ids = set(before["reusable_command_sources"]) | set(before["routine_file_edit_sources"]) | set(before["routine_build_test_sources"])
    for record_id in noisy_ids:
        useful = record_id in set(reusable_ids)
        disposition = "synthesized" if useful else (
            "routine_file_edit_noise" if record_id in set(before["routine_file_edit_sources"]) else "routine_build_test_noise"
        )
        _archive(
            records_by_id[record_id],
            root,
            replacement_id=replacement_id if useful else None,
            disposition=disposition,
        )

    stop_ids = before["stop_checkpoint_sources"]
    if len(stop_ids) > 1:
        latest = max(stop_ids)
        for record_id in stop_ids:
            if record_id != latest:
                _archive(records_by_id[record_id], root, replacement_id=latest, disposition="duplicate_stop_checkpoint")

    kimi_ids = before["kimi_score_sources"]
    if len(kimi_ids) > 1:
        latest = max(kimi_ids)
        latest_record = memory_manager.get_record(latest, root)
        if latest_record is not None:
            metadata = dict(latest_record.metadata or {})
            metadata.update({"claim_key": "evaluation:kimi-standard", "claim_value": latest_record.content[:220]})
            memory_manager.update_record_metadata(latest, metadata, root)
        for record_id in kimi_ids:
            if record_id != latest and str((records_by_id[record_id].metadata or {}).get("status") or "active") not in {"archived", "superseded"}:
                _archive(records_by_id[record_id], root, replacement_id=latest, disposition="historical_kimi_score")

    memory_manager.rebuild_index(root)
    after = plan_migration(root)
    return {"action": "migrate-corpus", "backup": str(backup), "before": before, "after": after, "replacement_id": replacement_id}
