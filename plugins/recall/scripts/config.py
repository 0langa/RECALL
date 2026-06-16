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
        "description": "Architectural choices, library selections, design rationale, and trade-offs.",
        "weight": 1.2,
    },
    "constraints": {
        "description": "Hard rules such as banned patterns, dependency pins, naming conventions, and security rules.",
        "weight": 1.4,
    },
    "debug_history": {
        "description": "Bugs, error patterns, failed attempts, root causes, fixes, and commands that worked.",
        "weight": 1.1,
    },
    "preferences": {
        "description": "User or project preferences, coding style, formatting rules, and workflow expectations.",
        "weight": 1.0,
    },
    "tasks": {
        "description": "Completed work, open TODOs, milestones, and current implementation status.",
        "weight": 1.0,
    },
    "session_summaries": {
        "description": "Compressed summaries of prior sessions to maintain continuity across context resets.",
        "weight": 0.9,
    },
    "project_state": {
        "description": (
            "Current repository status, active branch, pending refactors, known broken areas, "
            "and checkpoints."
        ),
        "weight": 1.3,
    },
    "architecture": {
        "description": "Stable system structure, module responsibilities, data flows, and overall system design.",
        "weight": 1.3,
    },
    "commands": {
        "description": "Verified commands for building, testing, linting, and running the project.",
        "weight": 1.1,
    },
    "lessons_learned": {
        "description": "Reusable insights from prior mistakes or successful fixes that guide future development.",
        "weight": 1.1,
    },
    "requirements": {
        "description": "Explicit user requirements and acceptance criteria that must be met.",
        "weight": 1.5,
    },
    "risks": {
        "description": "Known fragile areas, performance bottlenecks, and security-sensitive code paths.",
        "weight": 1.4,
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
    "embedding_model": "local-hash-v1",
    "summarizer_model": "heuristic-v1",
    "categories": DEFAULT_CATEGORIES,
}

VALID_BACKENDS = {"sqlite", "jsonl"}
VALID_CAPTURE_MODES = {"manual", "minimal", "standard", "off"}
VALID_RECALL_MODES = {"manual", "relevant", "always"}
VALID_OBSERVABILITY_MODES = {"quiet", "debug"}


def project_root(raw_root: str | Path | None = None) -> Path:
    """Return the project root RECALL should use for local storage."""
    if raw_root is not None:
        return Path(raw_root).expanduser().resolve()
    env_root = os.environ.get("RECALL_PROJECT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path.cwd().resolve()


def memory_dir(raw_root: str | Path | None = None) -> Path:
    return project_root(raw_root) / ".codex_memory"


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
    """Create `.codex_memory/memory_config.json` when missing."""
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
    memory_root = memory_dir(root)
    if not memory_root.exists():
        return False
    if config_path(root).exists():
        return True
    if (memory_root / "memory.sqlite").exists():
        return True
    if (memory_root / "vector_index.bin").exists():
        return True
    jsonl_root = memory_root / "jsonl"
    return any(jsonl_root.glob("*.jsonl")) if jsonl_root.exists() else False


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
        merged["categories"][normalized] = {
            "description": description,
            "weight": weight,
        }

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
) -> dict[str, Any]:
    config = load_config(raw_root)
    normalized = normalize_category(name)
    config["categories"][normalized] = {
        "description": description or f"Custom category `{normalized}`.",
        "weight": float(weight),
    }
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
