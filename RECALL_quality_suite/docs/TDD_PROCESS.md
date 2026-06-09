# RECALL TDD Process

Meaningful behavior changes require tests. RECALL does not accept "test later" as a normal workflow.

## Core rule

If a change alters behavior, safety, packaging expectations, or suite discoverability, add or update a test that proves the intended outcome. Write the failing test first when practical.

## Test selection

| Change shape | Minimum test type |
|---|---|
| Small deterministic logic | Unit test |
| CLI command, hook, or cross-file workflow | Integration/contract test |
| Retrieval usefulness or memory truthfulness | Source-blind retrieval test and, when stage promotion is in play, human source-blind evaluation |
| Runtime cost or endurance risk | Performance benchmark |
| Docs-only wording with no executable behavior change | No new behavior test required, but add/update docs contract tests if discoverability or required files change |

Use the narrowest layer that can prove the behavior, then add broader coverage when regression risk crosses boundaries.

## Red-Green-Refactor for RECALL

1. Red:
   Write a failing test for the intended change.
2. Verify red:
   Confirm it fails for the right reason, not from harness mistakes.
3. Green:
   Implement only enough to satisfy the new expectation.
4. Refactor:
   Clean code or docs while keeping tests green.
5. Re-run the required validation set for the change class.

## Failing test guidance

Write the failing test first when practical for:

- Public CLI behavior.
- Hook lifecycle behavior.
- Retrieval ranking or filtering.
- Redaction and privacy handling.
- Repair, doctor, rebuild, or corruption recovery.
- Suite structure and discoverability expectations.

When exploratory work is needed, throw away the exploration notes/code and restart from an explicit failing test before keeping production changes.

## How to handle bugs

1. Reproduce the bug with a failing test.
2. Verify the test fails because of the bug.
3. Fix the bug with minimal behavior change outside the intended area.
4. Add adjacent edge coverage if the bug suggests a nearby blind spot.

Never fix a bug only by manual testing.

## How to handle refactor work

Refactor means behavior should stay the same.

- Run existing relevant tests before changing code.
- Add a regression test first if behavior is under-specified.
- Keep refactor commits free of hidden behavior changes.

If behavior changes during refactor, it is no longer pure refactor. Reclassify it and add the needed tests.

## How to handle docs-only changes

Docs-only means no behavior contract changed.

- Update docs directly.
- Add docs/discoverability tests if required files, required links, or mandatory instructions changed.
- If docs reveal the code/test behavior is wrong, reclassify the task and return to full TDD.

## What counts as done

A task is done only when all apply:

- Required tests exist.
- New or changed tests were observed failing first when practical.
- All relevant tests pass.
- Required smoke/suite validation passes.
- Docs and rubrics match the new truth.
- Remaining blockers or gaps are reported explicitly.

## Forbidden

The following are forbidden:

This forbidden list is part of the release-control contract.

- Weakening tests merely to pass.
- Deleting a failing assertion without replacing its coverage.
- Rewriting docs to pretend an unmet gate is satisfied.
- Marking alpha behavior as release-ready without gate evidence.
- Treating manual testing as replacement for automated regression coverage.
- Hiding uncertainty that should be captured as missing-information honesty.
