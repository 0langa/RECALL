"""RECALL benchmark/eval harness.

Layer 1: deterministic engine benchmark (token cost, quality, latency) —
drives the real hooks, MCP server, and skill adapter exactly like providers
do, records every agent-visible emission, and computes comparable metrics.

Layer 2: agent-compliance evaluation — the calling agent is the test subject;
grading happens on artifacts (store diffs, debug traces, emission journal).

Judge: optional two-phase LLM scoring of recorded artifacts. This package
never calls a model itself; it only emits and aggregates judge task files.

Maintainer tooling: lives in the repository, never shipped in the plugin zip.
"""

from __future__ import annotations

BENCH_SCHEMA_VERSION = 1
