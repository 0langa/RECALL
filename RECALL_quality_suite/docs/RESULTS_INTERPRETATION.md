# Results Interpretation

## PASS

A gate passes when all assertions complete and the result object contains `"status": "pass"`.

## FAIL

A gate fails when:

- A Python test assertion fails.
- A subprocess exits non-zero.
- JSON output is malformed where JSON is required.
- Mandatory files or manifest fields are missing.
- Hook output does not continue safely.
- Secret-like values are stored unredacted.
- Runtime memory escapes the project `.codex_memory` directory.
- Package hygiene finds runtime data, caches, personal paths, or secret-like strings.
- Performance thresholds are exceeded.

## SKIP

A gate may be skipped only when it is explicitly optional, for example package-hygiene when no ZIP artifact exists and `--require-package` was not passed.

## Release interpretation

- All automated mandatory gates passing means the implementation is technically healthy enough for release-candidate testing, not automatic final release.
- Treat RECALL as alpha-stage until the roadmap and production criteria support promotion.
- It is not production-ready until the human source-blind agent evaluation also passes.
- Any hallucinated confidence during the source-blind evaluation is a release blocker.
