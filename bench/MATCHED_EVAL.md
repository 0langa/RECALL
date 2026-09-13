# Matched behavior evidence

This offline controller makes no model/API call, installs no plugin, and changes
no live store. Unit tests prove harness mechanisms only. Actual subject trials
and host access controls belong to the controller. The strict light benchmark
and `baselines/v1.3.0.json` remain separate and unchanged.

The matrix has five Task 13 families and four arms. Its fixture is
`matched_tasks/tasks.json`. That file contains **private judge material**. Never
mount the bench repo, fixture, evidence root or controller conversation in a
subject session. A subject gets its workspace and only the current phase prompt.
The task prompt is necessarily visible; judge/controller prompts are not.

## Prepare

Use a clean committed candidate and the exact release ZIP. The harness freezes
the full commit, fixture hash, ZIP hash when present, Python/OS/Git versions,
host name/version, and requested model. Source or ZIP drift blocks further starts.
A missing ZIP hash stays `null` and cannot pass release proof. Start a new matrix
after a build or candidate change; never amend the frozen identity.

Create controller files `host.json` with the observed host `name` and `version`,
and `models.json` mapping `candidate`, `memory_off`, `docs_only`, `native_memory`
to the same exact model name. Do not use an unverified alias as observed identity.

```powershell
python bench/run_matched_eval.py prepare --repo C:/path/to/clean-candidate --commit FULL_40_CHARACTER_SHA --zip C:/path/to/recall.zip --host C:/controller/host.json --models C:/controller/models.json --evidence C:/trial-01/evidence --subjects C:/trial-01/subjects
python bench/run_matched_eval.py begin --evidence C:/trial-01/evidence --family recurring_failure --arm memory_off
python bench/run_matched_eval.py subject-input --evidence C:/trial-01/evidence --attempt recurring_failure--memory_off--1 --phase setup
```

Both roots must be new and disjoint from each other and the repo. `begin` creates
a fresh workspace with empty `.recall`, `.native-memory`, and `.host` directories.
Its `launch.json` stays in controller evidence. It records policies, initial file
hashes and identity. Do not send it to the subject. The harness never deletes a
store or replaces an attempt. A fixture cannot populate a store/config directory.

## Run the host

Use one controller process and one active attempt. For each family run memory
off, docs only, native memory, then candidate. Thus the candidate judge can cite
already retained controls. A passed case cannot be rerun. A failed/unclear case
gets at most one rerun with fresh stores and all setup repeated. P0/P1 halts new
attempts, including reruns. A product fix requires a new frozen matrix.

| Arm | RECALL | Native memory | Generated history doc |
| --- | --- | --- | --- |
| candidate | exact frozen ZIP | disabled | absent |
| memory_off | disabled | disabled | absent |
| docs_only | disabled | disabled | present |
| native_memory | disabled | enabled | absent |

Run the **same setup prompts in all arms**. Candidate/native can retain synthetic
history through their enabled memory. Memory off loses context at the next fresh
session. Docs only gets the same history in `docs/project-history.md`. Common
source files and task prompts match across arms.

Verify that setup does not create history notes outside the enabled memory
backend. For memory-off, make setup project files read-only and disable all
durable memory paths. A history note smuggled into a control workspace breaks
the arm policy and must not receive a verified policy attestation.

For each `new_session` phase start a new conversation without transcript carryover.
Keep only that attempt's project/store and isolated host configuration. For
`interrupted_task`, actually stop setup after its response, record the
interruption, and start a distinct resume session. The resume prompt omits the
old requirement. Preserve a control's honest missing-requirement result.

Enforce workspace-only filesystem access in the host sandbox. Disable inherited
global memory, prior sessions, unrelated plugins and controller context. Native
memory must use that attempt's isolated host directory. Confirm the actual paths.
Directory separation alone is **not access-control proof**. An unsupported or
unverified boundary makes the attempt unknown. Never use a user's memory store.

For `no_memory`, setup can write history. The task phase must have zero RECALL
reads/writes across SessionStart, prompt, tools, Stop and finalizers. Instrument
all paths before task startup. A transcript without read/write instrumentation
cannot prove zero access.

## Retain evidence

Retain the full original host exports, including failed calls, all tool arguments
and results, messages, session IDs, identity and usage. Combine all phase exports
in one raw file/archive without dropping bytes. The harness copies it as
`raw-trace.bin`, plus a normalized `trace.jsonl`, `observation.json`, and private
`assessment.json`. Originals stay outside the subject workspace.

Every normalized event has `seq` starting at 1 without gaps, plus `attempt_id`.

| kind | Additional fields |
| --- | --- |
| `run_start` | observed `model`, `host`, `candidate` matching launch |
| `phase_start` | `phase_id`, exact `prompt`, distinct `session_id` for each new session |
| `tool_call` | unique `call_id`, `name`, complete `arguments` |
| `tool_result` | matching `call_id`, complete `output`, boolean `is_error` |
| `assistant_message` | full `content` |
| `interruption` | `phase_id` for the required interruption |
| `memory_access` | `phase_id`, `backend` (`recall`/`native_memory`), `operation` (`read`/`write`), `project_root` |
| `fault` | `fault`, `severity`, `evidence` (raw export pointer) |
| `run_end` | `complete: true`, integer `exit_code` |

Keep extra message/metadata events as needed. Pair failed tools with their error
results. Do not truncate strings. Missing exports, gaps, unpaired calls, missing
interruption, changed model or incomplete traces produce unknown. A nonzero exit
produces a failed attempt. Raw exports are the source of truth. Normalization
and host isolation are controller attestations subject to independent review.

`observation.json` example shape (these values are examples, not evidence):

```json
{
  "fresh_context": true,
  "workspace_only": true,
  "controller_context_absent": true,
  "judge_context_absent": true,
  "fresh_store": true,
  "full_trace": true,
  "runtime_policy_verified": true,
  "evidence": "Retained export, config and enforced access-boundary references",
  "tokens": {"input": 100, "output": 20},
  "elapsed_seconds": 1.5,
  "memory_access_audit": {
    "complete": true,
    "surfaces": ["session_start", "prompt", "tools", "stop", "finalizer"],
    "phases": ["setup", "task"],
    "event_count": 0,
    "evidence": "Instrumented reads/writes and phase boundaries in raw export"
  }
}
```

Sum actual provider input/output tokens and monotonic elapsed time across all
phases. State provider cache accounting in the evidence; retain raw usage objects.
Missing usage/time stays null, never zero or an estimate. Use the actual ordered
phase list (`task`, `setup/task`, or `setup/resume`). Audit event_count covers all
memory events, including setup. Reported no-memory reads/writes cover task only.

The judge receives the private rubric and retained evidence after the subject
finishes. It must not send feedback to the subject. `assessment.json` shape:

```json
{
  "judge": "Actual independent judge identity/model",
  "trace_sha256": "SHA256_OF_NORMALIZED_TRACE",
  "evidence": "Artifact checks and trace references for each decision",
  "task_result": "unknown",
  "wrong_action": null,
  "stale_memory_use": null,
  "harms": [],
  "history_benefit": null
}
```

Task result is `pass`, `fail` or `unknown`. Harm flags are boolean or null. Use
`harms: null` for unknown harm review. Known harms are objects with `severity`,
`fault`, and `evidence`. `matched.CRITICAL` defines P0/P1 codes; a named critical
fault cannot be downgraded. Foreign project access, RECALL in controls,
native memory in candidate/memory-off/docs-only, no-memory task access and
stale-fact misuse also produce blocking harms. Backend permissions come from
the arm identity. A contradictory launch flag or verified-policy attestation
cannot permit a forbidden read or write. Missing backend/operation stays unknown.

For a history-dependent candidate, history_benefit can be an object with
`helps: true`, `compared_attempts` (exactly three control attempt IDs from the same
family, one each for memory-off, docs-only and native memory), and `evidence`
explaining the observed benefit. Use all three control perspectives.
A correct answer alone does not prove memory helped. Comparisons must refer to
retained completed control attempts. Sealing the candidate records each compared
control receipt's SHA-256. A missing control, a changed receipt, an unresolved
result or a receipt created after the judgment cannot count as a benefit. A
later rerun never silently replaces a referenced attempt. Judge decisions remain
visible as judge decisions, distinct from deterministic harness checks.

```powershell
python bench/run_matched_eval.py seal --evidence C:/trial-01/evidence --attempt recurring_failure--memory_off--1 --trace C:/controller/trace.jsonl --raw C:/controller/raw.jsonl --observation C:/controller/observation.json --assessment C:/controller/assessment.json
python bench/run_matched_eval.py report --evidence C:/trial-01/evidence
```

Omit unavailable files when sealing an abandoned attempt. It stays unknown. Never
make empty substitute traces. Sealing writes SHA-256 receipts and refuses to
replace old evidence. Seal/report exit 2 for unknown, 1 for fail/blocked, and 0
only for a complete passing matrix. Setup commands exiting 0 prove setup only.

Reports include all 20 cells and all attempts. Task result, wrong action, stale
memory use, tokens, time and harms are separate. There is no mean quality score.
The original judge verdict remains visible if missing evidence makes the verified
result unknown. Task 13 requires 20 known cases, candidate correctness in four
of five families, clean stale/no-memory cases, history benefit in two dependent
families, exact frozen ZIP and no retained P0/P1. This is a small release signal,
not a universal productivity claim.

## Mechanism gates

```powershell
python -m pytest bench/tests -q
python bench/run_bench.py run --mode light --baseline bench/baselines/v1.3.0.json --strict
```

Tests cover seeded harms, missing traces/instrumentation, blind payloads, separate
stores, fixed identity, failed-attempt retention and rerun limits. Synthetic test
outputs must never enter an actual matrix evidence root.
