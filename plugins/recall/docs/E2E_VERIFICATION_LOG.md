# RECALL E2E Verification Log

Date: 2026-06-06

## Environment

- Codex CLI: `codex-cli 0.135.0`
- Repository layout: marketplace wrapper at `<repo-root>`, installable plugin at `<repo-root>/plugins/recall`
- Marketplace file: `<repo-root>/.agents/plugins/marketplace.json`
- Marketplace source path: `./plugins/recall`
- Installed plugin cache path: `<codex-cache>/plugins/cache/recall-local/recall/0.1.0`

## Verified

- `python -m unittest discover -s tests` from `<repo-root>/plugins/recall`: pass, 42 tests.
- `python <plugin-creator>/scripts/validate_plugin.py <repo-root>/plugins/recall`: pass.
- `python ./scripts/smoke_recall.py --json` from `<repo-root>/plugins/recall`: pass.
- `codex plugin marketplace add <repo-root>`: marketplace `recall-local` added.
- `codex plugin list`: shows `recall@recall-local` from `<repo-root>/plugins/recall`.
- `codex plugin add recall@recall-local`: installs and enables RECALL.
- Installed-cache smoke: `python <repo-root>/plugins/recall/scripts/smoke_recall.py --installed-plugin-root <codex-cache>/plugins/cache/recall-local/recall/0.1.0 --json`: pass.
- `./build_plugin.ps1` from `<repo-root>`: pass; delegates to `<repo-root>/plugins/recall`, runs tests, validator, smoke, builds `dist/recall.zip`, and package-inspects the zip.
- `codex plugin remove recall@recall-local` followed by `codex plugin add recall@recall-local`: pass.

## Not Yet Fully Verified

- Codex App plugin picker visibility. CLI listing confirms the marketplace entry; App UI still needs visual confirmation.
- Hook trust flow through `/hooks`. Hook definitions are source-tested and installed-cache smoke-tested, but the interactive trust review must be confirmed in a live Codex thread.
- Bundled skill discovery in a new thread after install. Current source tests verify skill files and plugin installation, but new-thread slash/mention behavior needs live UI/CLI confirmation.
- Real `SessionStart` injection in a fresh Codex thread. Smoke harness invokes the installed hook scripts with Codex-shaped payloads; live lifecycle injection still needs manual thread verification.

## Notes

- Repo-root marketplace paths `./`, `./.`, and `.` were skipped by `codex plugin add`. Moving the plugin to `./plugins/recall` matches the official repo-marketplace layout and makes `recall@recall-local` discoverable/installable.
- Runtime memories remained project-local under temp project `.codex_memory/` directories during smoke tests.
