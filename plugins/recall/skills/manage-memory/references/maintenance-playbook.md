# Maintenance Playbook

Use this reference when the maintenance request needs a quick rule instead of a long search.

## Preferred Order

1. Inspect with `review-memory` if identity or status is unclear.
2. Use the least destructive command that satisfies the request.
3. Prefer lifecycle metadata over deletion.
4. Run `doctor` before `repair` so the user can understand what changed.

## Safe Defaults

- Prefer `configure-capture minimal` over `off` unless the user wants full suppression.
- Prefer `archive-noise` over `delete-memory` for automatic command spam.
- Prefer `supersede-memory` over editing both old and new records by hand.
- Prefer `prune-memory` when the memory is obsolete but still historically useful.

## Escalation Signals

- multiple contradictory memories on the same topic
- repeated retrieval failures after repair
- requests to delete many records at once
- requests that mention tokens, passwords, keys, or private credentials
