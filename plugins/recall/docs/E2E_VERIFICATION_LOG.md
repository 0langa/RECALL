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
- `v0.1.0` tag and GitHub release with `recall.zip` artifact: pass.
- User-provided Codex App screenshots confirmed RECALL appears in the plugin picker, bundled skills are discoverable from the composer, and RECALL hooks can be trusted/enabled in Settings > Coding > Hooks.
- User-provided live continuation and new-session tests confirmed hook activation without `hook exited with code 1`; `Stop` saved checkpoints `#10` and `#27` in the project memory store.

## Residual Verification Note

- Direct visual inspection of exact hook-injected text in the Codex transcript remains limited by the app UI. Current installed-cache smoke verifies that `SessionStart` stays quiet and explicit `@recall` prompt invocation retrieves relevant local context.

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
- Historical finding: `PostToolUse` was functionally working but captured noisy successful command output in some cases. Current behavior buffers compact evidence only after explicit RECALL activation and relies on the Stop finalizer for durable writes.

## Opt-In Hook Retest And Cleanup

Date: 2026-06-10

Current behavior is explicit-activation first:

- A prompt without `@recall`, `plugin://recall`, or `$recall:` leaves `PostToolUse`, `PreCompact`, and `Stop` idle.
- `UserPromptSubmit` activates the turn only after explicit RECALL invocation.
- `PostToolUse` buffers compact evidence for activated turns and does not directly write durable command memory.
- `Stop` emits one compact inline finalizer request with `PACKET=` JSON when buffered evidence deserves review.
- `SessionStart` stays quiet; explicit `@recall` prompt retrieval injects curated context.
- Live cleanup used `archive-noise` non-destructively. After cleanup, `archive-noise` dry-run matched `0` remaining records, and review showed `217` active memories and `579` archived memories.

## Codex And Kimi Split Retest

Date: 2026-06-25

Environment:

- Codex CLI: `codex-cli 0.140.0`
- Kimi Code CLI: `0.19.2`
- Codex install: `recall@recall-local` reinstalled from the repository marketplace into `<home>\.codex\plugins\cache\recall-local\recall\1.0.0`
- Kimi install: fresh `dist/recall.zip` expanded into `<home>\.kimi-code\plugins\managed\recall`

Automated verification:

- `python -m unittest discover -s plugins\recall\tests`: pass, 150 tests.
- `python RECALL_quality_suite\scripts\run_recall_quality_suite.py --repo-root . --quick`: pass.
- `python build_plugin.py --skip-validator`: pass; package inspection reported 81 entries, no warnings, no errors.
- `kimi doctor`: pass after RECALL hooks were added to `~/.kimi-code/config.toml`.

Issue found and fixed:

- Kimi `UserPromptSubmit` hook payloads send `prompt` as content parts, for example `[{"type":"text","text":"..."}]`.
- RECALL's provider-neutral hook normalizer previously accepted string prompts only, so Kimi hook retrieval worked but `@recall remember this:` was not saved by the hook itself.
- `hook_events.py` now normalizes Kimi-style content parts into the same prompt string shape used by Codex.
- Regression coverage was added for the normalizer and for `prompt_inspector.py` saving categorized memories from a Kimi-shaped content-part payload.

Live Kimi checks:

- `kimi -p` in a fresh project with `@recall initialize this project` printed `RECALL activated for project ...`.
- A follow-up `kimi -p` prompt with `@recall remember this: requirements: Kimi hook content parts save marker 20260625...` printed `RECALL saved memory #1 in requirements` from the `UserPromptSubmit` hook.
- Retrieval through the installed Kimi plugin copy returned the saved memory with `origin_provider: kimi` and `capture_channel: hook`.
- `doctor` on the Kimi test project reported `records: 1`, `index_records: 1`, `index_complete: true`, and no warnings.

Live Codex checks:

- `codex exec --dangerously-bypass-hook-trust --enable hooks` in a fresh project with `@recall initialize this project` printed `RECALL activated for project ...`.
- A follow-up `codex exec` prompt with `@recall remember this: requirements: Codex hook e2e marker 20260625...` printed `RECALL saved memory #1 in requirements` from the `UserPromptSubmit` hook.
- Retrieval through the installed Codex plugin cache returned the saved memory with `origin_provider: codex` and `capture_channel: hook`.
- `doctor` on the Codex test project reported `records: 1`, `index_records: 1`, `index_complete: true`, and no warnings.

Cross-provider checks:

- Kimi, running in the Codex-written test project, retrieved the Codex memory through hook-injected RECALL context.
- Codex, running in the Kimi-written test project, retrieved the Kimi memory through hook-injected RECALL context.
- This confirms Codex and Kimi share project-local `.recall/` memory and use provider metadata as provenance, not as separate memory stores.

## Kimi Tool Wrapper Finalizer Retest

Date: 2026-06-29

Environment:

- Codex install: `recall@recall-local` reinstalled from the repository marketplace into `<home>\.codex\plugins\cache\recall-local\recall\1.0.0`
- Kimi install: fresh `dist/recall.zip` expanded into `<home>\.kimi-code\plugins\managed\recall`
- Kimi test project: `<temp>\recall-kimi-wrapperfix2-e2e`
- Codex test project: `<temp>\recall-codex-wrapperfix-e2e`

Automated verification:

- `python -m unittest discover -s plugins\recall\tests`: pass, 153 tests.
- `python RECALL_quality_suite\scripts\run_recall_quality_suite.py --repo-root . --quick`: pass.
- `python build_plugin.py --skip-validator`: pass; package inspection reported 81 entries, no warnings, no errors.
- `kimi doctor`: pass after installing the rebuilt RECALL copy.

Issue found and fixed:

- Kimi Code can report failed shell tools as JSON envelopes whose `message` field contains the real failure, for example a failed `uv run pytest -q --tb=short .` surfaced as `{"code":"internal","message":"error: Failed to spawn: `pytest`...","retryable":false}`.
- RECALL now unwraps those envelopes before compacting tool evidence, so finalizer candidates contain the distilled failure text rather than raw provider wrapper JSON.
- The finalizer service also ignores tool-tagged cards that still copy raw wrapper JSON, which protects the durable store if an agent tries to save the envelope directly.
- Transient operational prompts such as "Run exactly this shell command" and "Do not call RECALL MCP save tools" are no longer classified as durable project requirements.

Live Kimi checks:

- `kimi -p` in a fresh project with `@recall initialize this project` activated RECALL.
- A follow-up `kimi -p` prompt ran `uv run pytest -q --tb=short .` through the console; Kimi returned the failed spawn condition for `pytest`.
- Installed Kimi RECALL `doctor` reported `records: 1`, `index_records: 1`, `index_complete: true`, and no warnings.
- `review-memory` showed one active `debug_history` record from the finalizer with a `Failed to spawn` summary for `pytest` and tags `tool-use`, `bash`, `failure`, and `tests`.
- The durable memory content contained `Tool: Bash`, the command, the `Failed to spawn` failure, and `exit_code: 2`; it did not contain `{"code"`, `"retryable"`, or the transient test prompt.

Live Codex checks:

- `codex exec --dangerously-bypass-hook-trust --enable hooks` in a fresh project with `@recall initialize this project` activated RECALL.
- A follow-up `codex exec` prompt ran the same missing-`pytest` command. The Codex project memory remained free of raw wrapper JSON and did not store the transient command prompt as a requirement.
- A second `codex exec` prompt with `@recall remember this: requirements: Codex wrapper-fix e2e marker 20260629-1738` saved one explicit requirement through the installed plugin.
- Installed Codex RECALL `doctor` reported `records: 1`, `index_records: 1`, `index_complete: true`, and no warnings.
- `review-memory` showed exactly the explicit Codex marker, with no active noise candidates and a signal-to-noise estimate of `1.0`.
