# RECALL V1 Completion Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Keep each task independently testable and commit after each completed task.

**Goal:** Finish RECALL as a reliable, local-first, one-click installable Codex plugin whose initial design plan has no required open spots and the plugin runs stable in different projects of any kind.

**Architecture:** Keep RECALL dependency-light and local by default. Treat project memory storage as the source of truth, structured memory cards as the primary retrieval substrate, hook runtime behavior as the critical integration surface, and packaged installation as a release gate rather than a docs afterthought.

**Tech Stack:** Codex plugin manifest and marketplace metadata, plugin-bundled skills and hooks, Python stdlib backend, SQLite/JSONL, schema-first memory records, deterministic lexical/hash fallback scoring, PowerShell/bash packaging scripts.

---

## Current Known Limitations

- **Install is CLI-verified and app-evidenced.** Codex CLI marketplace add/install, remove/reinstall, installed-cache smoke, and built-archive marketplace smoke pass. User screenshots confirm plugin picker visibility, skill discovery, and hook trust/enablement in the Codex app.
- **Hook payload handling is test-verified and live-evidenced.** Tests cover Codex-shaped `SessionStart`, `UserPromptSubmit`, `PreCompact`, `Stop`, Bash `PostToolUse`, and `apply_patch` payloads. User retests confirmed live hook activation without exit-code failures; future Codex payload drift remains a normal compatibility risk.
- **One-click install is not truly sealed.** The plugin still assumes `python`/`py -3` is available. Codex hook trust is also mandatory for non-managed hooks, so the practical V1 target is “one install plus one hook trust review,” unless Codex adds managed trust for public plugins.
- **The public action surface is skills and hooks, not the backend CLI.** The package still includes internal Python backend scripts because hooks and local diagnostics need them. Bundled skills should use the narrow `recall_skill.py` adapter and should not steer Codex toward `memory_manager.py` unless the user explicitly asks for maintenance diagnostics.
- **Retrieval is schema-first, not model-grade semantic search.** Current V1 should rely on structured memory cards, categories, tags, status, and lexical/hash fallback scoring. This is intentional for local-first reliability; FAISS/Chroma or sentence-transformers remain optional after install/runtime behavior is proven.
- **Zip install is release-tested through extraction.** `dist/recall.zip` builds, package-inspects cleanly, extracts into a temporary marketplace wrapper, installs through Codex CLI, and passes installed-cache smoke.
- **Real Codex lifecycle is verified as far as current tools expose it.** The source and installed-cache smoke harnesses prove save -> recall -> hook simulation -> skill adapter -> doctor across a project boundary. User-provided app screenshots and memory-store checks confirm live hook activation, hook trust, plugin picker visibility, and new-session checkpoint behavior.
- **Manifest presentation is mostly ready.** Homepage/repository links, privacy/terms docs, and local icon/logo assets are present and validator-accepted. Screenshots are still optional polish.

## Initial Plan Gap Map

| Original plan item | Current code state | Status | Required V1 action |
|---|---|---:|---|
| Codex plugin scaffold and manifest | Installable plugin lives at `plugins/recall`; repo root is the marketplace wrapper; public metadata/assets validate | Done | Add screenshots only if useful |
| Default categories and custom categories | Built into `config.py` and template | Mostly done | Add explicit custom-category refinement workflow and docs |
| `memory_config.json` project root behavior | Root config is copied if present; runtime config lives in `.codex_memory/` | Done | Document precedence in user docs |
| SQLite backend | Implemented with schema version metadata and additive migration tests | Done | Keep migrations additive |
| JSONL backend | Implemented with malformed-row recovery tests | Done | Keep corrupt rows visible in `doctor` |
| Vector index | JSONL `vector_index.bin`, rebuild, doctor, auto-repair, integrity diagnostics | Mostly done | Add install-cache e2e tests |
| FAISS/Chroma vector search | Not implemented | Optional after V1 | Keep out of V1 unless packaged locally and e2e verified |
| Bundled sentence-transformer embeddings | Not implemented | Optional after V1 | Defer; V1 should use structured memory cards and deterministic retrieval |
| Structured memory-card schema | Implemented as metadata convention with adapter/CLI flags, hook write policy, and retrieval scoring over card fields | Done | Keep card policy aligned with bundled skills |
| `save_insight` skill | Installed-plugin-first guidance with structured memory-card examples through `recall_skill.py` | Done | Keep examples aligned with the skill adapter |
| `retrieve_memory` skill | Installed-plugin-first guidance with schema-first retrieval through `recall_skill.py` | Done | Keep recovery guidance current |
| `define_category` skill | Installed-plugin-first guidance with auto-created category refinement through `recall_skill.py` | Done | Add deeper category-weight behavior tests if ranking changes |
| `SessionStart` hook | Installed-cache smoke verifies context injection; live app screenshot verifies activation | Done | Watch for future Codex payload drift |
| `PreCompact` hook | Parses useful event text and metadata; avoids raw envelope storage | Done | Watch for future Codex payload drift |
| `PostToolUse` hook | Compact command/error capture implemented, noisy successful output reduced, live runs observed | Done | Watch for future Codex payload drift |
| `UserPromptSubmit` hook | Explicit memory cues work and false-positive `remembered` regression is covered | Done | Watch for future Codex payload drift |
| `Stop` hook | Parses `last_assistant_message`, avoids noisy JSON memory, live checkpoints observed | Done | Watch for future Codex payload drift |
| `UpdateCategories` hook | Script exists but not configured as a real Codex event | Optional | Convert to CLI command/docs; do not invent unsupported hook event |
| Heuristic summarization | Implemented with category/timestamp context | Done | Add quality regression fixtures |
| Packaged dependencies/venv/models | Not implemented | Optional after V1 | Replace with no-dependency release path for V1 |
| Build script | Runs tests, validator, smoke, zip build, and package inspection | Done | Keep release gates current |
| Sample project simulations | `scripts/smoke_recall.py` creates a temp project and verifies source plus installed-cache lifecycle; live test log recorded | Done | Keep smoke fixtures representative |
| Documentation/release | README, install docs, changelog, release checklist, limitations, and verification log exist | Done | Keep release checklist current |

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

- [x] Update skill docs so they describe installed-plugin behavior first and use the bundled `recall_skill.py` adapter instead of advertising the backend maintenance CLI.
- [x] Make unknown category behavior explicit: auto-create, warn in metadata, then recommend `define_category` refinement.
- [x] Add examples for saving requirements, risks, commands, and session summaries.
- [x] Add test assertions that every skill mentions local-only storage and no secrets.
- [x] Add test assertions that bundled skills reference `recall_skill.py` and do not reference `memory_manager.py`.
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

- [x] Install from `.agents/plugins/marketplace.json` in Codex CLI.
- [x] Confirm RECALL appears in the Codex App plugin picker and can be enabled there.
- [x] Confirm bundled skills are discoverable after a new thread starts.
- [x] Review and trust bundled hooks in Codex Settings > Coding > Hooks.
- [x] Run a real project lifecycle using the installed plugin bundle: “remember this,” command capture, new thread, `SessionStart` activation, manual retrieval via the skill/adapter path, and maintenance diagnostics only if needed.
- [x] Record the exact environment, commands, observed outputs, and any Codex limitations in `docs/E2E_VERIFICATION_LOG.md`.

### Task 7: Polish Public Manifest And One-Click Surface

**Files:**
- Modify: `.codex-plugin/plugin.json`
- Create: `assets/icon.png`
- Create: `assets/logo.png`
- Create: `docs/PRIVACY.md`
- Modify: `.agents/plugins/marketplace.json`
- Modify: `README.md`

- [x] Add repository, homepage, privacy policy, and terms fields if they are stable public URLs.
- [x] Add small local assets under `assets/` and reference them from the manifest only after validator confirms they are accepted.
- [x] Clarify the practical one-click story: plugin install is one click; hook execution still requires Codex’s trust review for non-managed hooks.
- [x] Update README with “Minimal Working Path,” “Troubleshooting,” and “Known Limitations.”

### Task 8: Release Gate And Tag

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/RELEASE_CHECKLIST.md`

- [x] Run `python -m unittest discover -s tests`.
- [x] Run plugin validation.
- [x] Run `python scripts/smoke_recall.py --json`.
- [x] Run `.\build_plugin.ps1`.
- [x] Run package inspection against `dist/recall.zip`.
- [x] Run the Codex install lifecycle checklist from Task 6 against the installed plugin bundle, not source-only backend commands.
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
- Current repo verification after Task 8: `python -m unittest discover -s tests` passes 47 tests from `plugins/recall`; source smoke passes; installed-cache smoke passes; built-archive marketplace smoke passes; plugin validator passes against `plugins/recall`; repo-root `.\build_plugin.ps1` builds and package-inspects `plugins/recall/dist/recall.zip`; `codex plugin add recall@recall-local` succeeds.
