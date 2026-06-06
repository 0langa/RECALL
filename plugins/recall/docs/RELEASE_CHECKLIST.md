# RECALL Release Checklist

Use this checklist before tagging a public RECALL release.

Run local plugin commands from `<repo-root>/plugins/recall` unless a step explicitly says to use `<repo-root>`.

## Local Gates

- [x] `python -m unittest discover -s tests`
- [x] `python <plugin-creator-path>\scripts\validate_plugin.py <repo-root>/plugins/recall`
- [x] `python .\scripts\smoke_recall.py --json`
- [x] `.\build_plugin.ps1` from `<repo-root>` or `<repo-root>/plugins/recall`
- [x] `python .\scripts\inspect_package.py .\dist\recall.zip`

## Install Lifecycle

- [x] Install from `.agents/plugins/marketplace.json` in Codex CLI.
- [ ] Confirm `RECALL` appears in the plugin picker and can be enabled.
- [ ] Confirm bundled skills are discoverable in a new thread.
- [ ] Review and trust bundled hooks through `/hooks`.
- [x] In a temp project, simulate “remember this” and verify `UserPromptSubmit` stores a preference.
- [x] Simulate a successful command and verify `PostToolUse` stores a compact command memory.
- [ ] Start a new thread in the same project and verify `SessionStart` injects relevant local context.
- [x] Run `python .\scripts\memory_manager.py doctor`.
- [x] Corrupt or delete `vector_index.bin`, run `python .\scripts\memory_manager.py repair`, and verify final health.
- [x] Uninstall and reinstall the plugin, then repeat a minimal save/query check.

## Public Surface

- [x] README has current install, smoke, build, known limitations, and troubleshooting guidance.
- [x] `docs/PRIVACY.md` exists and matches the local-only storage behavior.
- [x] Manifest public URLs are stable, if included.
- [x] Package inspection reports no runtime data, cache files, personal paths, or secret-like strings.
- [x] `CHANGELOG.md` has the release date and user-visible changes.

## Tag And Artifact

- [ ] Tag `v0.1.0` only after local gates and install lifecycle pass.
- [ ] Create the GitHub release from the tag.
- [ ] Attach `dist/recall.zip` as a release artifact.
- [ ] Do not commit `dist/recall.zip`.
