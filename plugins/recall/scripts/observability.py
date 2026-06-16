"""Redacted, runtime-only RECALL debug traces."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import config as recall_config
import security


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def debug_dir(root: str | Path) -> Path:
    return recall_config.memory_dir(root) / "runtime" / "debug"


def enabled(root: str | Path | None) -> bool:
    if root is None or not recall_config.persistent_memory_exists(root):
        return False
    return recall_config.load_config_if_present(root).get("observability_mode") == "debug"


def cleanup(root: str | Path) -> None:
    directory = debug_dir(root)
    if not directory.exists():
        return
    cfg = recall_config.load_config_if_present(root)
    cutoff = utc_now() - timedelta(days=int(cfg.get("debug_retention_days", 7)))
    for path in directory.glob("*.jsonl"):
        modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        if modified < cutoff:
            path.unlink(missing_ok=True)


def trace(root: str | Path | None, event: str, details: dict[str, Any]) -> None:
    if root is None or not enabled(root):
        return
    cleanup(root)
    directory = debug_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": utc_now().isoformat(timespec="seconds"),
        "event": event,
        "details": security.redact_value(details),
    }
    path = directory / f"{utc_now().date().isoformat()}.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")

