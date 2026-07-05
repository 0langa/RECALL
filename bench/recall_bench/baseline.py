"""Baseline storage and delta comparison with thresholds."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_THRESHOLDS = {
    # relative growth limits (fraction) before a delta becomes a violation
    "fixed_overhead_per_session_est_tokens": 0.15,
    "marginal_per_turn_est_tokens": 0.20,
    "projected_session_est_tokens_20_turns": 0.15,
    # absolute floors for quality (current must not drop below baseline - slack)
    "retrieval_hit_rate_slack": 0.05,
    "injection_accuracy_slack": 0.05,
    "flag_correct_rate_slack": 0.0,
}


def save(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def compare(current: dict[str, Any], baseline: dict[str, Any], thresholds: dict[str, float] | None = None) -> dict[str, Any]:
    limits = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    violations: list[str] = []
    deltas: dict[str, Any] = {}

    for key in ("fixed_overhead_per_session_est_tokens", "marginal_per_turn_est_tokens", "projected_session_est_tokens_20_turns"):
        old = baseline.get("metrics", {}).get("tokens", {}).get(key)
        new = current.get("metrics", {}).get("tokens", {}).get(key)
        if old is None or new is None or old == 0:
            continue
        change = (new - old) / old
        deltas[key] = {"baseline": old, "current": new, "change_pct": round(change * 100, 1)}
        if change > limits[key]:
            violations.append(f"{key} grew {change:+.1%} (limit +{limits[key]:.0%})")

    pairs = [
        ("retrieval_hit_rate", ("quality", "retrieval", "hit_rate_at_limit"), "retrieval_hit_rate_slack"),
        ("injection_accuracy", ("injection_gate", "accuracy"), "injection_accuracy_slack"),
        ("flag_correct_rate", ("quality", "flag_correctness", "correct_rate"), "flag_correct_rate_slack"),
    ]
    for name, path_keys, slack_key in pairs:
        old = _dig(baseline.get("metrics", {}), path_keys)
        new = _dig(current.get("metrics", {}), path_keys)
        if old is None or new is None:
            continue
        deltas[name] = {"baseline": old, "current": new}
        if new < old - limits[slack_key]:
            violations.append(f"{name} dropped {old} -> {new} (slack {limits[slack_key]})")

    leaks = _dig(current.get("metrics", {}), ("secret_leaks", "leaks_found"))
    if leaks:
        violations.append(f"secret leak sweep found {leaks} leak(s) in emissions")

    return {"deltas": deltas, "violations": violations, "pass": not violations}


def _dig(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    node: Any = payload
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node
