# RECALL E2E Verification Log

Date: 2026-06-06

## Environment

- Codex CLI: `codex-cli 0.135.0`
- Repository layout: marketplace wrapper at `<repo-root>`, installable plugin at `<repo-root>/plugins/recall`
- Marketplace file: `<repo-root>/.agents/plugins/marketplace.json`
- Marketplace source path: `./plugins/recall`
- Installed plugin cache path: `<codex-cache>/plugins/cache/recall-local/recall/0.1.0`

## Verified

- `python -m unittest discover -s tests` from `<repo-root>/plugins/recall`: pass, 47 tests.
- `python <plugin-creator>/scripts/validate_plugin.py <repo-root>/plugins/recall`: pass.
- `python ./scripts/smoke_recall.py --json` from `<repo-root>/plugins/recall`: pass.
- `codex plugin marketplace add <repo-root>`: marketplace `recall-local` added.
- `codex plugin list`: shows `recall@recall-local` from `<repo-root>/plugins/recall`.
- `codex plugin add recall@recall-local`: installs and enables RECALL.
- Installed-cache smoke: `python <repo-root>/plugins/recall/scripts/smoke_recall.py --installed-plugin-root <codex-cache>/plugins/cache/recall-local/recall/0.1.0 --json`: pass.
- Built-archive marketplace smoke: extract `dist/recall.zip` into a temporary marketplace wrapper, install `recall@recall-zip-test-*`, run installed-cache smoke, then remove the temporary plugin and marketplace: pass.
- `./build_plugin.ps1` from `<repo-root>`: pass; delegates to `<repo-root>/plugins/recall`, runs tests, validator, smoke, builds `dist/recall.zip`, and package-inspects the zip.
- `codex plugin remove recall@recall-local` followed by `codex plugin add recall@recall-local`: pass.
- User-provided Codex App screenshots confirmed RECALL appears in the plugin picker, bundled skills are discoverable from the composer, and RECALL hooks can be trusted/enabled in Settings > Coding > Hooks.
- User-provided live continuation and new-session tests confirmed hook activation without `hook exited with code 1`; `Stop` saved checkpoints `#10` and `#27` in the project memory store.

## Not Yet Fully Verified

- Direct visual inspection of the exact `SessionStart` injected context in the Codex transcript remains limited by the app UI. Installed-cache smoke verifies the `SessionStart` `additionalContext` payload, and user screenshots verify the live hook activation.

## Notes

- Repo-root marketplace paths `./`, `./.`, and `.` were skipped by `codex plugin add`. Moving the plugin to `./plugins/recall` matches the official repo-marketplace layout and makes `recall@recall-local` discoverable/installable.
- Runtime memories remained project-local under temp project `.codex_memory/` directories during smoke tests.

## Hook Follow-Up

Date: 2026-06-06

Observed user evidence showed `SessionStart`, `UserPromptSubmit`, `PostToolUse`, and `Stop` all exiting with code `1` in the Codex hook panel. Manual skill/CLI save and retrieve worked, and the live project database/index were healthy.

Follow-up testing showed:

- Direct script execution with `PLUGIN_ROOT` expanded by PowerShell exited `0`.
- The previous `commandWindows` form used `%PLUGIN_ROOT%`, which is fragile when invoked from PowerShell-style command execution.
- The Windows hook command now uses a Python launcher that reads `PLUGIN_ROOT` from `os.environ`, adds the hook script directory to `sys.path`, and runs the script with `runpy`.
- Source regression test: `test_windows_hook_commands_run_through_powershell` passes.
- Installed-cache hook command test: all installed `commandWindows` hooks exit `0` through PowerShell.
- Source smoke, installed-cache smoke, plugin validator, package inspection, and root build all pass after reinstalling `recall@recall-local`.

## Live Hook Retest Follow-Up

Date: 2026-06-06

User retested RECALL in a local `RECALL-testing` project with a continuation thread and a new thread. Hook UI screenshots showed no `hook exited with code 1` failures after reinstall/trust. Database/index cross-check found `27` SQLite records and `27` vector-index rows with `doctor` reporting `index_complete: true` and no warnings.

Findings:

- Continuation test matched hook UI: `UserPromptSubmit`, `8` `PostToolUse` runs, and `Stop` produced records `#1` through `#10`, with Stop saving checkpoint `#10`.
- New-session test matched hook UI: `SessionStart`, `UserPromptSubmit`, `15` `PostToolUse` runs, and `Stop` produced records `#11` through `#27`, with Stop saving checkpoint `#27`.
- `SessionStart` injection ran without writing a record, which is expected.
- `UserPromptSubmit` created one false-positive memory from incidental text containing `remembered`; prompt cue detection was tightened to explicit `remember:` / `remember this:` / `remember that:` forms.
- `PostToolUse` was functionally working but still captured noisy successful command output in some cases; command compaction now strips ANSI sequences and stores command/status summaries instead of raw directory or file-list dumps.
