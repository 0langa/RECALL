# RECALL Manual Release Notes

Date: 2026-06-16
Version: 1.0.0
Release tag: v1.0.0
Decision: release ready

## Summary

RECALL is release-ready for the local Codex plugin workflow. The final pass combined the scripted manual workflow, installed-cache smoke tests, source-blind CLI checks, cross-platform package building, and a real-world field test using the existing Scalpel development repository.

## Final Fixes

- Hardened failure capture so useful failed commands can become `debug_history` without turning failed commands into reusable `commands`.
- Prevented conditional command prompts from being saved before the command actually passes.
- Fixed natural-language activation such as `Use RECALL for this project`.
- Preserved explicit category routing for prompts such as `@recall remember this: requirements: ...`.
- Added claim-key handling for release-note path requirements and corrections.
- Added source-blind category matching so prompts asking for current requirements/risks receive relevant current memory.
- Prevented Stop finalizer from saving raw user prompt or implementation-plan transcript blobs as validated decisions.
- Superseded stale/prompt-shaped Scalpel memories and confirmed real-world memory retrieval now favors distilled outcome records.
- Replaced duplicated PowerShell and shell packaging logic with a cross-platform Python build path while keeping wrapper scripts as convenience entry points.
- Documented GitHub marketplace installation with `codex plugin marketplace add 0langa/RECALL --ref v1.0.0`.

## Validation

- `python -m pytest plugins\recall\tests -q`: passed.
- `python RECALL_quality_suite\scripts\run_recall_quality_suite.py --repo-root . --quick`: passed.
- `python build_plugin.py`: passed; package had no warnings or errors.
- Installed-cache smoke against the Codex-installed RECALL cache root: passed.
- Scalpel real-project memory audit: doctor clean, no conflicts, no active noise candidates, signal-to-noise estimate 1.0.

## Residual Notes

- RECALL remains local-first and stores project memory under each project root.
- Stale or superseded memories are retained for history but excluded from default current retrieval.
- Future improvements should focus on better ranking for broad "what next" prompts and richer automatic current-state supersession.
