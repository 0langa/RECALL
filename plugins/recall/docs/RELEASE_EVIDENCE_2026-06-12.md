# Release Evidence - 2026-06-12

## Automated gates passed

- 117 plugin tests on Windows/Python 3.13.
- Full RECALL quality suite, including semantic contracts, smoke, package hygiene, and the 500-record performance benchmark.
- Plugin Creator source validation.
- Source checkout smoke, clean installed-cache smoke, and built-ZIP marketplace smoke.
- Portable export/restore preserves IDs, lifecycle, provenance, and relationships.
- Secret-like content is redacted at the storage and export boundaries.
- Source-blind evaluator pack generated with 14 cards.
- PluginEval quick scores exceed 80 for all five primary skills with no anti-pattern flags.

Installed version: `0.1.0+codex.20260612112808`.

## Gates not certified

- PluginEval standard and deep: the evaluator reaches `claude-agent-sdk` but aborts with `Claude Code returned an error result: success`. No standard or deep score is claimed.
- Human source-blind scoring, cross-agent agreement, and fresh-thread skill discovery still require separate evaluator sessions.
- macOS and Linux smoke are configured in `.github/workflows/recall-quality.yml`; this Windows run does not claim those jobs have executed.
- Optional MCP facade was not implemented because its documented preconditions are not met and no measured benefit over the shared CLI/skill services has been established.

These open gates block Final Product certification. The artifact is automated-gate clean, not fully human-certified.
