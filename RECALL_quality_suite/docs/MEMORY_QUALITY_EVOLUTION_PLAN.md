# RECALL Memory Quality Evolution Plan

This plan defines how RECALL memory quality must improve from alpha-stage behavior to final product behavior.

## Current memory quality expectations

Current alpha expectations:

- RECALL can store and retrieve durable project facts locally.
- Current memories should usually outrank stale or superseded ones.
- Hooks should capture some useful development context without obvious raw-noise dumping.
- Retrieval should be useful for directed queries, but it may still lean on synthetic fixtures and limited long-session evidence.

## Target final memory quality expectations

Final expectations:

- Memory remains useful across long real development work, not only short demos.
- Current truth reliably outranks stale history.
- Superseded and archived records remain traceable without misleading retrieval.
- Contradictory memories are surfaced or downgraded instead of silently blending into false certainty.
- Fresh source-blind agents can recover architecture, decisions, risks, and next steps with high factual precision.

## Source-blind evaluation process

1. Build a memory pack from real project state and curated fixtures.
2. Expose only the memory pack to a fresh evaluator agent.
3. Ask the source-blind gate questions from `rubrics/source_blind_quality_gate.md`.
4. Score against hidden ground truth.
5. Record failures as blockers when the blind agent is stale, vague, or overconfident.

Synthetic-only success is not enough for release.

## Stale and superseded memory handling

- Active memory must rank above stale or superseded memory for equivalent topics.
- Stale memories must remain inspectable for history, but clearly marked.
- Superseded memories must preserve lineage to the correcting memory where possible.
- Review workflows should encourage confirm, resolve, stale, supersede, merge, and archive instead of destructive deletion.

## Contradiction detection expectations

Contradiction handling should mature over time:

- Alpha: obvious conflicts are manually reviewable.
- Beta: retrieval and review surfaces highlight likely contradiction clusters.
- Release Candidate: corrected or superseded truth is favored automatically.
- Final Product: contradictory memory rarely reaches users as confident current guidance.

## Long-session endurance expectations

Long-session endurance means memory quality should survive repeated hook writes, corrections, and planning cycles without drowning signal in repetitive summaries.

Evidence should include:

- Benchmark coverage for larger memory sets.
- Review-memory workflows that expose noise buildup.
- Retrieval tests that remain useful after many writes.

## Cross-agent consistency expectations

Cross-agent consistency means two fresh agents given the same memory pack should converge on the same major architecture facts, decision history, risks, and uncertainty boundaries.

cross-agent consistency is a required quality signal, not optional polish.

If agents diverge materially, improve memory structure, summaries, lineage, or fixture realism before claiming maturity.

## Missing-information honesty expectations

missing-information honesty is mandatory.

- Memory must not imply exact code details it does not contain.
- Blind plans must separate known facts from inferred guesses.
- Unknowns should be called out explicitly in fixtures, prompts, and rubrics.

## Fixture evolution plan

Fixtures should evolve in this order:

1. Synthetic cards proving storage and ranking basics.
2. Curated project-history-backed cards derived from real docs, commits, and release notes.
3. Mixed-history packs containing stale, superseded, contradictory, and partial memories.
4. Endurance packs representing longer real project timelines.

Do not keep fixtures permanently polished and unreal. Move them toward real project-history-based cases as the repository matures.
