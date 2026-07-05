#!/usr/bin/env python3
"""Configuration management for RECALL project memory."""

from __future__ import annotations

import json
import os
import re
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CATEGORIES: dict[str, dict[str, Any]] = {
    "decisions": {
        "description": "Accepted architectural choices, library selections, design rationale, and trade-offs.",
        "weight": 1.2,
        "examples": [
            "Chose SQLite over JSONL as default backend because WAL supports concurrent hooks.",
            "Rejected background daemon design; hooks must stay stateless.",
        ],
        "non_examples": [
            "A design idea still under discussion (save as risks/open instead).",
            "A decision fully documented in an ADR file (repo docs win).",
        ],
        "update_rule": "When a decision is reversed, supersede the old card with the new decision; never edit history in place.",
    },
    "constraints": {
        "description": "Hard rules: banned patterns, dependency pins, naming conventions, security/privacy rules, external service limits.",
        "weight": 1.4,
        "examples": [
            "Never store secrets or tokens in memory or fixtures.",
            "Provider API rate limit: max 2 requests/second against the staging service.",
        ],
        "non_examples": [
            "Style preferences (use preferences).",
            "Temporary workarounds (use debug_history or risks).",
        ],
        "update_rule": "Constraints rarely expire; when one is lifted, deprecate the card and state what replaced it.",
    },
    "debug_history": {
        "description": "Recurring failures and fixes: bugs, error patterns, root causes, failed attempts, working repairs.",
        "weight": 1.1,
        "examples": [
            "pytest hangs on Windows when run without --exclude-smoke; use run_tests.py wrapper.",
            "Build fails with 'Duplicate hooks file detected' if hooks are declared in the Claude manifest.",
        ],
        "non_examples": [
            "One-off typo fixes with no future value.",
            "Raw stack traces or full logs (summarize root cause + fix instead).",
        ],
        "update_rule": "If a documented failure no longer reproduces after a fix, mark the card resolved.",
    },
    "preferences": {
        "description": "Durable user or project preferences: coding style, formatting, workflow expectations.",
        "weight": 1.0,
        "examples": [
            "User wants commit messages in imperative mood without emoji.",
            "Project prefers pathlib over os.path in new code.",
        ],
        "non_examples": [
            "A one-task instruction ('for this PR, skip tests').",
            "Drafts or unconfirmed style ideas.",
        ],
        "update_rule": "Preferences need evidence (accepted/rejected decision); update the existing card when a preference changes.",
    },
    "tasks": {
        "description": "Open TODOs, milestones, deferred ideas, and current implementation status.",
        "weight": 1.0,
        "examples": [
            "Deferred: semantic repo-doc duplication check in hygiene (heuristic only today).",
            "Milestone: v1.2 requires manifest parity test in CI.",
        ],
        "non_examples": [
            "Fine-grained scratch checklists for the current turn.",
            "Completed work already visible in git history.",
        ],
        "update_rule": "Close or archive tasks when done; stale open tasks should be re-confirmed or pruned.",
    },
    "session_summaries": {
        "description": "Compressed summaries of prior sessions to maintain continuity across context resets.",
        "weight": 0.9,
        "examples": [
            "2026-07-05 session: implemented retrieval health flags and hygiene secret scan; tests green.",
        ],
        "non_examples": [
            "Full transcripts or chat logs.",
            "Generic checkpoints like 'session done'.",
        ],
        "update_rule": "Old summaries lose value fast; hygiene may archive summaries older than the retention window.",
    },
    "project_state": {
        "description": (
            "Current repository status, active branch, pending refactors, known broken areas, "
            "and checkpoints. Point-in-time snapshots that age quickly."
        ),
        "weight": 1.3,
        "examples": [
            "Release 1.1.1 shipped; main is clean; marketplace consumes RECALL as submodule.",
        ],
        "non_examples": [
            "Stable architecture facts (use architecture).",
            "Anything derivable from `git status` right now.",
        ],
        "update_rule": "Snapshots supersede prior snapshots on the same claim; hygiene flags snapshots older than the staleness window for review.",
    },
    "architecture": {
        "description": "Stable system structure, module responsibilities, data flows, and overall system design.",
        "weight": 1.3,
        "examples": [
            "One MCP server (kimi_mcp_server.py) serves both Claude Code and Kimi; provider comes from RECALL_DEFAULT_PROVIDER.",
        ],
        "non_examples": [
            "Current branch or WIP refactors (use project_state).",
            "Structure fully documented in README (repo docs win).",
        ],
        "update_rule": "When structure changes, update or supersede the existing card; conflicting architecture cards must be reconciled.",
    },
    "commands": {
        "description": "Verified commands for building, testing, linting, and running the project, with their gotchas.",
        "weight": 1.1,
        "examples": [
            "Unit tests: cd plugins/recall && python -m pytest tests/ -x -q (~2.5 min).",
            "recall_skill.py requires --root BEFORE the subcommand.",
        ],
        "non_examples": [
            "Every command that was ever run (only verified, reusable ones).",
            "Command output dumps.",
        ],
        "update_rule": "If a stored command fails, mark the card stale and save the corrected command as its replacement.",
    },
    "lessons_learned": {
        "description": "Reusable insights from prior mistakes or successful fixes that guide future development.",
        "weight": 1.1,
        "examples": [
            "Editing generated provider files directly causes drift; always change the source of truth and regenerate.",
        ],
        "non_examples": [
            "Restating documentation.",
            "Vague morals without an actionable rule.",
        ],
        "update_rule": "Merge overlapping lessons into one strong card instead of accumulating variants.",
    },
    "requirements": {
        "description": "Explicit user requirements and acceptance criteria that must be met.",
        "weight": 1.5,
        "examples": [
            "RECALL must stay local-first: no cloud storage, telemetry, or hosted sync.",
        ],
        "non_examples": [
            "Implementation ideas (use decisions or tasks).",
            "Requirements copied verbatim from a spec file in the repo.",
        ],
        "update_rule": "Requirements change only on explicit user instruction; supersede, do not silently edit.",
    },
    "risks": {
        "description": "Known fragile areas, performance bottlenecks, security-sensitive paths, and open risks.",
        "weight": 1.4,
        "examples": [
            "Hook payload drift against live Codex payloads is an open compatibility risk.",
        ],
        "non_examples": [
            "Resolved incidents (move to debug_history or lessons_learned).",
        ],
        "update_rule": "Re-confirm risks periodically; resolve or supersede when mitigated.",
    },
    "tooling_quirks": {
        "description": "Provider- and tool-specific quirks: agent client behavior, plugin loading rules, CLI flag surprises.",
        "weight": 1.1,
        "examples": [
            "Claude Code auto-loads hooks/hooks.json by convention; declaring it in the manifest breaks plugin load.",
            "Kimi manifest supports startupTimeoutMs; Claude Code rejects unknown manifest fields.",
        ],
        "non_examples": [
            "General project commands (use commands).",
            "Quirks already documented in provider docs bundled with the repo.",
        ],
        "update_rule": "Stamp applies_to_provider; re-verify after provider version upgrades and mark stale when behavior changes.",
    },
    "integrations": {
        "description": "External service constraints and facts: APIs, marketplaces, submodules, CI services this project depends on.",
        "weight": 1.2,
        "examples": [
            "Downstream marketplace consumes RECALL as a git submodule; version pins live in plugins.json and marketplace.json.",
        ],
        "non_examples": [
            "Secrets, tokens, or connection strings (never store).",
            "Internal module wiring (use architecture).",
        ],
        "update_rule": "External services change without notice; treat cards older than the staleness window as needing verification.",
    },
}

DEFAULT_CONFIG: dict[str, Any] = {
    "config_schema_version": 2,
    "backend": "sqlite",
    "activation": {
        "enabled": False,
        "project_root": None,
        "activated_at": None,
        "activated_by": None,
    },
    "capture_mode": "standard",
    "recall_mode": "relevant",
    "observability_mode": "quiet",
    "debug_retention_days": 7,
    "relevance": {
        "minimum_score": 0.75,
        "minimum_lexical_overlap": 0.15,
    },
    "token_budget": 1200,
    "recency_days": None,
    "staleness": {
        "snapshot_stale_days": 45,
        "retrieval_aging_days": 30,
    },
    "embedding_model": "local-hash-v1",
    "summarizer_model": "heuristic-v1",
    "categories": DEFAULT_CATEGORIES,
}

VALID_BACKENDS = {"sqlite", "jsonl"}
VALID_CAPTURE_MODES = {"manual", "minimal", "standard", "off"}
VALID_RECALL_MODES = {"manual", "relevant", "always"}
VALID_OBSERVABILITY_MODES = {"quiet", "debug"}
MEMORY_DIR_NAME = ".recall"
LEGACY_MEMORY_DIR_NAME = ".codex_memory"


def project_root(raw_root: str | Path | None = None) -> Path:
    """Return the project root RECALL should use for local storage."""
    if raw_root is not None:
        return Path(raw_root).expanduser().resolve()
    env_root = os.environ.get("RECALL_PROJECT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path.cwd().resolve()


def neutral_memory_dir(raw_root: str | Path | None = None) -> Path:
    return project_root(raw_root) / MEMORY_DIR_NAME


def legacy_memory_dir(raw_root: str | Path | None = None) -> Path:
    return project_root(raw_root) / LEGACY_MEMORY_DIR_NAME


def memory_dir(raw_root: str | Path | None = None) -> Path:
    """Return the active project memory directory.

    New projects use provider-neutral `.recall/`. Existing `.codex_memory/`
    stores remain authoritative until the user migrates them, so Codex users do
    not lose or silently fork memory.
    """

    root = project_root(raw_root)
    neutral = neutral_memory_dir(root)
    legacy = legacy_memory_dir(root)
    if neutral.exists():
        return neutral
    if legacy.exists():
        return legacy
    return neutral


def config_path(raw_root: str | Path | None = None) -> Path:
    return memory_dir(raw_root) / "memory_config.json"


def root_config_path(raw_root: str | Path | None = None) -> Path:
    return project_root(raw_root) / "memory_config.json"


def normalize_category(name: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower()).strip("_")
    if not normalized:
        raise ValueError("Category must contain at least one letter or digit.")
    return normalized


def default_config() -> dict[str, Any]:
    return deepcopy(DEFAULT_CONFIG)


def ensure_config(raw_root: str | Path | None = None) -> Path:
    """Create the project-local memory config when missing."""
    root = project_root(raw_root)
    target_dir = memory_dir(root)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = config_path(root)
    if target.exists():
        return target

    root_config = root_config_path(root)
    if root_config.exists():
        shutil.copyfile(root_config, target)
    else:
        save_config(default_config(), root)
    return target


def load_config_if_present(raw_root: str | Path | None = None) -> dict[str, Any]:
    runtime_path = config_path(raw_root)
    source_path = runtime_path if runtime_path.exists() else root_config_path(raw_root)
    if source_path.exists():
        with source_path.open(encoding="utf-8") as handle:
            loaded = json.load(handle)
        validated = validate_config(loaded)
        if "activation" not in loaded and memory_dir(raw_root).exists():
            validated["activation"].update(
                {
                    "enabled": True,
                    "project_root": str(project_root(raw_root)),
                    "activated_by": "legacy_memory_store",
                }
            )
        return validated
    return validate_config(default_config())


def persistent_memory_exists(raw_root: str | Path | None = None) -> bool:
    root = project_root(raw_root)
    for memory_root in (neutral_memory_dir(root), legacy_memory_dir(root)):
        if not memory_root.exists():
            continue
        if (memory_root / "memory_config.json").exists():
            return True
        if (memory_root / "memory.sqlite").exists():
            return True
        if (memory_root / "vector_index.bin").exists():
            return True
        jsonl_root = memory_root / "jsonl"
        if jsonl_root.exists() and any(jsonl_root.glob("*.jsonl")):
            return True
    return False


def load_config(raw_root: str | Path | None = None) -> dict[str, Any]:
    path = ensure_config(raw_root)
    with path.open(encoding="utf-8") as handle:
        loaded = json.load(handle)
    validated = validate_config(loaded)
    if "activation" not in loaded:
        validated["activation"].update(
            {
                "enabled": True,
                "project_root": str(project_root(raw_root)),
                "activated_by": "legacy_memory_store",
            }
        )
        save_config(validated, raw_root)
    return validated


def save_config(config: dict[str, Any], raw_root: str | Path | None = None) -> None:
    root = project_root(raw_root)
    target_dir = memory_dir(root)
    target_dir.mkdir(parents=True, exist_ok=True)
    validated = validate_config(config)
    with config_path(root).open("w", encoding="utf-8") as handle:
        json.dump(validated, handle, indent=2, sort_keys=True)
        handle.write("\n")


def validate_config(config: dict[str, Any]) -> dict[str, Any]:
    merged = default_config()
    merged.update({key: value for key, value in config.items() if key != "categories"})
    categories = deepcopy(DEFAULT_CATEGORIES)
    categories.update(config.get("categories", {}))
    merged["categories"] = {}

    merged["config_schema_version"] = 2
    activation = merged.get("activation")
    if not isinstance(activation, dict):
        activation = {}
    default_activation = deepcopy(DEFAULT_CONFIG["activation"])
    default_activation.update(activation)
    default_activation["enabled"] = bool(default_activation.get("enabled"))
    merged["activation"] = default_activation

    backend = merged.get("backend")
    if backend not in VALID_BACKENDS:
        raise ValueError(f"Unsupported RECALL backend: {backend}")

    capture_mode = str(merged.get("capture_mode", "standard")).strip().lower()
    if capture_mode not in VALID_CAPTURE_MODES:
        raise ValueError(f"Unsupported RECALL capture_mode: {capture_mode}")
    merged["capture_mode"] = capture_mode

    recall_mode = str(merged.get("recall_mode", "relevant")).strip().lower()
    if recall_mode not in VALID_RECALL_MODES:
        raise ValueError(f"Unsupported RECALL recall_mode: {recall_mode}")
    merged["recall_mode"] = recall_mode

    observability_mode = str(merged.get("observability_mode", "quiet")).strip().lower()
    if observability_mode not in VALID_OBSERVABILITY_MODES:
        raise ValueError(f"Unsupported RECALL observability_mode: {observability_mode}")
    merged["observability_mode"] = observability_mode
    merged["debug_retention_days"] = max(1, int(merged.get("debug_retention_days", 7)))
    relevance = merged.get("relevance") if isinstance(merged.get("relevance"), dict) else {}
    merged["relevance"] = {
        "minimum_score": float(relevance.get("minimum_score", 0.75)),
        "minimum_lexical_overlap": float(relevance.get("minimum_lexical_overlap", 0.15)),
    }
    staleness = merged.get("staleness") if isinstance(merged.get("staleness"), dict) else {}
    merged["staleness"] = {}
    for key, default in (("snapshot_stale_days", 45.0), ("retrieval_aging_days", 30.0)):
        try:
            value = float(staleness.get(key, default))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"staleness.{key} must be numeric.") from exc
        if value <= 0:
            raise ValueError(f"staleness.{key} must be positive.")
        merged["staleness"][key] = value

    for name, details in categories.items():
        normalized = normalize_category(name)
        if not isinstance(details, dict):
            details = {"description": str(details), "weight": 1.0}
        description = str(details.get("description") or f"Custom category `{normalized}`.")
        try:
            weight = float(details.get("weight", 1.0))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Category `{normalized}` weight must be numeric.") from exc
        if weight <= 0:
            raise ValueError(f"Category `{normalized}` weight must be greater than zero.")
        validated_category: dict[str, Any] = {
            "description": description,
            "weight": weight,
        }
        for guidance_key in ("examples", "non_examples"):
            values = details.get(guidance_key)
            if isinstance(values, list):
                cleaned = [str(item) for item in values if str(item).strip()]
                if cleaned:
                    validated_category[guidance_key] = cleaned
        update_rule = details.get("update_rule")
        if isinstance(update_rule, str) and update_rule.strip():
            validated_category["update_rule"] = update_rule.strip()
        default_details = DEFAULT_CATEGORIES.get(normalized, {})
        for guidance_key in ("examples", "non_examples", "update_rule"):
            if guidance_key not in validated_category and guidance_key in default_details:
                validated_category[guidance_key] = deepcopy(default_details[guidance_key])
        merged["categories"][normalized] = validated_category

    token_budget = int(merged.get("token_budget", 1200))
    if token_budget < 100:
        raise ValueError("token_budget must be at least 100.")
    merged["token_budget"] = token_budget

    recency_days = merged.get("recency_days")
    if recency_days is not None:
        recency_days = int(recency_days)
        if recency_days <= 0:
            raise ValueError("recency_days must be positive when set.")
    merged["recency_days"] = recency_days
    return merged


def add_category(
    name: str,
    description: str | None = None,
    weight: float = 1.0,
    raw_root: str | Path | None = None,
    *,
    examples: list[str] | None = None,
    non_examples: list[str] | None = None,
    update_rule: str | None = None,
) -> dict[str, Any]:
    config = load_config(raw_root)
    normalized = normalize_category(name)
    existing = dict(config["categories"].get(normalized, {}))
    existing["description"] = description or existing.get("description") or f"Custom category `{normalized}`."
    existing["weight"] = float(weight)
    if examples:
        existing["examples"] = [str(item) for item in examples if str(item).strip()]
    if non_examples:
        existing["non_examples"] = [str(item) for item in non_examples if str(item).strip()]
    if update_rule and update_rule.strip():
        existing["update_rule"] = update_rule.strip()
    config["categories"][normalized] = existing
    save_config(config, raw_root)
    return config["categories"][normalized]


def category_weight(config: dict[str, Any], category: str) -> float:
    normalized = normalize_category(category)
    details = config.get("categories", {}).get(normalized, {})
    return float(details.get("weight", 1.0))


def set_capture_mode(mode: str, raw_root: str | Path | None = None) -> dict[str, Any]:
    config = load_config(raw_root)
    config["capture_mode"] = mode
    save_config(config, raw_root)
    return config


def set_recall_mode(mode: str, raw_root: str | Path | None = None) -> dict[str, Any]:
    config = load_config(raw_root)
    config["recall_mode"] = mode
    save_config(config, raw_root)
    return config


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def activate_project(
    raw_root: str | Path,
    *,
    activated_by: str = "explicit_recall",
) -> dict[str, Any]:
    root = project_root(raw_root)
    config = load_config(root)
    config["activation"] = {
        "enabled": True,
        "project_root": str(root),
        "activated_at": utc_now(),
        "activated_by": activated_by,
    }
    config.setdefault("capture_mode", "standard")
    config.setdefault("recall_mode", "relevant")
    config.setdefault("observability_mode", "quiet")
    save_config(config, root)
    return config


GITIGNORE_ENTRIES = (".recall/", ".codex_memory/")


def ensure_gitignore_entries(raw_root: str | Path | None = None) -> dict[str, Any]:
    """Ensure local-only memory directories are ignored by git.

    Appends missing entries to the project `.gitignore` (creating it when the
    project is a git repository). Never rewrites existing content.
    """

    root = project_root(raw_root)
    gitignore = root / ".gitignore"
    if not gitignore.exists() and not (root / ".git").exists():
        return {"path": str(gitignore), "added": [], "present": [], "skipped": "not a git repository"}
    existing_lines: list[str] = []
    if gitignore.exists():
        existing_lines = gitignore.read_text(encoding="utf-8", errors="replace").splitlines()
    normalized = {line.strip().rstrip("/") for line in existing_lines if line.strip() and not line.strip().startswith("#")}
    added: list[str] = []
    present: list[str] = []
    for entry in GITIGNORE_ENTRIES:
        if entry.rstrip("/") in normalized:
            present.append(entry)
        else:
            added.append(entry)
    if added:
        joined = "\n".join(added)
        prefix = ""
        if existing_lines and existing_lines[-1].strip():
            prefix = "\n"
        with gitignore.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"{prefix}{joined}\n")
    return {"path": str(gitignore), "added": added, "present": present}


def deactivate_project(raw_root: str | Path) -> dict[str, Any]:
    root = project_root(raw_root)
    config = load_config(root)
    activation = dict(config.get("activation") or {})
    activation["enabled"] = False
    activation["deactivated_at"] = utc_now()
    config["activation"] = activation
    save_config(config, root)
    return config


def project_is_active(raw_root: str | Path | None) -> bool:
    if raw_root is None or not persistent_memory_exists(raw_root):
        return False
    config = load_config_if_present(raw_root)
    activation = config.get("activation")
    if isinstance(activation, dict) and "enabled" in activation:
        return bool(activation.get("enabled"))
    return True


def set_observability_mode(mode: str, raw_root: str | Path | None = None) -> dict[str, Any]:
    config = load_config(raw_root)
    config["observability_mode"] = mode
    save_config(config, raw_root)
    return config


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Manage RECALL memory configuration.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init")

    show = subparsers.add_parser("show")
    show.add_argument("--root")

    define = subparsers.add_parser("define-category")
    define.add_argument("name")
    define.add_argument("--description")
    define.add_argument("--weight", type=float, default=1.0)
    define.add_argument("--root")

    capture = subparsers.add_parser("set-capture-mode")
    capture.add_argument("mode", choices=sorted(VALID_CAPTURE_MODES))
    capture.add_argument("--root")

    args = parser.parse_args()
    if args.command == "init":
        print(ensure_config())
    elif args.command == "show":
        print(json.dumps(load_config(args.root), indent=2, sort_keys=True))
    elif args.command == "define-category":
        add_category(args.name, args.description, args.weight, args.root)
        print(json.dumps(load_config(args.root)["categories"][normalize_category(args.name)], indent=2))
    elif args.command == "set-capture-mode":
        print(json.dumps(set_capture_mode(args.mode, args.root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
