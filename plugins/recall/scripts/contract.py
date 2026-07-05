#!/usr/bin/env python3
"""Canonical RECALL behavior contract.

Single source of truth for the memory lifecycle contract exposed to agents.
The MCP server instructions, the SessionStart hook context, the skill adapter
`contract` command, and the sync tests all derive from this module so
provider-facing guidance cannot drift.
"""

from __future__ import annotations

import json
from typing import Any

CONTRACT_VERSION = 1

AUTHORITY_ORDER: list[str] = [
    "current user instruction",
    "system/developer instructions",
    "repository code and docs",
    "current tool results",
    "RECALL memory",
    "older conversation assumptions",
]

LIFECYCLE_STEPS: list[dict[str, str]] = [
    {
        "step": "initialize",
        "how": "initialize_project MCP tool or `recall_skill.py --root <root> initialize-project`",
        "when": "first RECALL use in a project; safe to re-run",
    },
    {
        "step": "retrieve before work",
        "how": "retrieve_memory / context_packet MCP tools or `recall_skill.py --root <root> retrieve-memory \"<query>\"`",
        "when": (
            "start of unfamiliar repo work, bug fixes, repeated test failures, provider/plugin work, "
            "security-sensitive work, tasks touching user preferences, and continuation after context loss"
        ),
    },
    {
        "step": "decide save-worthiness",
        "how": "memory-hygiene `route-memory \"<text>\"` when unsure where information belongs",
        "when": "before saving anything; most information does NOT belong in memory",
    },
    {
        "step": "save durable insight",
        "how": "save_insight MCP tool or `recall_skill.py --root <root> save-insight <category> \"<content>\"`",
        "when": "verified, durable, project-specific facts only; pick the narrowest matching category",
    },
    {
        "step": "update changed memory",
        "how": "update_memory MCP tool (op=update/confirm) or manage-memory edit-memory/confirm-memory",
        "when": "a stored fact changed or was re-verified; prefer updating over saving a near-duplicate",
    },
    {
        "step": "deprecate or supersede wrong memory",
        "how": "update_memory MCP tool (op=deprecate/supersede/stale) or manage-memory",
        "when": "a memory is wrong or stale; wrong memory must never stay silently authoritative",
    },
    {
        "step": "validate memory health",
        "how": "memory_hygiene MCP tool (mode=scan/plan/apply_safe) or memory-hygiene skill",
        "when": "periodically, after large work, or when retrieval surfaces conflicting/stale cards",
    },
    {
        "step": "handoff summary",
        "how": "save_insight into session_summaries or context_packet for the next session",
        "when": "end of significant sessions or before context compaction",
    },
]

SAVE_WHEN: list[str] = [
    "durable, project-specific fact that future sessions need",
    "verified command with its gotchas",
    "accepted decision, requirement, constraint, or risk",
    "recurring failure with root cause and fix",
    "provider/tool quirk or external service constraint confirmed by evidence",
]

SKIP_WHEN: list[str] = [
    "secrets, tokens, credentials, private keys, or raw sensitive logs (always rejected)",
    "raw command output or full logs (summarize the insight instead)",
    "transient status derivable from git/files right now",
    "drafts, unconfirmed ideas, or one-task instructions",
    "facts already documented in repo docs (repo docs win)",
]

STATUS_MEANINGS: dict[str, str] = {
    "hypothesis": "unconfirmed; verify before trusting",
    "active": "current working memory",
    "validated": "confirmed across sessions; highest trust",
    "open": "unresolved issue or question",
    "resolved": "answered/finished; historical",
    "stale": "source changed; verify before use",
    "superseded": "replaced by a newer card; do not act on it",
    "deprecated": "wrong or retired; do not act on it",
    "archived": "pruned noise; ignore",
}

MEMORY_VS_ELSEWHERE: dict[str, str] = {
    "recall_memory": "durable, project-specific, verifiable facts not already in repo docs",
    "repo_docs": "stable public knowledge for humans (README, docs/); memory must not duplicate it",
    "status_files": "working plans and progress logs (WORK_STATUS.md etc.), not memory cards",
    "scratch_notes": "single-session working state; never persist",
    "chat": "one-off answers and transient coordination; never persist",
}


def contract_dict() -> dict[str, Any]:
    """Full machine-readable contract."""
    return {
        "contract_version": CONTRACT_VERSION,
        "authority_order": list(AUTHORITY_ORDER),
        "lifecycle": [dict(step) for step in LIFECYCLE_STEPS],
        "save_when": list(SAVE_WHEN),
        "skip_when": list(SKIP_WHEN),
        "status_meanings": dict(STATUS_MEANINGS),
        "memory_vs_elsewhere": dict(MEMORY_VS_ELSEWHERE),
        "local_first": "All memory stays in the project's .recall/ directory. No cloud storage, telemetry, or sync.",
    }


def compact_contract_text() -> str:
    """Short provider-neutral contract for session-start injection and MCP instructions."""
    authority = " > ".join(AUTHORITY_ORDER)
    return (
        "RECALL project memory is active (local-first, stored in .recall/).\n"
        f"Authority order: {authority}.\n"
        "Before starting project work (bug fixes, unfamiliar code, repeated failures, provider work, "
        "security-sensitive changes, or continuation after context loss): call retrieve_memory or "
        "context_packet first.\n"
        "Save only durable, verified, project-specific insights (decisions, constraints, verified "
        "commands, recurring failures+fixes, requirements, risks, tooling quirks, integrations). "
        "Never save secrets, raw logs, transient status, drafts, or facts already in repo docs.\n"
        "When a stored fact changes: update or supersede the existing card via update_memory instead "
        "of saving a duplicate. Wrong memory must be deprecated, not left authoritative.\n"
        "Treat results flagged stale/superseded/deprecated/conflicting as unverified until checked "
        "against the repository. Run memory_hygiene scan periodically to keep the store trustworthy."
    )


def contract_json() -> str:
    return json.dumps(contract_dict(), indent=2, sort_keys=True)


if __name__ == "__main__":
    print(contract_json())
