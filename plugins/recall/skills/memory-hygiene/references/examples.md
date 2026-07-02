# Worked Hygiene Examples

Concrete adapter runs for common `memory-hygiene` situations. All examples use the public skill adapter and stay local-only.

## Example 1 — Stale source-backed memory

Candidate: memory 42 references `docs/legacy-arch.md` which was deleted last week.

```bash
python ./scripts/recall_skill.py hygiene-scan --limit 100
python ./scripts/recall_skill.py hygiene-plan --scope project
python ./scripts/recall_skill.py hygiene-apply --safe --limit 10
```

Expected plan:

```json
{
  "action": "hygiene-plan",
  "inspected": 100,
  "proposals": [
    {
      "id": 42,
      "proposed_action": "stale",
      "confidence": 0.94,
      "reason": "source_path no longer exists",
      "safe_to_apply": true
    }
  ]
}
```

Apply outcome: lifecycle status updates to `stale`; memory content stays for history.

## Example 2 — Near-duplicate commands

Two `commands` memories describe the same test command with different summaries.

Expected plan:

```json
{
  "id": 51,
  "proposed_action": "needs_confirmation",
  "confidence": 0.72,
  "reason": "near-duplicate of 47; provenance differs",
  "safe_to_apply": false,
  "related_ids": [47]
}
```

Do not auto-merge. Hand to `manage-memory merge-memories 47 51` after user approves.

## Example 3 — Current-truth conflict

Two records claim `recall.kimi.standard_average` with different values; one is validated, the other is hypothesis.

```bash
python ./scripts/recall_skill.py reconcile-current-truth --claim-key recall.kimi.standard_average
```

Expected result:

```json
{
  "action": "reconcile-current-truth",
  "winner": {"id": 60, "lifecycle": "validated", "value": 90.12},
  "loser": {"id": 55, "lifecycle": "hypothesis", "value": 88.4},
  "proposed_action": "supersede",
  "safe_to_apply": true
}
```

## Example 4 — Weak preference

A record asserts a user preference with no evidence fields.

Expected plan:

```json
{
  "id": 63,
  "proposed_action": "needs_confirmation",
  "confidence": 0.61,
  "reason": "preference without evidence fields",
  "safe_to_apply": false
}
```

Follow-up: ask the user to confirm; if confirmed, save through `save-insight` with `--preference-key`, `--preference-evidence-type`, and `--decision-id`.

## Example 5 — Route decision for docs-shaped candidate

```bash
python ./scripts/recall_skill.py route-memory "Release notes must stay in docs/manual-release-notes.md."
```

Expected:

```json
{"action":"route-memory","target":"repo_docs","reason":"candidate names a repo doc; belongs in file not memory"}
```

## Example 6 — Refresh source-backed metadata

```bash
python ./scripts/recall_skill.py refresh-source-backed --limit 50
```

Expected:

```json
{
  "action": "refresh-source-backed",
  "refreshed": [{"id": 42, "source_path": "docs/architecture.md"}],
  "invalidated": []
}
```
