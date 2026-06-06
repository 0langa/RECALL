# RECALL Release Checklist

Use this checklist before tagging a public RECALL release.

Run local plugin commands from `<repo-root>/plugins/recall` unless a step explicitly says to use `<repo-root>`.

## Local Gates

- [ ] `python -m unittest discover -s tests`
- [ ] `python <plugin-creator-path>\scripts\validate_plugin.py <repo-root>/plugins/recall`
- [ ] `python .\scripts\smoke_recall.py --json`
- [ ] `.\build_plugin.ps1` from `<repo-root>` or `<repo-root>/plugins/recall`
- [ ] `python .\scripts\inspect_package.py .\dist\recall.zip`

## Install Lifecycle

- [ ] Install from `.agents/plugins/marketplace.json` in Codex.
- [ ] Confirm `RECALL` appears in the plugin picker and can be enabled.
- [ ] Confirm bundled skills are discoverable in a new thread.
- [ ] Review and trust bundled hooks through `/hooks`.
- [ ] In a temp project, say “remember this” and verify `UserPromptSubmit` stores a preference.
- [ ] Run a successful command and verify `PostToolUse` stores a compact command memory.
- [ ] Start a new thread in the same project and verify `SessionStart` injects relevant local context.
- [ ] Run `python .\scripts\memory_manager.py doctor`.
- [ ] Corrupt or delete `vector_index.bin`, run `python .\scripts\memory_manager.py repair`, and verify final health.
- [ ] Uninstall and reinstall the plugin, then repeat a minimal save/query check.

## Public Surface

- [ ] README has current install, smoke, build, known limitations, and troubleshooting guidance.
- [ ] `docs/PRIVACY.md` exists and matches the local-only storage behavior.
- [ ] Manifest public URLs are stable, if included.
- [ ] Package inspection reports no runtime data, cache files, personal paths, or secret-like strings.
- [ ] `CHANGELOG.md` has the release date and user-visible changes.

## Tag And Artifact

- [ ] Tag `v0.1.0` only after local gates and install lifecycle pass.
- [ ] Create the GitHub release from the tag.
- [ ] Attach `dist/recall.zip` as a release artifact.
- [ ] Do not commit `dist/recall.zip`.
