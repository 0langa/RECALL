"""File provenance and repository reconciliation for RECALL memories."""

from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config as recall_config
import storage


IGNORED_PARTS = {".git", ".codex_memory", "__pycache__", "node_modules", "dist"}


def utc_now() -> str:
    """Return a stable UTC timestamp."""

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_file(path: Path) -> str:
    """Return a SHA-256 digest for one file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_relative_path(root: str | Path, path: str | Path) -> str:
    """Return a normalized project-relative path or reject scope escape."""

    project = recall_config.project_root(root)
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = project / candidate
    resolved = candidate.expanduser().resolve(strict=False)
    try:
        relative = resolved.relative_to(project)
    except ValueError as exc:
        raise ValueError(f"source path is outside project root: {path}") from exc
    return relative.as_posix()


def git_revision(root: str | Path) -> str | None:
    """Return current Git revision when the project is a repository."""

    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=recall_config.project_root(root),
        text=True,
        capture_output=True,
        check=False,
        timeout=5,
    )
    return completed.stdout.strip() or None if completed.returncode == 0 else None


def describe_file(root: str | Path, path: str | Path) -> dict[str, Any]:
    """Build provenance metadata for an existing project file."""

    relative = project_relative_path(root, path)
    absolute = recall_config.project_root(root) / relative
    if not absolute.is_file():
        raise FileNotFoundError(f"source file does not exist: {relative}")
    return {
        "source": relative,
        "source_kind": "file",
        "source_path": relative,
        "source_hash": hash_file(absolute),
        "source_revision": git_revision(root),
        "source_checked_at": utc_now(),
    }


def _find_hash(root: str | Path, expected_hash: str, missing_path: str) -> str | None:
    project = recall_config.project_root(root)
    for candidate in project.rglob("*"):
        if not candidate.is_file() or any(part in IGNORED_PARTS for part in candidate.parts):
            continue
        relative = candidate.relative_to(project).as_posix()
        if relative.casefold() == missing_path.casefold():
            continue
        try:
            if hash_file(candidate) == expected_hash:
                return relative
        except OSError:
            continue
    return None


def _mark_invalid(record: storage.MemoryRecord, reason: str, root: str | Path, **details: Any) -> storage.MemoryRecord:
    metadata = dict(record.metadata or {})
    metadata.update(details)
    metadata["status"] = "stale"
    metadata["invalidation_reason"] = reason
    metadata["invalidated_at"] = utc_now()
    return storage.update_record_metadata(record.id, metadata, root)


def invalidate_by_file(path: str | Path, root: str | Path) -> dict[str, Any]:
    """Mark every memory linked to a project file as stale."""

    relative = project_relative_path(root, path)
    changed = []
    for record in storage.iter_records(root):
        source_path = str((record.metadata or {}).get("source_path", ""))
        if source_path.casefold() == relative.casefold():
            changed.append(_mark_invalid(record, "source_invalidated", root).id)
    return {"source_path": relative, "invalidated_ids": changed, "count": len(changed)}


def refresh_source(record_id: int, root: str | Path) -> storage.MemoryRecord:
    """Refresh one memory's file hash and restore active status."""

    record = storage.get_record(record_id, root)
    if record is None:
        raise KeyError(f"RECALL memory #{record_id} was not found.")
    metadata = dict(record.metadata or {})
    source_path = metadata.get("replacement_source_path") or metadata.get("source_path")
    if not source_path:
        raise ValueError(f"RECALL memory #{record_id} has no file source.")
    descriptor = describe_file(root, str(source_path))
    metadata.update(descriptor)
    metadata["status"] = "active"
    metadata["updated_at"] = utc_now()
    for key in ("invalidation_reason", "invalidated_at", "replacement_source_path"):
        metadata.pop(key, None)
    return storage.update_record_metadata(record.id, metadata, root)


def reconcile_sources(root: str | Path) -> dict[str, Any]:
    """Find modified, deleted, or moved file sources missed by hooks."""

    project = recall_config.project_root(root)
    report: dict[str, Any] = {"checked": 0, "current": 0, "modified": 0, "deleted": 0, "moved": 0, "ids": []}
    for record in list(storage.iter_records(root)):
        metadata = record.metadata or {}
        if metadata.get("source_kind") != "file" or not metadata.get("source_path"):
            continue
        report["checked"] += 1
        relative = project_relative_path(project, str(metadata["source_path"]))
        source = project / relative
        expected_hash = str(metadata.get("source_hash") or "")
        if source.is_file():
            if expected_hash and hash_file(source) != expected_hash:
                _mark_invalid(record, "source_modified", project, observed_source_hash=hash_file(source))
                report["modified"] += 1
                report["ids"].append(record.id)
            else:
                report["current"] += 1
            continue
        replacement = _find_hash(project, expected_hash, relative) if expected_hash else None
        if replacement:
            _mark_invalid(record, "source_moved", project, replacement_source_path=replacement)
            report["moved"] += 1
        else:
            _mark_invalid(record, "source_deleted", project)
            report["deleted"] += 1
        report["ids"].append(record.id)
    return report
