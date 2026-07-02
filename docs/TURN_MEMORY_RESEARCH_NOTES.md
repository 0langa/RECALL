# RECALL Turn Memory Finalizer Guide

Date: 2026-06-09
Branch: `main`

This document merges:

- Local RECALL memory audit findings from this repository.
- Official Codex hook, plugin, memory, subagent, and non-interactive docs.
- The user-provided `codex with hooks.md` attachment.
- Comparison notes from Claude Code and Kimi Code hook systems.

## Executive Decision

RECALL should stop treating hook events as durable memories.

The target architecture is:

```text
UserPromptSubmit -> explicit memory only
PostToolUse      -> buffer compact evidence only
PreCompact       -> buffer or save only meaningful compaction checkpoints
Stop             -> if evidence is dirty, return decision:block once
Continuation     -> Codex performs one constrained memory-finalizer pass
Second Stop      -> stop_hook_active=true, mark finalized, exit cleanly
SessionStart     -> inject curated active memory only
```

The core product change is a new write boundary: durable memory should be created by a finalizer pass that has turn-level context, not by one hook record per command.

## Verified Codex Surface

Official source:

- https://developers.openai.com/codex/hooks

Relevant documented facts:

- Plugin-bundled hooks are loaded when a plugin is enabled and trusted.
- Hook commands receive JSON on stdin and run in the session `cwd`.
- Plugin hooks receive `PLUGIN_ROOT` and `PLUGIN_DATA`.
- Multiple matching hooks from multiple sources can run.
- Multiple command hooks for one event launch concurrently.
- `Stop` ignores matchers, so a configured Stop hook is global for that hook source.
- `timeout` is seconds; omitted timeout defaults to `600`.
- `commandWindows` exists for Windows commands.
- `async: true` is parsed but skipped today.
- Only hook handlers with `type: "command"` run today.
- Hook-native `type: "prompt"` and `type: "agent"` are parsed but skipped today.
- `Stop` expects JSON on stdout; plain text stdout is invalid.
- `Stop` input includes `turn_id`, `stop_hook_active`, and `last_assistant_message`.
- `Stop` can continue the turn with:

```json
{
  "decision": "block",
  "reason": "Run one more pass over the failing tests."
}
```

For `Stop`, `decision: "block"` does not reject the turn. Codex continues and creates a new continuation prompt using `reason` as prompt text.

This means the finalizer continuation design is not a hack. It is the documented Codex mechanism. The only part that still needs a live fixture is exact behavior in the currently installed local Codex build and UI, especially loop handling and hook trust after edits.

## Documentation Cross-Check

This section separates documented Codex behavior from RECALL engineering choices. The final plan must not blur those two.

| Plan claim | Status | Official documentation basis | Notes |
|---|---|---|---|
| Hooks can run custom scripts in the agent loop. | Confirmed | Codex Hooks says hooks inject scripts into the agentic loop for logging, prompt scanning, memory summaries, validation, and directory-specific prompting. | This supports using command hooks for RECALL lifecycle handling. |
| Hooks are enabled by default and can be disabled with `[features].hooks = false`. | Confirmed | Codex Hooks documents the canonical `hooks` feature key and the deprecated alias. | Good to keep in docs, but RECALL should not assume hooks always run. |
| Matching hooks from multiple sources all run. | Confirmed | Codex Hooks runtime behavior says matching hooks from multiple files all run. | RECALL hooks must be idempotent and cannot assume exclusivity. |
| Multiple command hooks for the same event run concurrently. | Confirmed | Codex Hooks says multiple matching command hooks for the same event launch concurrently. | RECALL needs locks/status files around finalizer requests. |
| Non-managed hooks, including plugin-bundled hooks, require trust review. | Confirmed | Codex Hooks and Build Plugins both state plugin-bundled hooks are non-managed and skipped until reviewed/trusted. | Release notes must mention retrusting hooks after hook edits. |
| Installed plugins can bundle hooks through `hooks/hooks.json`. | Confirmed | Codex Hooks and Build Plugins document default `hooks/hooks.json`; Build Plugins says no manifest `hooks` entry is needed for that default path. | RECALL's current package shape is correct. |
| Plugin hooks receive `PLUGIN_ROOT` and `PLUGIN_DATA`. | Confirmed | Build Plugins says plugin hook commands receive both env vars, with `PLUGIN_ROOT` pointing to the installed plugin root and `PLUGIN_DATA` to the writable data dir. | The guide should rely on these env vars instead of source checkout paths. |
| Hook commands run with the session `cwd`. | Confirmed | Codex Hooks config notes state commands run with the session `cwd`. | RECALL should resolve project memory from hook payload/session cwd, not from plugin root. |
| Only `type: "command"` handlers run today. | Confirmed | Codex Hooks says `prompt` and `agent` handlers are parsed but skipped; async command hooks are also skipped. | Do not build V1 around hook-native prompt/agent handlers. |
| `commandWindows` is supported. | Confirmed | Codex Hooks config notes document `commandWindows`; TOML accepts `command_windows` or `commandWindows`. | The existing Windows launcher shape is appropriate. |
| `timeout` is seconds, defaulting to `600` when omitted. | Confirmed | Codex Hooks config notes document timeout units and default. | RECALL hooks should use short explicit timeouts where possible. |
| `SessionStart` can inject `additionalContext`. | Confirmed | Codex Hooks documents `hookSpecificOutput.additionalContext` for `SessionStart`. | This supports curated memory injection. |
| `UserPromptSubmit` receives `prompt` and can add `additionalContext` or block. | Confirmed | Codex Hooks documents `prompt`, `additionalContext`, and `decision: "block"` for this event. | This supports explicit memory cue detection. |
| `PostToolUse` runs after Bash, `apply_patch`, and MCP tool output, including non-zero Bash exits. | Confirmed | Codex Hooks documents the event and supported tools. | This supports buffering failures and edits as evidence. |
| `PostToolUse` cannot undo side effects. | Confirmed | Codex Hooks explicitly states it cannot undo side effects from the tool that already ran. | Another reason durable memory should not be written here by default. |
| `PostToolUse` can provide `additionalContext`; `decision: "block"` replaces/feeds back tool result and continues. | Confirmed | Codex Hooks documents both behaviors. | RECALL should use this sparingly; buffering should normally stay silent. |
| `PreCompact` and `PostCompact` match `manual` or `auto`. | Confirmed | Codex Hooks matcher table and event sections document those trigger values. | Compaction checkpointing is supported but should be strict. |
| `Stop` ignores matcher. | Confirmed | Codex Hooks matcher table and Stop section say matcher is not used. | RECALL Stop hook is global once trusted and enabled. |
| `Stop` receives `turn_id`, `stop_hook_active`, and `last_assistant_message`. | Confirmed | Codex Hooks Stop section documents all three fields. | This is the key field set for a one-shot finalizer. |
| `Stop` expects JSON on stdout; plain text stdout is invalid. | Confirmed | Codex Hooks Stop section documents this. | Hook scripts must print JSON only. |
| `Stop` can return `decision: "block"` with `reason` to keep Codex going. | Confirmed | Codex Hooks Stop section documents this exact shape. | This supports the finalizer continuation mechanism. |
| `Stop decision:block` creates a new continuation prompt using `reason` as prompt text. | Confirmed | Codex Hooks says it acts as a new user prompt using `reason` as prompt text. | Strong support for the design. |
| A matching Stop hook returning `continue: false` takes precedence over continuation decisions. | Confirmed | Codex Hooks Stop section states this. | RECALL cannot guarantee continuation if another hook stops the turn. |
| Codex hard-stops after a fixed number of Stop blocks. | Not documented in OpenAI docs checked | Claude docs document a fixed limit, but OpenAI Codex Hooks docs do not state one. | Do not claim this for Codex. Use RECALL's own one-shot guard. |
| A Stop finalizer continuation will be invisible or UI-silent. | Not documented in OpenAI docs checked | Stop docs only say Codex creates a continuation prompt. | Assume it may be visible; keep finalizer prompt and summary concise. |
| A Stop finalizer continuation can write memory through `recall_skill.py`. | Plausible but requires E2E | Stop docs create a new prompt; normal Codex tool permissions should govern subsequent actions. | E2E must verify adapter writes under app/CLI permission modes. |
| `codex exec --ephemeral`, JSONL output, `--output-last-message`, and `--output-schema` exist. | Confirmed | Codex Non-interactive Mode documents those flags/outputs. | Nested `codex exec` remains optional; do not make it V1 default. |
| Built-in Codex memory updates in the background, skips active/short-lived sessions, redacts secrets, and stores under Codex home. | Confirmed | Codex Memories documents all of these. | This supports the policy shape, not RECALL's storage location. |
| Codex stores built-in memories under project `.codex_memory/`. | Disproved | Codex Memories says built-in memory lives under `~/.codex/memories/`. | RECALL's `.codex_memory/` storage is plugin-specific and local-first by design. |
| Codex only spawns subagents when explicitly asked and subagents consume more tokens. | Confirmed | Codex Subagents documents both points. | Do not require automatic subagents for every-turn memory. |
| Subagents inherit sandbox policy and Codex waits for requested results. | Confirmed | Codex Subagents documents inheritance and orchestration/waiting. | Useful for manual audits, not required for Stop finalizer. |
| RECALL's runtime buffer schema, memory-card schema, capture modes, and skill list are documented Codex behavior. | Not Codex behavior | These are RECALL design choices. | Keep them in the plan, but label them as implementation policy. |

Bottom line from the cross-check: the hook interaction the plan depends on is documented. The exact RECALL memory policy is not a Codex guarantee; it is an implementation design that should be validated with focused unit tests plus a live hook E2E before release.

## Current RECALL Finding

The live `.codex_memory` store in this repository was structurally healthy but semantically polluted:

- `649` total active memories.
- `621` memories from `post_tool_use`.
- `569` `commands` memories.
- `52` `debug_history` memories.
- `25` `project_state` memories.
- `646` generic or near-generic summaries, including `Bash result captured.`, `apply_patch result captured.`, `Session stop checkpoint.`, and `Result: completed`.
- `0` memories with lifecycle relationship metadata such as confirmed, superseded, archived, or merged.

Conclusion: this is an ingestion-policy failure, not a retrieval failure. Better search over junk is still junk. RECALL needs fewer and better writes.

## What Is Already Good

RECALL is not a bad foundation:

- The marketplace wrapper shape is correct.
- The installable plugin root is `plugins/recall/`.
- `.codex-plugin/plugin.json` is in the right place.
- `hooks/hooks.json` is discovered by Codex by default.
- Runtime storage is project-local under `.codex_memory/`.
- SQLite is the default backend, with JSONL support available.
- The vector index is rebuildable, not the source of truth.
- `scripts/recall_skill.py` is the right public action adapter.
- `scripts/memory_manager.py` is correctly internal backend plumbing.
- Lifecycle concepts already exist: active, open, resolved, superseded, stale, archived, confirm, merge, prune.
- SessionStart context injection is high-value when it injects curated active memory.
- The current docs already identify ingestion as the main problem.

## What Must Change

Replace durable writes from:

- `plugins/recall/hooks/scripts/post_tool_use.py`
- `plugins/recall/hooks/scripts/stop.py`

`PostToolUse` should never write durable command/debug memories by default. It should classify and buffer evidence.

`Stop` should not save generic `project_state` checkpoints. Its job is to decide whether a finalizer continuation is justified and, if so, create exactly one finalizer request.

Keep and improve:

- `prompt_inspector.py`: explicit user memory cues still save immediately.
- `session_start.py`: inject only curated memory; do not create `.codex_memory` just because a session started.
- `pre_compact.py`: save only meaningful compaction checkpoints or buffer compaction evidence for finalization.

Do not make V1 depend on:

- A mandatory local LLM runtime.
- Cloud services.
- Sentence-transformers, FAISS, or Chroma.
- Hook-native `agent` or `prompt` handlers.
- Automatic subagents for every turn.
- Nested `codex exec` inside hooks as the default path.

## Target Runtime State

Add runtime-only turn state:

```text
.codex_memory/
  runtime/
    turns/
      <session_id>/
        <turn_id>.jsonl
    finalizer_requests/
      <session_id>-<turn_id>.json
    locks/
      <session_id>-<turn_id>.lock
    quarantine/
```

Rules:

- Runtime state is never packaged.
- Runtime state is project-local.
- Runtime state is redacted before write.
- Runtime files are bounded and pruned.
- Corrupt runtime files are quarantined, not fatal to hooks.

## Turn Event Schema

Each buffered event should be small, finite, and already redacted:

```json
{
  "schema": "recall.turn_event.v1",
  "session_id": "string",
  "turn_id": "string",
  "event": "post_tool_use",
  "timestamp": "2026-06-09T15:42:00Z",
  "source": "PostToolUse",
  "tool_name": "Bash",
  "command": "python -m unittest discover -s tests",
  "exit_code": 0,
  "files": [],
  "signal": "test_pass",
  "summary": "Unit tests passed.",
  "details": "Compact supporting text only.",
  "durable_candidate": true,
  "importance_hint": 0.6,
  "tags": ["tests", "command"]
}
```

Allowed signal vocabulary should stay finite:

- `explicit_remember`
- `test_pass`
- `test_fail`
- `build_pass`
- `build_fail`
- `lint_pass`
- `lint_fail`
- `file_patch`
- `config_change`
- `release_check`
- `error_root_cause`
- `decision`
- `requirement`
- `risk`
- `generic_low_signal`

## Finalizer Request Schema

The Stop hook writes a compact request packet:

```json
{
  "schema": "recall.finalizer_request.v1",
  "session_id": "string",
  "turn_id": "string",
  "cwd": "C:\\path\\to\\project",
  "plugin_root": "C:\\Users\\...\\.codex\\plugins\\cache\\...\\recall",
  "adapter": "C:\\Users\\...\\recall\\scripts\\recall_skill.py",
  "transcript_path": "string-or-null",
  "last_assistant_message": "redacted and truncated",
  "candidate_count": 3,
  "candidate_summary": [
    {
      "signal": "test_pass",
      "summary": "Unit tests passed after hook command fix.",
      "tags": ["tests", "hooks"]
    }
  ],
  "policy": {
    "max_new_cards": 5,
    "prefer_lifecycle_updates": true,
    "write_scope": ".codex_memory only",
    "network": "not required"
  }
}
```

Do not copy the whole transcript into the packet. `transcript_path` is a convenience path, not a stable API, so any transcript parsing must be defensive.

## Stop Hook Rules

The first Stop hook may return `decision: "block"` only when all are true:

- `stop_hook_active` is false.
- A dirty buffer exists for `session_id` plus `turn_id`.
- No finalizer request is already marked requested or finalized.
- Evidence includes a durable signal: explicit memory, requirement, decision, risk, architecture, verified tests/build/release, file edits, failure/root cause/fix, or meaningful project state.

Return `{"continue": true}` when:

- `stop_hook_active` is true.
- The buffer is empty.
- Only low-signal commands occurred.
- A finalizer request already completed.
- A loop guard or lock is present.
- The request packet cannot be created safely.

Never block repeatedly. One continuation request per turn is the hard limit.

## Finalizer Prompt

The Stop hook should keep stdout JSON small. The detailed context lives in the finalizer packet. The `reason` should be deterministic:

```text
RECALL_FINALIZER_REQUEST

Codex must run one memory-finalization pass before ending this turn.

Read this local RECALL finalizer packet:
<absolute path>

Constraints:
- Do not edit project source files.
- Only write RECALL memory through the adapter path listed in the packet.
- Store nothing if no durable memory is justified.
- Prefer updating, confirming, superseding, merging, resolving, or pruning existing memories over creating duplicates.
- Store at most 5 new memory cards.
- Do not store secrets, credentials, tokens, private keys, passwords, or sensitive personal data.
- Keep cards future-useful: decision, requirement, risk, command, architecture, lesson learned, or project state.
- End after the memory pass; do not continue normal implementation work.

Required workflow:
1. Read the packet.
2. Review relevant existing memories using the packet adapter.
3. Decide whether any durable memory update is needed.
4. Apply the smallest useful memory changes through the adapter.
5. Reply with a short finalization summary.
```

## Durable Write Criteria

The finalizer should write memory only if it passes at least one criterion:

- It changes how future agents should work in this repo.
- It records an explicit user requirement or acceptance criterion.
- It records a decision and rationale.
- It records a verified command future agents should reuse.
- It records a non-obvious failure, root cause, and fix.
- It records a known risk or fragile area.
- It updates project state that matters across sessions.
- It supersedes, confirms, resolves, merges, or archives an older memory.

It should not write:

- A transcript summary just because a turn ended.
- A command result that is obvious or one-off.
- A generic assistant-response recap.
- A duplicate of an active memory.
- A successful read/list/status command.
- Raw stdout/stderr.

## Memory Card Standard

All durable cards should conform to this standard:

```text
content: concise human-readable memory
metadata.summary: one sentence
metadata.details: short supporting context
metadata.tags: lowercase stable tags
metadata.source: prompt_inspector | finalizer | pre_compact | skill | manual
metadata.status: active | open | resolved | superseded | stale | archived
metadata.importance: 0.0 to 1.0
metadata.confidence: 0.0 to 1.0
```

Recommended categories:

- `project_state`
- `architecture`
- `commands`
- `lessons_learned`
- `requirements`
- `risks`
- `debug_history`
- `constraints`
- `decisions`
- `preferences`
- `tasks`
- `session_summaries`

## Capture Modes

Add project-level capture modes:

- `off`: no automatic writes; explicit skill/manual saves only.
- `manual`: explicit user memory cues and explicit skill/manual saves only.
- `minimal`: explicit cues, failures, durable milestones, and meaningful finalizer cards.
- `standard`: minimal plus carefully gated edit/build/test summaries.

Default should be `minimal`, with `manual` available for users who want no automatic finalizer writes.

## Public Skill Surface To Add Or Improve

RECALL should give the user real control. Aim for at least these skills:

- `retrieve-memory`: search active memory with status/category filters.
- `save-insight`: manually save a structured memory card.
- `save-turn-card`: finalizer-facing save path with schema validation.
- `review-memory`: inspect current memory quality and lifecycle state.
- `audit-memory`: summarize source/category/status/noise distribution.
- `archive-noise`: dry-run/apply archive of low-value automatic records.
- `edit-memory`: correct content or metadata.
- `delete-memory`: explicit destructive delete with confirmation semantics, separate from archive.
- `confirm-memory`: mark a memory as verified.
- `supersede-memory`: replace stale or incorrect memory.
- `merge-memories`: merge duplicates.
- `resolve-memory`: close open task/risk/debug memories.
- `configure-recall`: set capture mode and retention policy.

The automatic finalizer should prefer lifecycle operations over creating duplicates.

## Implementation Plan

### Phase 1: Runtime buffer

- Add `scripts/turn_buffer.py`.
- Add atomic runtime writes and bounded cleanup.
- Add redaction before every runtime write.
- Add tests for append, load, dirty detection, malformed row quarantine, and packet creation.

### Phase 2: PostToolUse becomes evidence-only

- Replace durable writes in `post_tool_use.py` with event classification and buffering.
- Ignore successful read/list/status commands.
- Buffer failures, patches, tests, builds, releases, commits, pushes, installs, and explicit durable signals.
- Verify PostToolUse alone creates zero durable memory rows.

### Phase 3: Stop finalizer gate

- Replace direct Stop checkpoint writes with finalizer request creation.
- Return `decision: "block"` once when dirty.
- Mark requested/finalized with a lock or status file.
- On `stop_hook_active: true`, mark finalized and return `{"continue": true}`.
- Add `scripts/finalizer_prompt.py`.

### Phase 4: Finalizer adapter support

- Add or extend `save-turn-card` in `recall_skill.py`.
- Validate schema before storage.
- Enforce `max_new_cards`.
- Prefer confirm/supersede/merge/resolve/archive when relevant.
- Reject secrets and generic summaries.

### Phase 5: Prompt inspector upgrade

- Keep explicit direct saves.
- Support syntax like `remember as requirements: ...`, `remember risk: ...`, `remember decision: ...`, and `remember command: ...`.
- Do not treat incidental words like `remembered` as explicit cues.
- Store structured metadata, not just `{"source":"prompt_inspector"}`.

### Phase 6: Legacy cleanup

- Add `audit-memory`.
- Add `archive-noise --dry-run`.
- Add `archive-noise --apply`.
- Archive low-signal automatic records non-destructively.

### Phase 7: Optional typed MCP

Only after the finalizer is stable, consider a stdio MCP server exposing typed recall operations. Keep `recall_skill.py` as fallback and test surface.

## Tests To Add Or Change

Add `tests/test_turn_buffer.py`:

- Runtime dirs are created under temp project.
- Events append atomically.
- Malformed rows are skipped or quarantined.
- Dirty false for low-signal events.
- Dirty true for requirements, decisions, tests, errors, patches, releases.
- Finalizer packet is bounded.
- Requested/finalized status works.

Change `tests/test_hooks.py`:

- Empty Stop returns `{"continue": true}`.
- Dirty Stop with `stop_hook_active: false` returns `decision: "block"` and `RECALL_FINALIZER_REQUEST`.
- Dirty Stop with `stop_hook_active: true` returns `{"continue": true}` and marks finalized.
- Already requested finalizer does not request again.
- Stop output is always valid JSON.

Change PostToolUse tests:

- Successful high-signal test command buffers but does not create durable memory.
- Failed command buffers compact failure details.
- `apply_patch` buffers changed file targets.
- Low-signal listing command is ignored.
- Redaction happens before buffer write.

Change prompt inspector tests:

- `remember:` saves structured metadata.
- Incidental `remembered` does not save.
- Category syntax stores in the requested category.

Add finalizer prompt tests:

- Prompt includes packet path.
- Prompt forbids project source edits.
- Prompt caps new cards.
- Prompt tells Codex to prefer lifecycle updates.
- Prompt includes stable `RECALL_FINALIZER_REQUEST` marker.

## E2E Gate

Before making the Stop finalizer the default release behavior, run a live fixture:

1. Trust the updated RECALL hooks.
2. Simulate 100 read-only commands and verify zero durable records.
3. Simulate an edit plus tests and verify exactly one finalizer continuation.
4. Verify the second Stop sees `stop_hook_active: true` and exits.
5. Verify no finalizer loop after failed or invalid memory writes.
6. Verify `.codex_memory/runtime/` is not packaged.
7. Verify SessionStart still injects curated active memory.
8. Verify legacy noisy records can be archived, not deleted.

### Quick Noninteractive Probe

On 2026-06-09, a quick isolated `codex exec` probe was attempted with:

- `codex-cli 0.135.0`
- temporary `CODEX_HOME`
- copied auth only
- `config.toml` and then `hooks.json`
- `--dangerously-bypass-hook-trust`
- `--json`
- a harmless `SessionStart` logger and a one-shot `Stop decision:block` logger

Result: neither `SessionStart` nor `Stop` hooks ran in that noninteractive fixture. The JSONL stream only showed the warning that hook-trust bypass was enabled and the normal agent response.

After the user confirmed hooks had been disabled on their side and re-enabled them, the probe was rerun with the same temporary `CODEX_HOME` path and then with project-local `.codex/hooks.json` plus normal auth and `--ignore-user-config --enable hooks`. Both reruns still produced no hook invocation logs. This does not disprove the documented Stop continuation behavior; it means this quick `codex exec` setup did not exercise hooks and must not be used as proof of UI visibility.

The visibility question still needs an interactive CLI or Codex app fixture with trusted hooks.

### First Implementation Slice

Implemented on 2026-06-09:

- Added runtime-only turn evidence buffering in `scripts/turn_buffer.py`.
- Added deterministic finalizer prompt construction in `scripts/finalizer_prompt.py`.
- Changed `PostToolUse` from durable writes to evidence buffering for durable candidates.
- Successful read/list/status commands are ignored before storage.
- Changed `Stop` from direct `project_state` checkpoint writes to a one-shot `RECALL_FINALIZER_REQUEST`.
- `Stop` marks finalizer requests finalized when `stop_hook_active` is true.
- `Stop` fails open with valid JSON instead of breaking the user turn.
- Hook status text now says `Observing RECALL memory candidates` and `Checking RECALL finalization` instead of claiming a save.
- Smoke now asserts `PostToolUse` buffers evidence and `Stop` requests a finalizer for dirty evidence.
- Added the public `save-turn-card` adapter in `scripts/recall_skill.py` for finalizer-written structured cards.
- `save-turn-card` accepts JSON from `--file` or `--stdin`, validates required fields, rejects secret-like text, and stores cards with `recall.turn_card.v1` metadata.
- Finalizer request packets now list `save-turn-card` plus lifecycle commands as the allowed write/update surface.
- Historical note: an earlier design proposed separate discoverable skills for `save-turn-card`, lifecycle, edit, delete, and health operations.
- Current shipped surface after the hygiene update: the plugin exposes seven public skill folders (`using-recall`, `retrieve-memory`, `save-insight`, `review-memory`, `manage-memory`, `define-category`, and `memory-hygiene`). Lifecycle, edit/delete, finalizer, cleanup, and health operations are adapter commands grouped under `manage-memory`, `memory-hygiene`, or internal hook/finalizer workflows.
- Moved this internal research guide to repo-level `docs/` so it remains available without bloating the installable plugin package.

Verification run:

- `python -m unittest plugins.recall.tests.test_hooks -v` passed 18 tests.
- `python -m unittest plugins.recall.tests.test_recall_skill plugins.recall.tests.test_hooks -v` passed 25 tests.
- `python -m unittest discover -s tests -v` passed 77 tests from `plugins/recall`.
- `python scripts/smoke_recall.py --json` passed.
- Plugin-creator validation against `.\plugins\recall` passed.
- `.\build_plugin.ps1` passed plugin validation, smoke, package inspection, zip build, and unit tests.
- Plugin-eval still scored `77/100`; current top issue remains deferred token budget, not this hook path.

Remaining live E2E:

- Trust the updated hooks in the Codex app after reinstall.
- Confirm the visible Stop hook no longer exits with code `1`.
- Confirm the continuation prompt visibility/noise profile in the app.
- Confirm the finalizer can write through `recall_skill.py` during the Stop continuation under normal app permissions.

## Validation Commands

From repo root:

```powershell
.\build_plugin.ps1
```

From plugin root:

```powershell
cd .\plugins\recall
python -m unittest discover -s tests -v
python .\scripts\smoke_recall.py --json
.\build_plugin.ps1
```

For hook ingestion changes, also run when present:

```powershell
python RECALL_quality_suite\perf\benchmark_recall_memory.py --plugin-root plugins\recall --records 120 --queries 10
python RECALL_quality_suite\scripts\run_recall_quality_suite.py --repo-root .
```

## AGENTS.md Policy To Add

Add a short repo guidance section after implementation:

```text
## RECALL Hook Memory Policy

Hooks may observe and buffer candidate memory, but PostToolUse and Stop must not write durable memory by default.

Durable memory writes are allowed immediately only for explicit user memory/category actions or explicit lifecycle/review commands. End-of-turn synthesis happens through the Stop-hook finalizer continuation. The first Stop may return decision:block with a RECALL_FINALIZER_REQUEST; the second Stop must exit cleanly when stop_hook_active is true.

Keep runtime candidate data under .codex_memory/runtime/. Do not package runtime memory. Do not store secrets. Prefer lifecycle updates over duplicate records.
```

## Final Recommendation

Make Stop-continuation finalization the main design. Keep deterministic fallbacks for no-op, invalid, or unsafe cases, but do not settle for direct `PostToolUse` or direct `Stop` durable writes.

The future RECALL loop should feel like this:

```text
Hooks observe.
Codex synthesizes once.
RECALL validates and stores.
Lifecycle tools keep memory clean.
SessionStart injects only the useful active layer.
```

That is the path out of hook noise and toward memory that actually helps the next agent drive.
