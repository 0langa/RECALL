"""Human-readable markdown rendering of a benchmark report."""

from __future__ import annotations

from typing import Any

from .tokens import humanize


def _tok(value: Any) -> str:
    """Exact token count first (this is test output), short form for scanning."""
    if not isinstance(value, (int, float)):
        return str(value)
    return f"{value} (~{humanize(value)})" if value >= 1_000 else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    meta = report.get("meta", {})
    metrics = report.get("metrics", {})
    token_data = metrics.get("tokens", {})
    lines = [
        f"# RECALL benchmark — {meta.get('mode', 'custom')} mode",
        "",
        f"- version: {meta.get('recall_version', '?')}  |  seed: {meta.get('seed')}  |  scenarios: {', '.join(meta.get('scenarios', []))}",
        f"- emission determinism hash: `{meta.get('emission_hash', '')[:16]}…`",
        "",
        "## Token cost",
        f"- fixed overhead per session: **{_tok(token_data.get('fixed_overhead_per_session_est_tokens', '?'))} est tokens**",
        f"- marginal per turn: **{_tok(token_data.get('marginal_per_turn_est_tokens', '?'))} est tokens**",
        f"- projected 20-turn session: **{_tok(token_data.get('projected_session_est_tokens_20_turns', '?'))} est tokens**",
    ]
    if "projected_session_cost_usd_20_turns" in token_data:
        # Dollar line only appears when the run was explicitly priced.
        lines.append(
            f"- projected 20-turn session cost: **${token_data['projected_session_cost_usd_20_turns']}** "
            f"(at ${token_data['price_per_million_used']}/M input tokens)"
        )
    lines += ["", "| channel | count | est tokens | fixed |", "|---|---|---|---|"]
    for name, bucket in token_data.get("per_channel", {}).items():
        lines.append(f"| {name} | {bucket['count']} | {bucket['est_tokens']} | {'yes' if bucket['fixed'] else ''} |")

    gate = metrics.get("injection_gate", {})
    if gate.get("labeled_turns"):
        lines += [
            "",
            "## Injection gate",
            f"- accuracy: **{gate.get('accuracy')}** over {gate['labeled_turns']} labeled turns",
            f"- false injections (wasted tokens): {gate['false_inject']}  |  false suppressions (lost context): {gate['false_suppress']}",
        ]

    quality = metrics.get("quality", {})
    retrieval = quality.get("retrieval")
    if retrieval:
        lines += [
            "",
            "## Quality",
            f"- golden retrieval hit rate: **{retrieval['hit_rate_at_limit']}** (MRR {retrieval['mrr']}, {retrieval['queries']} queries)",
        ]
        if retrieval.get("misses"):
            lines.append(f"  - misses: {', '.join(retrieval['misses'])}")
    flag_data = quality.get("flag_correctness")
    if flag_data:
        lines.append(f"- flag correctness: **{flag_data['correct_rate']}** over {flag_data['checked']} lifecycle cards")
    dedup = quality.get("dedup")
    if dedup:
        lines.append(f"- dedup: duplicate confirmed existing = **{dedup.get('duplicate_confirmed_existing')}**, distinct saved = {dedup.get('distinct_saved')}")
    secret = quality.get("secret_rejection")
    if secret:
        lines.append(f"- secret rejection at write: **{secret.get('rejected')}**")
    hygiene = quality.get("hygiene_detection")
    if hygiene:
        lines.append(f"- hygiene detection rate on planted-bad pack: **{hygiene.get('detection_rate')}** (false positives: {len(hygiene.get('false_positive_golden_ids', []))})")

    leaks = metrics.get("secret_leaks", {})
    leak_count = leaks.get("leaks_found", 0)
    lines += ["", f"## Secret leak sweep: {'CLEAN' if not leak_count else f'{leak_count} LEAK(S) FOUND'}"]

    latency = metrics.get("latency", {})
    if latency:
        lines += ["", "## Latency", "| operation | p50 ms | p95 ms | max ms |", "|---|---|---|---|"]
        for operation, stats in latency.items():
            lines.append(f"| {operation} | {stats['p50_ms']} | {stats['p95_ms']} | {stats['max_ms']} |")

    growth = metrics.get("store_growth", {})
    if growth:
        lines += ["", "## Store growth", "| scenario | sessions | cards added | cards/session | db bytes |", "|---|---|---|---|---|"]
        for scenario, stats in growth.items():
            lines.append(f"| {scenario} | {stats['sessions']} | {stats['cards_added']} | {stats['cards_per_session']} | {stats['db_bytes_last']} |")

    comparison = report.get("baseline_comparison")
    if comparison:
        lines += ["", f"## Baseline comparison: {'PASS' if comparison['pass'] else 'FAIL'}"]
        for name, delta in comparison.get("deltas", {}).items():
            lines.append(f"- {name}: {delta}")
        for violation in comparison.get("violations", []):
            lines.append(f"- VIOLATION: {violation}")

    return "\n".join(lines) + "\n"
