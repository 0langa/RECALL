"""Find and undo text garbled by the pre-1.6.1 Windows MCP input bug.

Before 1.6.1 the MCP server and the `--stdin` CLI paths read UTF-8 input with
the Windows code page, so "Grüße" was saved as "GrÃ¼ÃŸe". Only text whose
cp1252 bytes are valid UTF-8, and that turns back into exactly the stored text,
counts as garbled. Ordinary non-ASCII text such as "café" does not round-trip
and is left alone. `doctor` lists each change; only `doctor --repair` writes.
"""

from __future__ import annotations

from typing import Any, Iterable

PREVIEW_CHARS = 120


def repaired_text(text: str) -> str | None:
    """Return the original text, or None when `text` is not an exact round-trip."""
    if text.isascii():
        return None
    try:
        candidate = text.encode("cp1252").decode("utf-8")
        if candidate == text or candidate.encode("utf-8").decode("cp1252") != text:
            return None
    except UnicodeError:
        return None
    return candidate


Change = tuple[str, str, str]  # field path, stored text, repaired text


def _repair_value(value: Any, path: str, changes: list[Change]) -> Any:
    if isinstance(value, str):
        fixed = repaired_text(value)
        if fixed is None:
            return value
        changes.append((path, value, fixed))
        return fixed
    if isinstance(value, list):
        return [_repair_value(item, f"{path}[{index}]", changes) for index, item in enumerate(value)]
    if isinstance(value, dict):
        return {key: _repair_value(item, f"{path}.{key}", changes) for key, item in value.items()}
    return value


def record_repair(content: Any, metadata: Any) -> tuple[str, dict[str, Any], list[Change]] | None:
    """Return repaired content and metadata plus each change, or None."""
    if not isinstance(content, str) or not isinstance(metadata, (dict, type(None))):
        return None  # A malformed JSONL row; doctor reports it and a repair leaves it alone.
    changes: list[Change] = []
    fixed_content = _repair_value(content, "content", changes)
    fixed_metadata = _repair_value(dict(metadata or {}), "metadata", changes)
    if not changes:
        return None
    return fixed_content, fixed_metadata, changes


def _preview(text: str) -> str:
    clean = " ".join(text.split())
    return clean if len(clean) <= PREVIEW_CHARS else clean[: PREVIEW_CHARS - 1] + "…"


def change_report(record_id: int, category: str, changes: list[Change]) -> dict[str, Any]:
    """Describe one record's repair: its changed fields and the first one before and after."""
    _, before, after = changes[0]
    return {
        "id": record_id,
        "category": category,
        "fields": [path for path, _, _ in changes],
        "before": _preview(before),
        "after": _preview(after),
    }


def find_garbled(records: Iterable[Any]) -> list[dict[str, Any]]:
    """Return a change report for every record that holds garbled text."""
    reports = []
    for record in records:
        repair = record_repair(record.content, record.metadata)
        if repair is not None:
            reports.append(change_report(record.id, record.category, repair[2]))
    return reports
