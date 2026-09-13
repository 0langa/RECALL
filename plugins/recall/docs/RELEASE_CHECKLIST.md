# RECALL v1.6.0 release evidence

This table starts fresh for v1.6.0.
It does not reuse checks from an older release.
`Pending at candidate freeze` is not a pass.

The final public asset and evidence will be at the [v1.6.0 GitHub release](https://github.com/0langa/RECALL/releases/tag/v1.6.0) after publication.

## Candidate evidence table

| Gate | Status at candidate freeze | Evidence needed before release |
| --- | --- | --- |
| Wave 1 joined source | Accepted | Source commit `ee4419f69fbcf7e7302553fdcd8b67847d8ed842`; 30 unit modules, 14 smoke checks, Ruff, Mypy, and public contracts passed. |
| SQLite and JSONL concurrency lane | Approved in bounded scope | Review B, retained lane receipts, and the pre-doc joined rerun passed. The final clean-candidate rerun is still required. |
| Matched-evaluation mechanism | Approved in bounded scope | Review B covers mechanism controls only. An actual matched-benefit result is still required. |
| Hygiene lane | Accepted with P2 follow-up | Review B failure is retained. Use canonical project-relative source paths. The pre-doc joined rerun passed. The final clean-candidate rerun is still required. |
| Truth and retrieval lane | Approved in bounded scope | Fix commit `00691a83d8ad5f44565fe9aad0f7ab0f3d2d39da`; 32 unit modules and 14 smoke checks passed. The pre-doc joined rerun passed. The final clean-candidate rerun is still required. |
| Runtime and no-memory lane | Accepted | Review A found two P1 and two P2 defects. The one allowed fix pass addressed them. Review B passed with no open P0 or P1. |
| Final joined source gate | Pending at candidate freeze | The Task 10 pre-doc gate passed. One clean release-candidate commit must pass unit, smoke, Ruff, Mypy, strict benchmark, quality, and required contract checks. |
| Version and docs contract | Pending at candidate freeze | Three manifests, MCP server, package test, install pins, and docs checks must use v1.6.0. |
| Exact ZIP build | Pending at candidate freeze | Build from the clean release candidate commit. Record ZIP SHA-256. |
| ZIP inspection | Pending at candidate freeze | Prove no runtime store, Git data, Python cache, personal path, or secret-shaped text. |
| ZIP marketplace smoke | Pending at candidate freeze | Run against the exact frozen ZIP. |
| Codex installed package | Pending at candidate freeze | Fresh isolated-home proof with Codex CLI `0.154.0` and the exact ZIP. |
| Claude Code installed package | Pending at candidate freeze | Fresh isolated-home proof with Claude Code `2.1.268` and the exact ZIP. |
| Kimi Code installed package | Pending at candidate freeze | Fresh isolated-home proof with Kimi Code `0.42.0` and the exact ZIP. |
| Matched user benefit | Pending at candidate freeze | Run the frozen candidate and all required controls. Keep unknown values unknown. |
| CI | Pending at candidate freeze | All required `recall-quality.yml` jobs must pass on the reviewed commit. |
| Local and CI package identity | Pending at candidate freeze | Compare contents and hashes for the reviewed commit. |
| Tag and GitHub release | Pending at candidate freeze | Tag must resolve to the approved commit. The release asset hash must match the frozen ZIP. |

## Accepted follow-up

The v1.6.0 hygiene plan validator uses canonical project-relative source paths.
`README.md` passes.
Equivalent `./README.md` and `.\README.md` forms fail closed.
No unsafe apply was seen.

Use this workaround:

1. Keep source metadata in canonical project-relative form.
2. Create a new plan.
3. Review the complete plan.
4. Apply that exact plan.
5. Never change the hashed reviewed plan.

CLI flow:

```powershell
python .\scripts\recall_skill.py --root <project-root> hygiene-plan --scope project --save-plan recall-hygiene-plan.json
python .\scripts\recall_skill.py --root <project-root> hygiene-apply --safe --plan-file recall-hygiene-plan.json
```

MCP flow:

1. Call `memory_hygiene` with `mode=plan`.
2. Keep the complete plan object.
3. Pass that exact object in `plan` to `mode=apply_safe`.
4. When `claim_key` is present, use `response.plan`.

## Known limits

- JSONL is supported for normal process concurrency.
- One store-local operating-system lock serializes JSONL operations.
- Each JSONL file replacement uses flush, `fsync`, and atomic replace.
- JSONL has no multi-file rollback.
- Multi-file power-loss safety is not certified.
- The vector index is derived state and may need a rebuild after a fault.
- The 21-case hygiene fixture is bounded lexical evidence.
- Broad semantic truth is not certified.
- The 5,000-card comparison is a synthetic SQLite test.
- Its candidate-to-v1.5.5 median ratio was `0.9974007` under high host load.
- Candidate peak working set was `149549056` bytes.
- Baseline peak working set was `148074496` bytes.
- These numbers make no speed claim.
- Host readiness does not prove the exact ZIP.
- No real project memory store was used.

## Commands for the final source candidate

Run from the repository root:

```powershell
python -m ruff check .
python -m mypy --config-file pyproject.toml
python bench\run_bench.py run --mode light --baseline bench\baselines\<baseline>.json --strict
python RECALL_quality_suite\scripts\run_recall_quality_suite.py --repo-root . --quick
```

Run from `plugins\recall`:

```powershell
python scripts\run_tests.py --exclude-smoke --json
python scripts\smoke_recall.py --json
```

Run the metadata and docs contract tests that own the changed public text.
Record each command, source commit, exit code, and retained result path.

## Commands for the exact ZIP

Run from the repository root:

```powershell
python build_plugin.py
python plugins\recall\scripts\inspect_package.py dist\recall.zip
python plugins\recall\scripts\smoke_zip_marketplace.py dist\recall.zip --json
Get-FileHash -Algorithm SHA256 -LiteralPath dist\recall.zip
```

Do not commit `dist/recall.zip`.
Do not call the release ready while a P0 or P1 is open.
