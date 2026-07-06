"""Aggregate a run journal into the benchmark report structure."""

from __future__ import annotations

import statistics
from typing import Any

from . import tokens
from .store_fabricator import SECRET_MARKER


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return round(ordered[index], 2)


def compute(journal: list[dict[str, Any]], *, price_per_million: float | None = None) -> dict[str, Any]:
    emissions = [entry for entry in journal if entry.get("kind") == "emission"]
    latencies = [entry for entry in journal if entry.get("kind") == "latency"]
    probes = [entry for entry in journal if entry.get("kind") == "probe"]
    decisions = [entry for entry in journal if entry.get("kind") == "injection_decision"]
    snapshots = [entry for entry in journal if entry.get("kind") == "store_snapshot"]

    report: dict[str, Any] = {
        "tokens": _token_metrics(emissions, price_per_million),
        "injection_gate": _injection_metrics(decisions),
        "quality": _probe_metrics(probes),
        "latency": _latency_metrics(latencies),
        "store_growth": _growth_metrics(snapshots),
        "secret_leaks": _leak_sweep(emissions),
    }
    return report


def _token_metrics(emissions: list[dict[str, Any]], price_per_million: float | None) -> dict[str, Any]:
    per_channel: dict[str, dict[str, Any]] = {}
    fixed_total = 0
    marginal_total = 0
    sessions = {(entry["scenario"], entry["session"]) for entry in emissions if entry["scenario"] != "static"}
    turn_count = len({
        (entry["scenario"], entry["session"], entry["turn"])
        for entry in emissions
        if entry.get("turn") is not None
    })
    conditional_static_total = 0
    for entry in emissions:
        channel = entry["channel"]
        bucket = per_channel.setdefault(channel, {"count": 0, "est_tokens": 0, "chars": 0, "fixed": entry["fixed"]})
        bucket["count"] += 1
        bucket["est_tokens"] += entry["est_tokens"]
        bucket["chars"] += entry["chars"]
        if entry["fixed"]:
            fixed_total += entry["est_tokens"]
        elif entry["session"] == 0:
            # session 0 = static file measurements and probe-phase tool calls:
            # informational sizes, not per-turn scenario behavior.
            conditional_static_total += entry["est_tokens"]
        else:
            marginal_total += entry["est_tokens"]

    marginal_per_turn = round(marginal_total / max(1, turn_count), 1)
    # Fixed floor = what ONE session pays: mean per emission for each fixed
    # channel (session_start_context is recorded once per simulated session,
    # handshake surfaces once per run). Conditional skill bodies stay out.
    fixed_floor = round(sum(
        bucket["est_tokens"] / bucket["count"]
        for channel, bucket in per_channel.items()
        if bucket["fixed"] and bucket["count"]
    ))
    summary = {
        "per_channel": {name: dict(bucket) for name, bucket in sorted(per_channel.items())},
        "fixed_overhead_per_session_est_tokens": fixed_floor,
        "conditional_static_est_tokens": conditional_static_total,
        "marginal_total_est_tokens": marginal_total,
        "marginal_per_turn_est_tokens": marginal_per_turn,
        "sessions_measured": len(sessions),
        "turns_measured": turn_count,
        "projected_session_est_tokens_20_turns": fixed_floor + round(marginal_per_turn * 20),
    }
    if price_per_million is not None:
        summary["projected_session_cost_usd_20_turns"] = tokens.dollars(
            summary["projected_session_est_tokens_20_turns"], price_per_million,
        )
        summary["price_per_million_used"] = price_per_million
    return summary


def _injection_metrics(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    matrix = {"true_inject": 0, "false_inject": 0, "true_suppress": 0, "false_suppress": 0}
    for decision in decisions:
        expected, actual = decision["should_inject"], decision["injected"]
        if expected and actual:
            matrix["true_inject"] += 1
        elif expected and not actual:
            matrix["false_suppress"] += 1
        elif not expected and actual:
            matrix["false_inject"] += 1
        else:
            matrix["true_suppress"] += 1
    labeled = sum(matrix.values())
    return {
        **matrix,
        "labeled_turns": labeled,
        "accuracy": round((matrix["true_inject"] + matrix["true_suppress"]) / labeled, 4) if labeled else None,
    }


def _probe_metrics(probes: list[dict[str, Any]]) -> dict[str, Any]:
    def of(kind: str) -> list[dict[str, Any]]:
        return [probe for probe in probes if probe["probe"] == kind]

    golden = of("golden_retrieval")
    paraphrase = of("paraphrase_retrieval")
    flags = of("flag_correctness")
    quality: dict[str, Any] = {}
    if golden:
        hits = [probe for probe in golden if probe["hit"]]
        ranks = [probe["rank"] for probe in hits]
        quality["retrieval"] = {
            "queries": len(golden),
            "hit_rate_at_limit": round(len(hits) / len(golden), 4),
            "mean_rank": round(statistics.mean(ranks), 2) if ranks else None,
            "mrr": round(statistics.mean(1 / rank for rank in ranks), 4) if ranks else 0.0,
            "misses": [probe["query"] for probe in golden if not probe["hit"]],
        }
    if paraphrase:
        # Deliberately separate from `retrieval`: this is the honest
        # semantic-matching headroom metric, not gated against the lexical
        # baseline in baseline.py (see bench/README.md paraphrase section).
        hits = [probe for probe in paraphrase if probe["hit"]]
        ranks = [probe["rank"] for probe in hits]
        quality["paraphrase_retrieval"] = {
            "queries": len(paraphrase),
            "hit_rate_at_limit": round(len(hits) / len(paraphrase), 4),
            "mean_rank": round(statistics.mean(ranks), 2) if ranks else None,
            "mrr": round(statistics.mean(1 / rank for rank in ranks), 4) if ranks else 0.0,
            "misses": [probe["query"] for probe in paraphrase if not probe["hit"]],
        }
    if flags:
        quality["flag_correctness"] = {
            "checked": len(flags),
            "correct_rate": round(sum(1 for probe in flags if probe["correct"]) / len(flags), 4),
            "wrong": [{"id": probe["id"], "expected": probe["expected_flag"], "actual": probe["actual_flag"]} for probe in flags if not probe["correct"]],
        }
    for kind in ("conflict_marking", "dedup", "secret_rejection", "compact_vs_verbose", "hygiene_detection", "hygiene_apply_safe", "contract_exposure"):
        found = of(kind)
        if found:
            quality[kind] = found if len(found) > 1 else found[0]
    return quality


def _latency_metrics(latencies: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[float]] = {}
    for entry in latencies:
        grouped.setdefault(entry["operation"], []).append(float(entry["duration_ms"]))
    return {
        operation: {
            "count": len(values),
            "p50_ms": _percentile(values, 0.50),
            "p95_ms": _percentile(values, 0.95),
            "max_ms": round(max(values), 2),
        }
        for operation, values in sorted(grouped.items())
    }


def _growth_metrics(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    by_scenario: dict[str, list[dict[str, Any]]] = {}
    for snapshot in snapshots:
        by_scenario.setdefault(snapshot["scenario"], []).append(snapshot)
    growth: dict[str, Any] = {}
    for scenario, entries in by_scenario.items():
        ordered = sorted(entries, key=lambda item: item["session"])
        first, last = ordered[0], ordered[-1]
        growth[scenario] = {
            "sessions": len(ordered),
            "cards_first_session": first["total"],
            "cards_last_session": last["total"],
            "cards_added": last["total"] - first["total"],
            "cards_per_session": round((last["total"] - first["total"]) / max(1, len(ordered) - 1), 2) if len(ordered) > 1 else 0,
            "db_bytes_last": last["db_bytes"],
            "status_distribution_last": last["statuses"],
        }
    return growth


def _leak_sweep(emissions: list[dict[str, Any]]) -> dict[str, Any]:
    leaks = [
        {"channel": entry["channel"], "scenario": entry["scenario"], "turn": entry.get("turn")}
        for entry in emissions
        if SECRET_MARKER in entry.get("text", "")
    ]
    return {"marker": SECRET_MARKER[:12] + "…", "leaks_found": len(leaks), "locations": leaks}
