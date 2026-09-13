# RECALL — v1.6.0 release status

Updated: 2026-09-13.

## Current state

`v1.6.0` is a release candidate.
It is not yet the public release.

Wave 1 was accepted at source commit `ee4419f69fbcf7e7302553fdcd8b67847d8ed842`.
The storage lane and matched-evaluation mechanism review are approved in their bounded scopes.

The hygiene lane is accepted with one follow-up.
Canonical project-relative source paths such as `README.md` pass saved-plan validation.
Equivalent `./README.md` and `.\README.md` paths fail closed.
Do not change the hashed reviewed plan.
Create a new plan with canonical paths.

The truth and retrieval lane Review B approved fix commit `00691a83d8ad5f44565fe9aad0f7ab0f3d2d39da` in its bounded scope.
Its 32-unit-module and 14-smoke-check receipts do not replace final joined gates.

The runtime lane Review A found two P1 defects and two P2 defects.
The one allowed fix pass addressed those defects.
Review B passed on the joined source with no open P0 or P1.

The Task 10 source gates passed before the version and documentation update.
A final clean-candidate rerun is still required after this release-candidate commit.

## Candidate scope

The candidate adds these user-visible controls:

- Safe concurrent save behavior for SQLite and normal JSONL process concurrency.
- A fail-closed memory-free turn guard across public surfaces and hooks.
- Observed-evidence checks for `validated` status.
- Exact opaque structured-claim handling.
- Stable hygiene plans with separate scan, output, and action limits.
- Exact reviewed-plan apply through CLI and MCP.
- Conservative project-root resolution.
- Retrieval health warnings that survive card selection and budget cuts.
- A 256-D local hash embedder description that matches the source.
- One MCP declaration in each provider manifest, including Codex.

These are candidate behaviors until final source and package gates bind them to the release commit.

## Required next work

1. Commit the v1.6.0 versions and final docs.
2. Run the final clean-candidate source, metadata, and docs gates.
3. Build and inspect the exact `recall.zip` from the clean release candidate.
4. Record its SHA-256.
5. Run source-blind and matched-benefit evaluation against the frozen candidate.
6. Run fresh installed-package tests on Codex CLI `0.154.0`, Claude Code `2.1.268`, and Kimi Code `0.42.0`.
7. Run full CI on the reviewed commit.
8. Confirm that local and CI package contents agree.
9. Publish only after there is no open P0 or P1.

## Evidence that is pending at candidate freeze

| Proof | Status | Required evidence |
| --- | --- | --- |
| Final joined source gates | Pending | One clean candidate commit and retained Task 10 receipts |
| Exact ZIP | Pending | ZIP SHA-256, package inspection, and ZIP marketplace smoke |
| Installed Codex package | Pending | Fresh isolated-host proof from the exact ZIP |
| Installed Claude Code package | Pending | Fresh isolated-host proof from the exact ZIP |
| Installed Kimi Code package | Pending | Fresh isolated-host proof from the exact ZIP |
| Matched user benefit | Pending | Frozen matched evaluation with completed controls |
| CI | Pending | Required `recall-quality.yml` jobs on the reviewed commit |
| Tag and GitHub release | Pending | Tag identity, release asset identity, and published hash |

The public asset and evidence will be available at the [v1.6.0 GitHub release](https://github.com/0langa/RECALL/releases/tag/v1.6.0) after publication.

## Known limits

- JSONL has one cross-process lock and atomic replacement per file.
- JSONL does not have one transaction across several files.
- Multi-file power-loss safety is not certified.
- The 21-case hygiene set is a bounded lexical positive check.
- Broad semantic truth is not certified.
- The 5,000-card test is synthetic SQLite evidence under host load.
- Its median ratio of `0.9974007` is no speed claim.
- Host readiness does not prove the exact package.
- No real project memory store was used.
