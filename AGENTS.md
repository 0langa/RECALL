# AGENTS.md

Guidance for agents working in this repository.

## Repository Shape

This repository is a Codex plugin marketplace wrapper. The installable plugin lives in:

```text
plugins/recall/
```

The repo-root marketplace file is:

```text
.agents/plugins/marketplace.json
```

Do not treat the repository root as the plugin root for code changes unless you are editing wrapper scripts, marketplace metadata, or repository-level docs.

## Current Product Direction

RECALL is a local-first Codex plugin for project memory. It stores project-local data under:

```text
.codex_memory/
```

Core architecture decisions:

- Keep V1 stdlib-only and local-first.
- Do not add cloud services, local LLM runtimes, sentence-transformers, FAISS, or Chroma unless a later plan explicitly changes that.
- Storage is the source of truth; the vector index is rebuildable.
- Public workflow surface is skills/hooks plus `scripts/recall_skill.py`.
- `scripts/memory_manager.py` is internal backend and support plumbing.
- Runtime memory data must never be packaged into release artifacts.
- Hook output must use Codex `hookSpecificOutput.additionalContext` when injecting context.
- Secrets must be redacted before storage.

## Before Starting Work

Run from the repo root:

```powershell
git status --short --branch
```

Read these files before assuming what is missing:

```text
plugins/recall/docs/RECALL_V1_COMPLETION_PLAN.md
plugins/recall/docs/E2E_VERIFICATION_LOG.md
plugins/recall/docs/RELEASE_CHECKLIST.md
plugins/recall/docs/MEMORY_LIFECYCLE_REVIEW_PLAN.md
plugins/recall/docs/MEMORY_QUALITY_INGESTION_AUDIT_AND_PLAN.md
plugins/recall/CHANGELOG.md
plugins/recall/.codex-plugin/plugin.json
```

If making changes, create a `cdx/...` branch unless the user explicitly asks to work on another branch.

## Known Local Worktree Noise

At the time this file was added, the worktree had pre-existing local items that should not be disturbed unless the user asks:

```text
deleted: RECALL_Design_and_Development_Plan.md
untracked: DO NOT INCLUDE.rar
untracked: RECALL_quality_suite/
```

Do not inspect or extract `DO NOT INCLUDE.rar`.

## Common Commands

From the repo root:

```powershell
.\build_plugin.ps1
```

From the plugin root:

```powershell
cd .\plugins\recall
python -m unittest discover -s tests
python .\scripts\smoke_recall.py --json
.\build_plugin.ps1
```

Validate the plugin manifest with the local `plugin-creator` validator when available:

```powershell
python C:\Users\juliu\.codex\skills\.system\plugin-creator\scripts\validate_plugin.py .\plugins\recall
```

Run built-zip marketplace smoke:

```powershell
cd .\plugins\recall
python .\scripts\smoke_zip_marketplace.py --json
```

## PowerShell On Windows

This repository is actively developed on Windows with PowerShell as the shell. Treat PowerShell as its own runtime, not as `bash` with different path separators.

General references worth remembering:

- https://myitforum.substack.com/p/common-mistakes-in-powershell-and
- https://powershell.howtos.io/troubleshooting-common-powershell-errors/

### First Rule: Check Real Status, Not Color

Codex may show red text for stderr or PowerShell error streams even when the command ultimately succeeds. Do not infer failure from color alone.

For native executables such as `python`, `git`, `node`, `codex`, or `gh`, check `$LASTEXITCODE` immediately after the command:

```powershell
python -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) { throw "tests failed with exit code $LASTEXITCODE" }
```

For PowerShell cmdlets, check errors with terminating behavior when correctness matters:

```powershell
$ErrorActionPreference = 'Stop'
try {
    Get-Content -LiteralPath '.\plugins\recall\README.md'
} catch {
    throw "Failed to read README: $_"
}
```

Know the difference:

- `$LASTEXITCODE` is for the most recent native executable.
- `$?` is PowerShell's success flag for the last pipeline, and can be reset by later commands.
- `$ErrorActionPreference = 'Stop'` helps cmdlets throw terminating errors, but it does not make native executables throw.
- Red stderr can be diagnostic output, not failure. Pair it with exit code and expected artifacts.

### RECALL-Specific PowerShell Pitfalls Already Seen

- Do not use `%PLUGIN_ROOT%` in PowerShell hook commands. That is `cmd.exe` syntax and caused earlier Codex hook exits with code `1`.
- In `hooks/hooks.json`, keep Windows hook commands in the Python-launcher shape that reads `PLUGIN_ROOT` through `os.environ`, adds the hook script directory to `sys.path`, and runs the script with `runpy`.
- Direct hook scripts may pass when manifest hook commands fail. If hook UI is red, test both the direct script and the exact `commandWindows` form.
- PowerShell red text in the Codex chat can come from stderr or error-like output even when the process completed. Verify with exit code, hook output JSON, and `.codex_memory` health.
- The current noisy-memory issue is not the same as hook failure. Hooks can succeed while writing too many low-value `post_tool_use` records.

### Do Not Translate Windows Tasks Into Bash

If the user gives Windows paths, PowerShell variables, or PowerShell cmdlets, answer and run the task in PowerShell unless the user explicitly asks for Bash.

Bad signs:

- Rewriting `C:\app\logs` as `/c/app/logs`.
- Using `grep`, `cat`, `awk`, or `curl` when PowerShell has a native cmdlet.
- Parsing JSON with Python when `ConvertFrom-Json` is enough.
- Saving a `.sh` file for a task that was clearly Windows-native.
- Treating a throwaway prompt as permission to change shell/runtime.

For a Windows log-check task, prefer this shape:

```powershell
$ErrorActionPreference = 'Stop'

$backupDir = Join-Path $env:USERPROFILE 'logs_backup'
if (-not (Test-Path -LiteralPath $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir | Out-Null
}

$logFiles = @(
    Get-ChildItem -Path 'C:\app\logs' -Filter '*.log' -File -ErrorAction SilentlyContinue |
        Select-String -Pattern 'FATAL' -SimpleMatch
)

if ($logFiles.Count -gt 0) {
    Add-Content -Path (Join-Path $backupDir 'status.txt') -Value "$([DateTime]::Now) - Logs checked successfully"
} else {
    Write-Output 'Check failed'
}

$jsonFile = Join-Path $backupDir 'status.json'
Invoke-RestMethod -Uri 'https://internal.local' -OutFile $jsonFile -ErrorAction SilentlyContinue

if (Test-Path -LiteralPath $jsonFile) {
    $version = (Get-Content -LiteralPath $jsonFile | ConvertFrom-Json).version
    Write-Output $version
}
```

PowerShell 7 supports `&&` and `||`, but use them as PowerShell pipeline-chain operators, not as an excuse to write Bash-shaped scripts. In committed scripts and troubleshooting docs, prefer `if`, `try`/`catch`, and explicit exit-code checks when clarity matters.

When success means "matches were found," check the resulting collection. When success means "the command completed," use `try`/`catch` or `$?` immediately after the pipeline.

### Paths, Quoting, And Literals

Prefer `-LiteralPath` for paths from git, file listings, plugin cache directories, or user-provided strings:

```powershell
Get-Content -LiteralPath 'C:\Users\juliu\source\repos\RECALL\AGENTS.md'
```

Use single quotes for literal strings and double quotes only when variable interpolation is required:

```powershell
$root = 'C:\Users\juliu\source\repos\RECALL'
Write-Output "Repo root: $root"
```

Avoid mixing slash styles in the same command when a tool is path-sensitive. Python usually accepts `/`, PowerShell-native paths are clearer with `\`.

Use `Join-Path` for computed paths:

```powershell
$pluginRoot = Join-Path (Get-Location) 'plugins\recall'
```

### Pipelines Pass Objects

PowerShell pipelines pass objects, not plain text. Do not write filters as if this were `grep`/`awk`.

Use comparison operators such as `-eq`, `-ne`, `-like`, and `-match`:

```powershell
Get-ChildItem -Force | Where-Object { $_.Name -eq 'plugins' }
```

Inspect object shape with:

```powershell
Get-ChildItem | Get-Member
```

Avoid formatting before data processing. `Format-Table` is for humans at the end of a pipeline, not for data that another command must parse.

### Avoid Aliases In Scripts And Docs

Interactive aliases are fine for quick exploration, but committed scripts and documented commands should use full cmdlet names:

- Use `Get-ChildItem`, not `dir` or `ls`.
- Use `ForEach-Object`, not `%`.
- Use `Where-Object`, not `?`.
- Use `Select-Object`, not `select`.

This keeps commands readable for agents and portable across PowerShell versions.

### Safer File Operations

For recursive delete or move operations, resolve and verify the absolute path first. Never delete a computed path unless it is exactly under the intended workspace or explicitly named target.

```powershell
$target = Resolve-Path -LiteralPath '.\quality_results'
if ($target.Path -ne 'C:\Users\juliu\source\repos\RECALL\quality_results') {
    throw "Unexpected target: $($target.Path)"
}
Remove-Item -LiteralPath $target.Path -Recurse -Force
```

Do not pipe paths from PowerShell into `cmd /c del`, `bash rm`, or another shell for destructive work. Use one shell end to end, preferably native PowerShell cmdlets with `-LiteralPath`.

### Command Composition

Prefer one clear command per tool call when the result matters. If multiple steps must run together, fail explicitly after each native executable:

```powershell
git add -- AGENTS.md
if ($LASTEXITCODE -ne 0) { throw "git add failed" }
git diff --cached --stat
if ($LASTEXITCODE -ne 0) { throw "git diff failed" }
```

Avoid long semicolon chains for validation because they can hide which step failed and can create noisy RECALL hook records.

### Execution Policy And Scripts

If a `.ps1` script will not run, check execution policy before changing code:

```powershell
Get-ExecutionPolicy -List
```

Prefer fixing the invocation or trust issue over weakening system policy. If a one-off bypass is needed for local validation, keep it scoped to that process:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_plugin.ps1
```

### Troubleshooting Checklist

When PowerShell output looks like a failure:

1. Check the command's actual exit code or returned JSON.
2. Distinguish cmdlet errors from native executable stderr.
3. Re-run the smallest failing command without unrelated pipeline steps.
4. Verify paths with `Test-Path` or `Resolve-Path -LiteralPath`.
5. Check dependencies with explicit version commands such as `python --version`, `py -3 --version`, `node --version`, or `codex --version`.
6. For hooks, test direct script execution and then the manifest `commandWindows` shape.
7. Record the real failure mode in docs or tests once fixed.

## Performance Checks

Performance matters because hooks may run frequently and memory stores can grow quickly.

A recent quick benchmark on 2026-06-09 passed with:

- `120` records
- `10` queries
- average query about `48 ms`
- p95 query about `60 ms`
- rebuild about `0.24 s`
- seed/write about `5.8 s`

The seed/write path is the weak spot. Prefer cheap ingestion gates that reject low-value hook events before storage, index append, or duplicate scans.

When touching hook ingestion, write policy, storage, retrieval, or index behavior, run at least:

```powershell
python RECALL_quality_suite\perf\benchmark_recall_memory.py --plugin-root plugins\recall --records 120 --queries 10
```

For release or larger policy changes, also run the full quality suite if `RECALL_quality_suite/` is present:

```powershell
python RECALL_quality_suite\scripts\run_recall_quality_suite.py --repo-root .
```

## Memory Quality Rules

The current priority is reducing automatic hook noise without losing valuable project memory.

Important current finding:

- Live memory inventory showed hundreds of `post_tool_use` command records and only a small number of meaningful project-state records.
- This is an ingestion-policy problem first, not a retrieval problem.

When changing hooks:

- Default-deny low-value `PostToolUse` writes.
- Ignore successful read-only exploration commands such as `Get-Content`, `rg`, `git status`, directory listings, and memory review commands.
- Always preserve explicit user memory cues.
- Preserve failures, actionable debugging history, build/test/release milestones, and real file-edit summaries.
- Do not store generic summaries like `Bash result captured.` as durable active memory.
- Do not turn greetings, one-word replies, or unrelated explanations into `project_state`.
- Prefer non-destructive archival over deletion for cleanup.

## Testing Expectations

For narrow docs-only changes, inspect the diff and run targeted checks if relevant.

For plugin code changes, run:

```powershell
cd .\plugins\recall
python -m unittest discover -s tests
python .\scripts\smoke_recall.py --json
```

For hook behavior changes, include tests under:

```text
plugins/recall/tests/test_hooks.py
plugins/recall/tests/test_write_policy.py
plugins/recall/tests/test_memory_hygiene.py
```

For retrieval or memory-quality changes, include tests under:

```text
plugins/recall/tests/test_retrieval_quality.py
plugins/recall/tests/test_memory_review.py
```

If `RECALL_quality_suite/` is present, add or update contract tests there when changing public behavior.

## Packaging Rules

Release artifacts must not include:

- `.codex_memory/`
- `__pycache__/`
- `.pyc`
- `.git/`
- personal paths
- secret-like strings

The build scripts and package inspector are expected to enforce this. Do not commit `dist/recall.zip`; attach it to releases instead.

## Git Discipline

Do not revert user changes or unrelated local changes.

Before committing, stage only the files owned by the current task. After staging, verify:

```powershell
git diff --cached --stat
```

Use focused commit messages, for example:

```text
docs: add agent guidance
fix: tighten recall hook ingestion policy
test: cover noisy hook suppression
```
