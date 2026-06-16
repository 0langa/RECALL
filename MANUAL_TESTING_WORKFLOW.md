# RECALL Manual Testing Workflow

This workflow is for finding real-world gaps that automated tests and PluginEval can miss. It focuses on user-visible behavior, project-scoped activation, auto-memory management, corpus quality, quiet-mode hooks, and installed-plugin readiness.

Run this from `C:\Users\Julius\source\repos\RECALL` unless a step says otherwise.

Current UI-app manual fixture paths:

- Main activated project: `C:\Users\Julius\source\test_enviroments\RECALL\project`
- Second activated project: `C:\Users\Julius\source\test_enviroments\RECALL\project2`
- Non-project/greenfield fixture: `C:\Users\Julius\source\test_enviroments\RECALL\recall-nonproject-manual`

The phases below assume you are testing primarily in the Codex App UI. Use terminal commands only as an external audit/check after the UI turn has finished.

## Current Remaining Work

Status as of 2026-06-16 after unattended hook, skill-adapter, installed-cache, source-blind `codex-cli 0.140.0`, and real Scalpel repository field testing:

- No open release blockers.

The final release decision is recorded in `docs\manual-release-notes.md`. Keep the phase details below as the reproducible procedure.

## Goals

- Verify RECALL does not create memory stores for ordinary non-project prompts.
- Verify one explicit RECALL activation enables persistent project-local memory across later prompts and new sessions.
- Verify automatic memory capture is semantic, low-noise, and not command spam.
- Verify quiet mode hides all finalizer internals from the user.
- Verify debug mode exposes enough trace data for development without indexing it.
- Verify retrieval is relevant, sufficient, and honest when memory is missing.
- Verify migration and lifecycle behavior preserve history without destructive cleanup.
- Produce a release-readiness decision with concrete evidence.

## Prerequisites

- Python launcher and `python` are available.
- Current plugin is built and installed in Codex.
- Hooks are trusted in Codex Settings.
- `GITHUB_TOKEN`, `OPENAI_API_KEY`, and `KIMI_API_KEY` are available if you also run remote evals.
- Use a separate scratch directory for destructive or negative manual tests.

Recommended baseline commands:

```powershell
cd C:\Users\Julius\source\repos\RECALL
python -m unittest discover -s plugins\recall\tests -q
python RECALL_quality_suite\scripts\run_recall_quality_suite.py --repo-root . --quick
.\build_plugin.ps1
python plugins\recall\scripts\smoke_recall.py --installed-plugin-root C:\Users\Julius\.codex\plugins\cache\recall-local\recall\0.1.0+codex.20260615152000 --json
```

Do not treat these commands as release proof. They only establish a clean starting point.

## Evidence Log

Create a local evidence file while testing:

```powershell
New-Item -ItemType Directory -Force quality_results\manual | Out-Null
New-Item -ItemType File -Force quality_results\manual\manual_test_notes.md | Out-Null
```

For every test below, record:

- Date and Codex version, if visible.
- Plugin install source: source, installed cache, or built zip.
- Project path.
- Prompt used.
- Expected behavior.
- Actual behavior.
- Memory IDs created or updated.
- Screenshots for visible UI issues.
- Final pass/fail.

## Phase 1: Fresh Install Sanity

Status: PASS. Build, `codex plugin add recall@recall-local`, installed-cache smoke, and real Codex App usage all succeeded.

1. Build and install the current plugin.

```powershell
.\build_plugin.ps1
codex plugin add recall@recall-local
```

2. Open a fresh Codex thread in `C:\Users\Julius\source\repos\RECALL`.

3. Confirm these are true in the UI:

- RECALL appears in the plugin picker.
- RECALL skills are discoverable.
- Hooks are present and trusted.
- No hook error appears on thread start.

Fail if:

- A hook exits with code 1.
- The plugin picker points to an old cache path unexpectedly.
- Hook trust review reappears after being accepted without an intentional reinstall.

## Phase 2: No Accidental Project Creation

Status: PASS. Covered by unattended hook/skill simulation; evidence in `quality_results\manual\manual_test_notes.md`.

Use a non-project folder:

```powershell
$scratch = "C:\Users\Julius\source\test_enviroments\RECALL\recall-nonproject-manual"
Remove-Item -Recurse -Force $scratch -ErrorAction SilentlyContinue
New-Item -ItemType Directory $scratch | Out-Null
```

Open a fresh Codex thread in that folder.

Important Codex App caveat: the app may create a `.git` folder automatically on the first prompt. Once `.git` exists, RECALL correctly treats the folder as a recognized project. In that case this phase can still verify that ordinary prompts do not create `.codex_memory`, but an explicit `@recall` mention is expected to activate the project and create `.codex_memory`.

For a true unrecognized-folder test, use a folder with no `.git` and run the hook/CLI simulation outside a Codex App thread, or remove `.git` before the explicit RECALL prompt if the app does not recreate it.

Prompts to test:

```text
What is SQLite?
```

```text
Can you explain what memory retrieval means?
```

```text
@recall what do you remember here?
```

Expected:

- No `.codex_memory` directory is created.
- Ordinary prompts produce no RECALL context injection.
- A normal RECALL mention in an unrecognized folder does not initialize memory.
- If Codex App auto-created `.git`, the folder is no longer unrecognized; an explicit RECALL mention may initialize project memory.
- The explicit initialization option is shown only when relevant.

Check:

```powershell
Test-Path "$scratch\.codex_memory"
```

Fail if:

- `.codex_memory` appears after ordinary prompts.
- RECALL silently activates an unrecognized folder.
- The plugin stores generic Q&A as project memory.

## Phase 3: Explicit Greenfield Initialization

Status: PASS. Covered by unattended hook/skill simulation; evidence in `quality_results\manual\manual_test_notes.md`.

In the same scratch folder, submit:

```text
@recall initialize this project
```

Expected:

- `.codex_memory` is created only in the scratch root.
- Config uses schema version 2.
- Activation is enabled and project-local.

Check:

```powershell
Get-Content "$scratch\.codex_memory\memory_config.json"
python C:\Users\Julius\source\repos\RECALL\plugins\recall\scripts\recall_skill.py --root $scratch activation-status
```

Fail if:

- Memory is created in a parent folder.
- Activation is global rather than project-local.
- Config defaults are missing: `capture_mode=standard`, `recall_mode=relevant`, `observability_mode=quiet`.

## Phase 4: Recognized Project Activation

Status: PASS. Covered by installed-cache fresh project E2E simulation; evidence in `quality_results\manual\manual_test_notes.md`.

Create a real project fixture:

```powershell
$project = "C:\Users\Julius\source\test_enviroments\RECALL\project"
Remove-Item -Recurse -Force $project -ErrorAction SilentlyContinue
New-Item -ItemType Directory $project | Out-Null
Set-Content "$project\pyproject.toml" "[project]`nname='recall-manual'`nversion='0.1.0'`n"
```

Open a fresh Codex App thread in `C:\Users\Julius\source\test_enviroments\RECALL\project`.

Submit:

```text
Use RECALL for this project. We must keep generated release notes under docs/manual-release-notes.md.
```

Expected:

- RECALL activates because the folder is a recognized project.
- A requirement memory is saved or queued for quiet finalization.
- A short confirmation may appear, for example `RECALL saved 1 memory.`
- No finalizer prompt is visible.

Check:

```powershell
python C:\Users\Julius\source\repos\RECALL\plugins\recall\scripts\recall_skill.py --root C:\Users\Julius\source\test_enviroments\RECALL\project review-memory --category requirements --limit 10
```

Fail if:

- `RECALL_FINALIZER_REQUEST` is visible.
- The assistant explains `apply-finalizer-batch`.
- Memory is stored outside `C:\Users\Julius\source\test_enviroments\RECALL\project\.codex_memory`.
- The requirement is stored as `commands` or generic `project_state`.

## Phase 5: Persistent Activation Across Prompts

Status: PASS. Covered by installed-cache fresh project E2E simulation; evidence in `quality_results\manual\manual_test_notes.md`.

In the same thread, do not mention RECALL.

Submit:

```text
Create the release notes file with a short placeholder.
```

Then run or ask Codex to run a simple verification command.

Expected:

- RECALL remains active without another mention.
- File edits and successful commands are buffered as evidence, not durable command memories.
- Stop finalization is quiet.
- Routine successful edits/builds do not become standalone durable memories.

Check:

```powershell
python C:\Users\Julius\source\repos\RECALL\plugins\recall\scripts\recall_skill.py --root C:\Users\Julius\source\test_enviroments\RECALL\project review-memory --category commands --limit 20
python C:\Users\Julius\source\repos\RECALL\plugins\recall\scripts\recall_skill.py --root C:\Users\Julius\source\test_enviroments\RECALL\project review-memory --category project_state --limit 20
```

Fail if:

- Successful file edits create durable `file_edit` records.
- Successful test/build commands create routine durable `build_result` or `test_result` records.
- The UI shows finalizer internals.

## Phase 6: New Session Retrieval

Status: PASS. Prior manual transcript confirmed release-notes retrieval; evidence in `quality_results\manual\manual_test_notes.md`.

Close the thread. Open a new Codex App thread in `C:\Users\Julius\source\test_enviroments\RECALL\project`.

Submit:

```text
What project-specific release notes requirement should I preserve?
```

Expected:

- Relevant context is retrieved without requiring another RECALL mention if the project is already active.
- The answer references the release notes requirement.
- It does not invent exact details that were never stored.

Then submit an unrelated prompt:

```text
Explain the difference between TCP and UDP.
```

Expected:

- RECALL should stay silent or not inject unrelated project context.

Fail if:

- New sessions forget activation.
- Unrelated prompts receive project memory.
- The answer fabricates exact file names or requirements.

## Phase 7: Retrieval Sufficiency And Honesty

Status: PASS. Prior manual transcript confirmed calibrated insufficiency for unknown deployment/database decisions; evidence in `quality_results\manual\manual_test_notes.md`.

Open or keep using a Codex App thread in:

```text
C:\Users\Julius\source\test_enviroments\RECALL\project
```

Ask explicit memory questions that should not be answerable from the current project memory:

```text
@recall What deployment provider did we choose for this project?
```

```text
@recall What database migration tool did we settle on?
```

Expected:

- RECALL says it does not contain enough relevant memory.
- The assistant does not guess.
- The answer may mention that the current memory only contains the release-notes requirement.
- No command is required for the answer unless you explicitly ask Codex to inspect files.

Fail if:

- It confidently answers from weak or unrelated memory.
- It blends stale, superseded, or archived records into the answer.
- It uses memories from `project2` or the RECALL source repo while the current UI directory is `project`.

## Phase 8: Failure Capture

Status: PASS after fix. Failure capture and conditional command capture were verified; evidence in `quality_results\manual\manual_test_notes.md`.

In the Codex App UI for:

```text
C:\Users\Julius\source\test_enviroments\RECALL\project
```

Ask Codex to intentionally run a failing command:

```text
Run this intentionally failing command so we can test RECALL failure capture: `python -m pytest tests\does_not_exist.py`
```

The actual shell command may be:

```text
python -m pytest tests\does_not_exist.py
```

Expected:

- Failure evidence is captured.
- A durable `debug_history` memory may be saved if the failure is future-useful.
- Secret-like content is redacted.
- The failed command is not saved as a reusable `commands` memory unless it becomes a verified useful command later.

Check:

```powershell
python C:\Users\Julius\source\repos\RECALL\plugins\recall\scripts\recall_skill.py --root C:\Users\Julius\source\test_enviroments\RECALL\project review-memory --category debug_history --limit 20
```

Fail if:

- Failures are ignored entirely.
- Raw secrets appear.
- The corpus fills with low-value command records.

## Phase 9: Reusable Command Capture

Status: PASS after fix. Conditional reusable command capture refused to save a failing command; evidence in `quality_results\manual\manual_test_notes.md`.

In the same UI project, ask Codex to establish a verified reusable command:

```text
The reusable validation command for this project is `python -m pytest`; remember it only if it actually works.
```

If that fixture has no pytest suite, use a command that actually passes in that project, such as a tiny Python syntax/import check or another project-local validation command. The important behavior is that RECALL should only save a command after it was verified as reusable.

Expected:

- Only verified reusable commands should land in `commands`.
- One command memory should contain the stable command and purpose.
- Routine one-off commands should remain evidence only.

Fail if:

- Every shell command becomes durable memory.
- Failed commands are saved as recommended commands.
- Commands lack purpose, working directory, or verification status.
- A command from the RECALL source repo is saved into the scratch project's memory.

## Phase 10: Conflict And Current Truth

Status: PASS after fix. Release-notes path correction supersession was verified; evidence in `quality_results\manual\manual_test_notes.md`.

Use `project2` for conflict testing so the main `project` fixture keeps its clean Phase 6/7 release-notes record:

```text
C:\Users\Julius\source\test_enviroments\RECALL\project2
```

In a Codex App thread for `project2`, store a requirement:

```text
@recall remember this: requirements: The release notes file must live at docs/manual-release-notes.md.
```

Then introduce a correction:

```text
Correction: the release notes file should instead live at docs/release/manual-notes.md.
```

Expected:

- Higher-trust correction supersedes or conflicts with the older requirement.
- Retrieval should not blend both as current truth.
- A quiet conflict alert is acceptable if equal-trust records cannot be resolved.

Check:

```powershell
python C:\Users\Julius\source\repos\RECALL\plugins\recall\scripts\recall_skill.py --root C:\Users\Julius\source\test_enviroments\RECALL\project2 review-memory --category requirements --limit 20
```

Fail if:

- Both requirements remain active with no alert.
- Retrieval presents both as simultaneously true.
- The correction is stored in the wrong category.

## Phase 11: Deactivation

Status: PASS. Deactivation preserved memory and stopped background behavior in simulation; evidence in `quality_results\manual\manual_test_notes.md`.

Use `project2` for deactivation testing unless you intentionally want to pause the main `project` fixture.

From an external terminal, run:

```powershell
python C:\Users\Julius\source\repos\RECALL\plugins\recall\scripts\recall_skill.py --root C:\Users\Julius\source\test_enviroments\RECALL\project2 deactivate-project
python C:\Users\Julius\source\repos\RECALL\plugins\recall\scripts\recall_skill.py --root C:\Users\Julius\source\test_enviroments\RECALL\project2 activation-status
```

In a new Codex App thread in `project2`, submit:

```text
What should we do next?
```

Expected:

- Existing memories remain on disk.
- Background retrieval and capture stop.
- No new automatic memories are created.

Fail if:

- Deactivation deletes memory.
- RECALL continues automatic retrieval or capture after deactivation.

Reactivate with:

```text
@recall continue for this project
```

## Phase 12: Quiet Mode UI Audit

Status: PASS. Quiet finalizer internals stayed hidden in installed-cache smoke and real Scalpel field use; raw prompt-plan memory capture was fixed before release.

This phase specifically targets the final-release UX in the Codex App.

In an active project, preferably `project`, perform several turns involving:

- File edits.
- Passing commands.
- Failing commands.
- Explicit requirements.
- Explicit corrections.
- A normal stop/end of turn.

Expected visible behavior:

- No `RECALL_FINALIZER_REQUEST`.
- No `apply-finalizer-batch`.
- No finalizer packet JSON.
- No assistant explanation of finalizer steps.
- At most a short status such as `RECALL saved 1 memory.`
- Hook cards in the UI should either be absent, compact, or show only user-meaningful status.

Fail if any finalizer implementation detail appears in normal quiet mode.

## Phase 13: Debug Mode Audit

Status: PASS. Debug trace behavior was verified by terminal simulation; evidence in `quality_results\manual\manual_test_notes.md`.

Enable debug mode only for development. Use `project2` so debug artifacts do not muddy the main fixture:

```powershell
python C:\Users\Julius\source\repos\RECALL\plugins\recall\scripts\recall_skill.py --root C:\Users\Julius\source\test_enviroments\RECALL\project2 configure-observability debug
```

Perform one active Codex App UI turn in `project2`.

Expected:

- Debug traces are written under `.codex_memory\runtime\debug`.
- Traces include root resolution, activation, retrieval gate decisions, capture decisions, and finalizer operations.
- Debug traces are redacted.
- Debug traces are not indexed as memories.
- Debug artifacts expire or are eligible for cleanup after seven days.

Return to quiet mode:

```powershell
python C:\Users\Julius\source\repos\RECALL\plugins\recall\scripts\recall_skill.py --root C:\Users\Julius\source\test_enviroments\RECALL\project2 configure-observability quiet
```

Fail if:

- Debug traces contain secrets.
- Debug traces are retrieved as project memory.
- Debug behavior leaks into quiet mode.

## Phase 14: Corpus Quality Audit

Status: PASS. Corpus review found no active automatic command-noise candidates in the manual fixtures; evidence in `quality_results\manual\manual_test_notes.md`.

Run category review for both UI fixtures from an external terminal:

```powershell
python C:\Users\Julius\source\repos\RECALL\plugins\recall\scripts\recall_skill.py --root C:\Users\Julius\source\test_enviroments\RECALL\project review-memory --limit 100
python C:\Users\Julius\source\repos\RECALL\plugins\recall\scripts\recall_skill.py --root C:\Users\Julius\source\test_enviroments\RECALL\project2 review-memory --limit 100
```

Audit the corpus manually:

- Requirements contain explicit obligations.
- Constraints contain hard rules.
- Decisions contain accepted choices, not speculation.
- Architecture contains stable structure and design rationale.
- Debug history contains durable failures, root causes, and fixes.
- Commands contain verified reusable commands only.
- Project state contains meaningful checkpoints, not every successful action.
- Risks and tasks are future-useful.
- Preferences are explicit or strongly corroborated.
- Session summaries exist only when compaction or continuity requires them.

Quantitative checks:

- Active automatic command-like records should be rare.
- No active routine `file_edit`, `build_result`, or `test_result` durable records.
- At least 80% of active records should be useful in a future session.
- Every current-truth record should have clear status and provenance.

Fail if:

- More than 20% of active records are command noise.
- Empty categories stay empty because capture rules miss real user intent.
- Project state becomes a log of routine successful actions.
- Memory content cannot answer why it exists.
- IDs restarting at `#1` in different projects are not a failure; memory IDs are project-local.

## Phase 15: Migration Audit

Status: PASS. Migration dry-run and apply on `migration-copy` preserved records and created a backup; evidence in `quality_results\manual\manual_test_notes.md`.

Use a copied project or backup corpus.

Do not run migration against the only copy of `project` or `project2`. First copy one fixture:

```powershell
$migration = "C:\Users\Julius\source\test_enviroments\RECALL\migration-copy"
Remove-Item -Recurse -Force $migration -ErrorAction SilentlyContinue
Copy-Item -Recurse C:\Users\Julius\source\test_enviroments\RECALL\project $migration
```

Dry run:

```powershell
python C:\Users\Julius\source\repos\RECALL\plugins\recall\scripts\recall_skill.py --root C:\Users\Julius\source\test_enviroments\RECALL\migration-copy migrate-corpus --dry-run
```

Apply only after reviewing:

```powershell
python C:\Users\Julius\source\repos\RECALL\plugins\recall\scripts\recall_skill.py --root C:\Users\Julius\source\test_enviroments\RECALL\migration-copy migrate-corpus --apply
```

Expected:

- A database backup is created before apply.
- No IDs or history are deleted.
- Useful automatic records are linked through `evidence_ids`, `merged_from`, or `superseded_by`.
- Noise records are archived, not destroyed.
- Latest score/checkpoint claims remain current.

Fail if:

- Migration deletes records.
- Useful source records are archived without replacement links.
- Active command noise remains after migration.
- Backups are missing or not restorable.

## Phase 16: Source-Blind Manual Evaluation

Status: PASS after fix. All three source-blind prompts were exercised through `codex exec` against the active fixture; evidence in `quality_results\manual\manual_test_notes.md`.

Use a fresh Codex App thread in:

```text
C:\Users\Julius\source\test_enviroments\RECALL\project
```

Ask the assistant to use only automatically provided RECALL memory, not source files or terminal commands.

Ask:

```text
Without running commands or reading source files, use only automatically provided RECALL memory: summarize this fixture project's current requirements and risks.
```

```text
Without running commands or reading source files, use only automatically provided RECALL memory: what are the current accepted requirements and constraints?
```

```text
Without running commands or reading source files, use only automatically provided RECALL memory: what should the next engineer do first?
```

Score each answer:

- 5: Accurate, specific, cites enough provenance, no fabrication.
- 4: Mostly accurate, minor omissions.
- 3: Useful but incomplete or slightly overconfident.
- 2: Contains important omissions or weak unsupported claims.
- 1: Misleading or fabricated.

Fail release readiness if:

- Any answer fabricates exact details.
- Average score is below 4.5.
- The agent cannot distinguish current, superseded, and uncertain memory.
- The answer silently pulls in RECALL source-repo memories while the UI directory is the scratch project.

## Phase 17: Installed-Plugin Fresh Project E2E

Status: PASS after fixes. Installed-cache E2E simulation covered activation, memory capture, failure capture, retrieval, deactivation, and debug traces; evidence in `quality_results\manual\manual_test_notes.md`.

Use this current fixture path for installed-plugin E2E:

```powershell
$fresh = "C:\Users\Julius\source\test_enviroments\RECALL\installed-e2e"
Remove-Item -Recurse -Force $fresh -ErrorAction SilentlyContinue
New-Item -ItemType Directory $fresh | Out-Null
Set-Content "$fresh\package.json" "{`"name`":`"recall-installed-e2e`",`"version`":`"0.1.0`"}"
```

In the Codex App, open a new thread in `C:\Users\Julius\source\test_enviroments\RECALL\installed-e2e`.

Manual scenario:

1. Ask an unrelated question. Confirm no `.codex_memory`.
2. Mention RECALL once with a real requirement. Confirm activation and memory creation.
3. Make a file edit without mentioning RECALL. Confirm background capture is active.
4. Run a passing command. Confirm no durable command spam.
5. Run a failing command. Confirm durable debug history if useful.
6. Open a new thread. Confirm relevant memory retrieval.
7. Deactivate. Confirm background behavior stops.
8. Re-enable debug. Confirm traces exist and are not indexed.
9. Return to quiet mode.

Fail if:

- Installed behavior differs from source behavior.
- New sessions lose activation.
- Quiet finalization is visible.
- Memory lands outside the project root.
- The Codex App sidebar/thread project path differs from the intended `installed-e2e` directory.

## Phase 18: Release Decision

Status: PASS. Release decision recorded in `docs\manual-release-notes.md`.

Release candidate is acceptable only if all are true:

- No accidental `.codex_memory` creation for ordinary prompts or unrecognized folders.
- One RECALL mention activates recognized projects persistently.
- New sessions retrieve relevant project context without repeated mentions.
- Insufficient memory produces honest uncertainty.
- Quiet mode never exposes finalizer internals.
- Debug mode gives useful traces without indexing them.
- Durable memory is semantic and future-useful.
- Active command noise is near zero.
- Migration is non-destructive and backed up.
- Installed-plugin behavior matches source behavior.
- Manual source-blind score is at least 90/100.

Open release blockers for:

- Any secret leak.
- Any user-visible finalizer internals in quiet mode.
- Any global activation or cross-project memory bleed.
- Any destructive migration behavior.
- Any confident fabricated answer from insufficient memory.
- Any recurring automatic command spam.

## Suggested Final Manual Report

Use this template in `quality_results\manual\manual_test_notes.md`:

```markdown
# RECALL Manual Test Report

Date:
Tester:
Codex version:
Plugin install source:
Commit:

## Summary

Decision: pass / fail / conditional

## Critical Findings

- Finding:
- Repro:
- Expected:
- Actual:
- Severity:
- Fix required:

## Memory Quality Metrics

- Active records:
- Active command records:
- Active routine file/build/test records:
- Categories with useful records:
- Categories empty but expected:
- Signal-to-noise estimate:

## UI/Hook Behavior

- Quiet finalizer hidden: yes/no
- Debug traces usable: yes/no
- Hook errors observed:

## Source-Blind Score

- Architecture/risk answer:
- Requirements/constraints answer:
- Next-work answer:
- Average:

## Release Blockers

- Blocker:
- Owner:
- Required evidence to close:
```
