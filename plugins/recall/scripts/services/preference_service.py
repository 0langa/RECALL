"""Evidence policy for durable user and project preferences."""

from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple

import storage


DURABLE_DECISIONS = {"approved_plan", "rejected_plan", "accepted_edit", "rejected_edit", "adjusted_edit", "undone_edit"}
NON_DURABLE = {"draft", "correction", "one_task_constraint", "model_output"}


class PreferenceDecision(NamedTuple):
    action: str
    reason: str
    metadata: dict[str, Any]
    record: storage.MemoryRecord | None = None


def evaluate(
    category: str,
    metadata: dict[str, Any],
    root: str | Path | None = None,
) -> PreferenceDecision:
    """Apply durable preference evidence rules before persistence."""

    if category != "preferences":
        return PreferenceDecision("save", "not_preference", metadata)
    evidence_type = str(metadata.get("preference_evidence_type") or "").strip().lower()
    key = str(metadata.get("preference_key") or "").strip().lower()
    if evidence_type in NON_DURABLE or not evidence_type:
        return PreferenceDecision("ignore", "non_durable_preference_evidence", metadata)
    updated = dict(metadata)
    updated["preference_scope"] = str(updated.get("preference_scope") or "project")
    if evidence_type == "explicit_declaration":
        updated.update({"status": "active", "trust": max(0.9, float(updated.get("trust", 0.0)))})
        return PreferenceDecision("save", "explicit_preference", updated)
    if evidence_type not in DURABLE_DECISIONS or not key or not metadata.get("decision_id"):
        return PreferenceDecision("ignore", "insufficient_preference_evidence", metadata)

    decision_id = str(metadata["decision_id"])
    for record in storage.iter_records(root):
        existing = record.metadata or {}
        if record.category != "preferences" or str(existing.get("preference_key", "")).lower() != key:
            continue
        evidence_ids = [str(value) for value in existing.get("supporting_event_ids", [])]
        existing_decision = existing.get("decision_id")
        if existing_decision:
            evidence_ids.append(str(existing_decision))
        if decision_id not in evidence_ids:
            evidence_ids.append(decision_id)
        merged = dict(existing)
        merged["supporting_event_ids"] = sorted(set(evidence_ids))
        if len(set(evidence_ids)) >= 2:
            merged.update({"status": "active", "trust": max(0.75, float(merged.get("trust", 0.0)))})
        return PreferenceDecision(
            "update",
            "preference_evidence_accumulated",
            merged,
            storage.update_record_metadata(record.id, merged, root),
        )
    updated.update({"status": "hypothesis", "trust": min(0.49, float(updated.get("trust", 0.4)))})
    return PreferenceDecision("save", "preference_hypothesis", updated)
