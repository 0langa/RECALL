# RECALL Release Checklist

Use this checklist before tagging a public RECALL release.

Run local plugin commands from `<repo-root>/plugins/recall` unless a step explicitly says to use `<repo-root>`.

## Local Gates

- [x] `python -m unittest discover -s tests` (124+ tests)
- [x] Persistent activation, greenfield initialization, deactivation, buffered hooks, atomic finalization, idempotency, and relevance calibration are covered.
- [x] Quick seed benchmark is under 20 seconds and full seed benchmark is under 90 seconds.
- [x] Corpus migration creates a backup and leaves zero active automatic file-edit/build/test noise records.
- [x] `python <plugin-creator-path>\scripts\validate_plugin.py <repo-root>/plugins/recall`
- [x] `python .\scripts\smoke_recall.py --json`
- [x] `python .\scripts\recall_skill.py retrieve-memory "current project context" --summary`
- [x] `python build_plugin.py` from `<repo-root>` or `python scripts/build_plugin.py` from `<repo-root>/plugins/recall`
- [x] `python .\scripts\inspect_package.py .\dist\recall.zip`
- [x] `python .\scripts\smoke_zip_marketplace.py --json`

## Install Lifecycle

- [x] Install from `.agents/plugins/marketplace.json` in Codex CLI.
- [x] Confirm `RECALL` appears in the plugin picker and can be enabled.
- [ ] Confirm bundled skills are discoverable in a new thread.
- [ ] Review and trust bundled hooks in Codex Settings > Coding > Hooks.
- [x] In a temp project, submit a prompt without `@recall` and verify hooks stay idle with no durable memory write.
- [x] In a temp project, simulate `@recall remember this:` and verify `UserPromptSubmit` stores a preference.
- [x] Simulate a successful command after explicit `@recall` activation and verify `PostToolUse` buffers compact evidence without writing durable command memory.
- [x] Trigger `Stop` after buffered evidence and verify it emits one compact inline finalizer request.
- [ ] Start a new thread in the same project and verify `SessionStart` stays quiet; explicit `@recall` prompt retrieval injects relevant local context.
- [x] Run installed-bundle skill adapter retrieval rather than source-only backend commands.
- [x] Run `python .\scripts\recall_skill.py archive-noise` as a dry run before any live cleanup.
- [x] Run `python .\scripts\recall_skill.py archive-noise --apply --limit <n>` only after reviewing dry-run matches.
- [x] Run `python .\scripts\memory_manager.py doctor` only as a developer/support diagnostic.
- [x] Corrupt or delete `vector_index.bin`, run `python .\scripts\memory_manager.py repair`, and verify final health as a maintenance diagnostic.
- [x] Uninstall and reinstall the plugin, then repeat a minimal save/query check through the installed bundle.
- [x] Install from built zip extraction through a temporary marketplace and run installed-cache smoke.

## Public Surface

- [x] README has current install, smoke, build, known limitations, and troubleshooting guidance.
- [x] `docs/PRIVACY.md` exists and matches the local-only storage behavior.
- [x] Manifest public URLs are stable, if included.
- [x] Package inspection reports no runtime data, cache files, personal paths, or secret-like strings.
- [x] Bundled skills reference `recall_skill.py` and do not advertise the backend maintenance CLI.
- [x] `CHANGELOG.md` has the release date and user-visible changes.

## Tag And Artifact

- [x] Tag `v1.0.0` only after local gates, install lifecycle, and real-project field testing pass.
- [x] Create the GitHub release from the tag.
- [x] Attach `dist/recall.zip` as a release artifact.
- [x] Do not commit `dist/recall.zip`.

## Certification

- [x] PluginEval quick scores at least 80 for all five primary skills.
- [ ] PluginEval standard scores at least 80 for all five primary skills.
- [ ] PluginEval deep certification meets the release threshold.
- [ ] Human source-blind evaluation meets the final threshold.
- [ ] Cross-agent agreement meets the final threshold.

See `docs/RELEASE_EVIDENCE_2026-06-12.md` for current automated evidence and blockers.
