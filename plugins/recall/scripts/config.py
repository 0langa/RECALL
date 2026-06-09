#!/usr/bin/env python3
"""Configuration management for RECALL project memory."""

from __future__ import annotations

import json
import os
import re
import shutil
from copy import deepcopy
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
    "backend": "sqlite",
    "token_budget": 1200,
    "recency_days": None,
    "embedding_model": "local-hash-v1",
    "summarizer_model": "heuristic-v1",
    "categories": DEFAULT_CATEGORIES,
}

VALID_BACKENDS = {"sqlite", "jsonl"}


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

    root_config = root / "memory_config.json"
    if root_config.exists():
        shutil.copyfile(root_config, target)
    else:
        save_config(default_config(), root)
    return target


def load_config(raw_root: str | Path | None = None) -> dict[str, Any]:
    path = ensure_config(raw_root)
    with path.open(encoding="utf-8") as handle:
        loaded = json.load(handle)
    return validate_config(loaded)


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

    backend = merged.get("backend")
    if backend not in VALID_BACKENDS:
        raise ValueError(f"Unsupported RECALL backend: {backend}")

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

    args = parser.parse_args()
    if args.command == "init":
        print(ensure_config())
    elif args.command == "show":
        print(json.dumps(load_config(args.root), indent=2, sort_keys=True))
    elif args.command == "define-category":
        add_category(args.name, args.description, args.weight, args.root)
        print(json.dumps(load_config(args.root)["categories"][normalize_category(args.name)], indent=2))


if __name__ == "__main__":
    main()
