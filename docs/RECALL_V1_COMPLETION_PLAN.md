# RECALL V1 Completion Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Keep each task independently testable and commit after each completed task.

**Goal:** Finish RECALL as a reliable, local-first, one-click installable Codex plugin whose initial design plan has no required open spots and the plugin runs stable in different projects of any kind.

**Architecture:** Keep RECALL dependency-light and local by default. Treat project memory storage as the source of truth, structured memory cards as the primary retrieval substrate, hook runtime behavior as the critical integration surface, and packaged installation as a release gate rather than a docs afterthought.

**Tech Stack:** Codex plugin manifest and marketplace metadata, plugin-bundled skills and hooks, Python stdlib backend, SQLite/JSONL, schema-first memory records, deterministic lexical/hash fallback scoring, PowerShell/bash packaging scripts.

---

## Current Known Limitations

- **Install is not live-verified in Codex.** Unit tests and plugin validation pass, but we have not yet proven install, enablement, hook trust, and new-thread recall in the actual Codex app/CLI lifecycle.
- **Hook payload handling is source-verified but not live-verified.** Tests cover Codex-shaped `SessionStart`, `UserPromptSubmit`, `PreCompact`, `Stop`, Bash `PostToolUse`, and `apply_patch` payloads; the remaining risk is actual Codex install lifecycle verification.
- **One-click install is not truly sealed.** The plugin still assumes `python`/`py -3` is available. Codex hook trust is also mandatory for non-managed hooks, so the practical V1 target is “one install plus one hook trust review,” unless Codex adds managed trust for public plugins.
- **Retrieval is schema-first, not model-grade semantic search.** Current V1 should rely on structured memory cards, categories, tags, status, and lexical/hash fallback scoring. This is intentional for local-first reliability; FAISS/Chroma or sentence-transformers remain optional after install/runtime behavior is proven.
- **No packaged runtime artifact is release-tested.** `dist/recall.zip` builds cleanly, but there is no release workflow that installs that zip or verifies the installed cache copy.
- **Real Codex lifecycle verification is still open.** The source smoke harness proves save -> recall -> hook simulation -> doctor across a project boundary; the remaining gap is install, hook trust, and new-thread recall inside the actual Codex app/CLI lifecycle.
- **Manifest presentation is minimal.** There are no assets, screenshots, homepage/repository links, or privacy/terms docs suitable for a polished public plugin card.

## Initial Plan Gap Map

| Original plan item | Current code state | Status | Required V1 action |
|---|---|---:|---|
| Codex plugin scaffold and manifest | `.codex-plugin/plugin.json`, skills, hooks, marketplace exist | Done | Add richer public metadata/assets before release |
| Default categories and custom categories | Built into `config.py` and template | Mostly done | Add explicit custom-category refinement workflow and docs |
| `memory_config.json` project root behavior | Root config is copied if present; runtime config lives in `.codex_memory/` | Done | Document precedence in user docs |
| SQLite backend | Implemented with schema version metadata and additive migration tests | Done | Keep migrations additive |
| JSONL backend | Implemented with malformed-row recovery tests | Done | Keep corrupt rows visible in `doctor` |
| Vector index | JSONL `vector_index.bin`, rebuild, doctor, auto-repair, integrity diagnostics | Mostly done | Add install-cache e2e tests |
| FAISS/Chroma vector search | Not implemented | Optional after V1 | Keep out of V1 unless packaged locally and e2e verified |
| Bundled sentence-transformer embeddings | Not implemented | Optional after V1 | Defer; V1 should use structured memory cards and deterministic retrieval |
| Structured memory-card schema | Not implemented as first-class schema | Missing | Add summary/details/tags/source/status/importance fields and write policy |
| `save_insight` skill | Installed-plugin-first guidance with structured memory-card examples | Done | Keep examples aligned with CLI |
| `retrieve_memory` skill | Installed-plugin-first guidance with schema-first retrieval and repair advice | Done | Keep recovery guidance current |
| `define_category` skill | Installed-plugin-first guidance with auto-created category refinement advice | Done | Add deeper category-weight behavior tests if ranking changes |
| `SessionStart` hook | Simulated and works with project_state categories | Partial | Live Codex install verification required |
| `PreCompact` hook | Parses useful event text and metadata; avoids raw envelope storage | Mostly done | Live Codex install verification required |
| `PostToolUse` hook | Compact command/error capture implemented | Mostly done | Verify live Bash/apply_patch payloads and failure behavior |
| `UserPromptSubmit` hook | Simulated and works | Mostly done | Verify live prompt capture and avoid false positives |
| `Stop` hook | Parses `last_assistant_message`; avoids noisy JSON memory | Mostly done | Live Codex install verification required |
| `UpdateCategories` hook | Script exists but not configured as a real Codex event | Optional | Convert to CLI command/docs; do not invent unsupported hook event |
| Heuristic summarization | Implemented with category/timestamp context | Done | Add quality regression fixtures |
| Packaged dependencies/venv/models | Not implemented | Optional after V1 | Replace with no-dependency release path for V1 |
| Build script | Runs tests, validator, smoke, zip build, and package inspection | Done | Keep release gates current |
| Sample project simulations | `scripts/smoke_recall.py` creates a temp project and verifies the lifecycle | Mostly done | Add packaged/install-cache smoke runs and real Codex lifecycle log |
| Documentation/release | README, install docs, changelog exist | Partial | Add release checklist, known limitations, troubleshooting, and tag workflow |

## Development Tasks

### Task 1: Lock The E2E Acceptance Harness

**Files:**
- Create: `scripts/smoke_recall.py`
- Modify: `README.md`
- Test: `tests/test_smoke_recall.py`

- [x] Add a stdlib-only smoke harness that creates a temp project, writes `.gitignore`, initializes RECALL, saves records in `project_state`, `requirements`, `commands`, and `risks`, queries them, runs `rebuild-index`, runs `doctor`, invokes hook scripts with realistic JSON payloads, verifies `.codex_memory/` stays inside the temp project, and deletes the temp project unless `--keep` is passed.
- [x] Add `--installed-plugin-root` and `--project-root` options so the same harness can run against the source checkout, a built zip extraction, or a Codex-installed cache copy.
- [x] Add a unit test that executes `python scripts/smoke_recall.py --json` and asserts `status: pass`.
- [x] Document the command as the required local acceptance test before release.

### Task 1B: Make Structured Memory Cards First-Class

**Files:**
- Modify: `scripts/memory_manager.py`
- Modify: `scripts/storage.py`
- Modify: `scripts/retrieval.py`
- Modify: `skills/save_insight/SKILL.md`
- Modify: `hooks/scripts/pre_compact.py`
- Test: `tests/test_memory_manager.py`

- [x] Add a memory-card payload convention stored in `metadata`: `summary`, `details`, `tags`, `source`, `status`, `importance`, and `confidence`.
- [x] Add CLI support for `--summary`, `--details`, `--tag`, `--status`, `--importance`, and `--confidence` while preserving the existing positional `content` path.
- [x] Make retrieval search `content`, `metadata.summary`, `metadata.details`, and `metadata.tags`, with category and status filters before scoring.
- [x] Update `save_insight` and hook compaction guidance so Codex writes concise, scannable memory cards instead of arbitrary transcripts.
- [x] Add tests proving a tagged structured card is retrieved without model embeddings and beats an untagged keyword-only note.

### Task 2: Make Hook Payload Handling Release-Grade

**Files:**
- Modify: `hooks/scripts/hook_io.py`
- Modify: `hooks/scripts/pre_compact.py`
- Modify: `hooks/scripts/stop.py`
- Modify: `hooks/scripts/session_start.py`
- Modify: `hooks/scripts/post_tool_use.py`
- Test: `tests/test_hooks.py`

- [x] Parse hook JSON into event-specific fields instead of summarizing raw JSON wrappers.
- [x] For `PreCompact`, store a `session_summaries` record only when useful text is present; include `trigger`, `turn_id`, and source metadata.
- [x] For `Stop`, store `last_assistant_message` as `project_state` only when non-empty; never store the whole hook envelope as memory content.
- [x] For `SessionStart`, return `hookSpecificOutput.additionalContext` only when relevant memories exist; otherwise exit cleanly with no noisy UI message.
- [x] For `PostToolUse`, verify live-shaped Bash and `apply_patch` payloads, keep command/error summaries compact, and redact secrets before storage.
- [x] Add regression tests for empty payloads, malformed JSON, missing fields, real-shaped `PreCompact`, real-shaped `Stop`, Bash success, Bash failure, and `apply_patch`.

### Task 3: Harden Storage, Config, And Index Recovery

**Files:**
- Modify: `scripts/config.py`
- Modify: `scripts/storage.py`
- Modify: `scripts/index_store.py`
- Modify: `scripts/memory_manager.py`
- Test: `tests/test_config.py`
- Test: `tests/test_memory_manager.py`

- [x] Add tests for project-root `memory_config.json` copy precedence and invalid category weights.
- [x] Add malformed JSONL row recovery: skip bad rows, report them in `doctor`, and never fail the whole query because one line is corrupt.
- [x] Add index integrity checks for missing IDs, stale IDs, wrong dimensions, missing embedding model, and invalid JSON rows.
- [x] Make `doctor` return `warnings` and `repairs_available` fields so support output is actionable.
- [x] Add `memory_manager.py repair` as a single command that validates config, rebuilds the index, and reports final health.
- [x] Add SQLite migration tests using an older schema fixture and assert additive migration preserves records.

### Task 4: Close The Skill And User Workflow Gaps

**Files:**
- Modify: `skills/save_insight/SKILL.md`
- Modify: `skills/retrieve_memory/SKILL.md`
- Modify: `skills/define_category/SKILL.md`
- Modify: `examples/workflows.md`
- Test: `tests/test_package_metadata.py`

- [x] Update skill docs so they describe installed-plugin behavior first and direct CLI fallback second.
- [x] Make unknown category behavior explicit: auto-create, warn in metadata, then recommend `define_category` refinement.
- [x] Add examples for saving requirements, risks, commands, and session summaries.
- [x] Add test assertions that every skill mentions local-only storage and no secrets.
- [x] Remove any wording that implies cloud, hosted services, or remote APIs are needed.

### Task 5: Make Packaging Truly Release-Checkable

**Files:**
- Modify: `build_plugin.ps1`
- Modify: `build_plugin.sh`
- Create: `scripts/inspect_package.py`
- Create: `docs/RELEASE_CHECKLIST.md`
- Test: `tests/test_package_metadata.py`

- [x] Update build scripts to run unit tests, plugin validation, package inspection, and the smoke harness before producing the final zip.
- [x] Add `scripts/inspect_package.py` to reject `__pycache__`, `.pyc`, `.git`, `.codex_memory`, personal paths, fake key-shaped strings, missing manifest, missing hooks, and missing skills.
- [x] Add a release checklist covering install from repo marketplace, install from built archive/extraction, hook trust, new-thread recall, and uninstall/reinstall.
- [x] Keep homepage/repository metadata tests deferred until public URLs are finalized; retain manifest/license/marketplace/package tests.

### Task 6: Verify Actual Codex Install Lifecycle

**Files:**
- Modify: `docs/INSTALL.md`
- Create: `docs/E2E_VERIFICATION_LOG.md`

- [ ] Install from `.agents/plugins/marketplace.json` in Codex CLI/App.
- [ ] Confirm RECALL appears in the plugin picker and can be enabled.
- [ ] Confirm bundled skills are discoverable after a new thread starts.
- [ ] Review and trust bundled hooks via `/hooks`.
- [ ] Run a real project lifecycle: “remember this,” command capture, new thread, `SessionStart` recall, manual `retrieve_memory`, `doctor`, and `repair`.
- [ ] Record the exact environment, commands, observed outputs, and any Codex limitations in `docs/E2E_VERIFICATION_LOG.md`.

### Task 7: Polish Public Manifest And One-Click Surface

**Files:**
- Modify: `.codex-plugin/plugin.json`
- Create: `assets/icon.png`
- Create: `assets/logo.png`
- Create: `docs/PRIVACY.md`
- Modify: `.agents/plugins/marketplace.json`
- Modify: `README.md`

- [ ] Add repository, homepage, privacy policy, and terms fields if they are stable public URLs.
- [ ] Add small local assets under `assets/` and reference them from the manifest only after validator confirms they are accepted.
- [ ] Clarify the practical one-click story: plugin install is one click; hook execution still requires Codex’s trust review for non-managed hooks.
- [ ] Update README with “Minimal Working Path,” “Troubleshooting,” and “Known Limitations.”

### Task 8: Release Gate And Tag

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/RELEASE_CHECKLIST.md`

- [ ] Run `python -m unittest discover -s tests`.
- [ ] Run plugin validation.
- [ ] Run `python scripts/smoke_recall.py --json`.
- [ ] Run `.\build_plugin.ps1`.
- [ ] Run package inspection against `dist/recall.zip`.
- [ ] Run the Codex install lifecycle checklist from Task 6.
- [ ] If all checks pass, tag `v0.1.0`, create a GitHub release, and attach the built zip as a release artifact rather than committing it.

## Optional After V1

- Replace hash embeddings with a bundled local sentence-transformer only if the model can be packaged, installed, and smoke-tested without network calls. This is not a V1 blocker because structured memory cards, tags, and deterministic retrieval cover the advertised local-first behavior.
- Add FAISS/Chroma only if it remains local, deterministic, and simple to repair.
- Add optional local summarizer model only after hook and storage behavior are fully verified.
- Add MCP/app integrations only if they solve a concrete workflow gap.

## Verification Sources

- Official Codex plugin docs confirm `.codex-plugin/plugin.json`, repo marketplaces, plugin root structure, default `hooks/hooks.json`, and `PLUGIN_ROOT`/`PLUGIN_DATA` behavior: https://developers.openai.com/codex/plugins/build
- Official Codex hook docs confirm hook trust, event scopes, command hook limitations, `commandWindows`, and `hookSpecificOutput.additionalContext`: https://developers.openai.com/codex/hooks
- Letta/MemGPT memory docs support the schema-first direction by emphasizing memory hierarchy, editable memory blocks, archival storage, and agent-managed memory updates before raw vector retrieval: https://docs.letta.com/guides/agents/memory and https://docs.letta.com/guides/agents/architectures/memgpt
- Recent agent-memory survey work frames memory as a write-manage-read loop across temporal scope, representation, and control policy, which supports improving write policy and record structure before adding local models: https://arxiv.org/abs/2603.07670
- Current repo verification after Task 5: `python -m unittest discover -s tests` passes 42 tests; `python scripts/smoke_recall.py --json` passes; plugin validator passes against the repo root; `.\build_plugin.ps1` builds and package-inspects `dist/recall.zip`.
