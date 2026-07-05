"""Scenario schema: scripted turn sequences with behavior labels.

A scenario never encodes expected RECALL *output* (that would be circular);
it encodes the synthetic session (prompts, tool events, stop notes) plus
ground-truth labels the metrics engine grades against, e.g. should_inject.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED_TURN_KEYS = {"prompt"}
ALLOWED_TURN_KEYS = {"prompt", "should_inject", "tools", "stop_text", "precompact"}
ALLOWED_TOOL_KEYS = {"tool_name", "command", "output"}


def load_scenario(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return validate_scenario(payload, source=str(path))


def validate_scenario(payload: dict[str, Any], *, source: str = "<inline>") -> dict[str, Any]:
    for key in ("name", "store", "turns"):
        if key not in payload:
            raise ValueError(f"{source}: scenario missing required key `{key}`")
    store = payload["store"]
    if store.get("tier") not in {"fresh", "working", "mature"}:
        raise ValueError(f"{source}: store.tier must be fresh|working|mature")
    turns = payload["turns"]
    if not isinstance(turns, list) or not turns:
        raise ValueError(f"{source}: turns must be a non-empty list")
    for position, turn in enumerate(turns):
        missing = REQUIRED_TURN_KEYS - set(turn)
        if missing:
            raise ValueError(f"{source}: turn {position} missing {sorted(missing)}")
        unknown = set(turn) - ALLOWED_TURN_KEYS
        if unknown:
            raise ValueError(f"{source}: turn {position} has unknown keys {sorted(unknown)}")
        if "should_inject" in turn and not isinstance(turn["should_inject"], bool):
            raise ValueError(f"{source}: turn {position} should_inject must be boolean")
        for tool in turn.get("tools", []):
            unknown_tool = set(tool) - ALLOWED_TOOL_KEYS
            if unknown_tool:
                raise ValueError(f"{source}: turn {position} tool has unknown keys {sorted(unknown_tool)}")
    return payload


def load_all(directory: Path, names: list[str] | None = None) -> list[dict[str, Any]]:
    scenarios = []
    for path in sorted(directory.glob("*.json")):
        scenario = load_scenario(path)
        if names is None or scenario["name"] in names:
            scenarios.append(scenario)
    if names:
        found = {scenario["name"] for scenario in scenarios}
        missing = set(names) - found
        if missing:
            raise ValueError(f"Unknown scenario names requested: {sorted(missing)}")
    return scenarios
