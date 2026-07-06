---
name: define-category
description: Use this skill proactively when creating a reusable category, when configuring retrieval weight, when refining an auto-created definition, or when organizing repeated memory types. Trigger when category configuration is needed; invoke automatically for durable taxonomy work, not one-off tags.
---

# Define Category

Use this skill when the user wants a new memory category or wants to tune how strongly an existing category is retrieved.

RECALL is local-only project memory. Category definitions are stored in the active project's RECALL memory config: `.recall/memory_config.json` for new projects, or existing `.codex_memory/memory_config.json` stores for legacy projects. Never require hosted services or external APIs. Do not put secrets, credentials, tokens, private keys, passwords, or sensitive personal data in category names or descriptions.

## Execution Path

Use this skill as the public RECALL category-management interface. When shell execution is needed, run the bundled skill adapter from the installed plugin root or source plugin root. Treat lower-level backend scripts as internal support code, not as the user-facing RECALL workflow.

All `python ./scripts/recall_skill.py ...` examples assume the current directory is the plugin root. If the shell is in the active project repository, do not look for `./scripts` there; locate the installed/source plugin root or use an absolute adapter path, then pass `--root <project-root>` when needed.

## Contract

This skill receives a category-design request and returns one normalized category definition:
name, description, and retrieval weight. It owns durable taxonomy only — not ordinary tagging,
memory writing, broad cleanup, or retrieval. Storing a fact is `save-insight`'s contract;
inspecting category counts or noisy records is `review-memory`'s contract. Those requests are
out of scope here, not requests this skill routes elsewhere.

Use the contract asset as the quick boundary check:

```json
{"asset":"assets/contract.json","kind":"category-boundary"}
```

## Workflow

1. Normalize the category to lower snake case.
2. List existing categories when you need to avoid creating a near-duplicate category:

```bash
python ./scripts/recall_skill.py list-categories
```

3. Write a short description that explains what belongs in the category.
4. Choose a positive weight. Use `1.0` for normal priority, higher values such as `1.3` to surface the category more aggressively, and lower values such as `0.8` for background context.
5. If RECALL auto-created this category from a saved memory, preserve the normalized name and refine only the description/weight.
6. Run:

```bash
python ./scripts/recall_skill.py define-category <category> --description "<description>" --weight <weight>
```

Add deterministic usage guidance whenever the category will be reused — agents pick categories
correctly when each carries examples, non-examples, and an update rule:

```bash
python ./scripts/recall_skill.py define-category <category> --description "<description>" --weight <weight> \
  --example "<memory that belongs here>" --non-example "<memory that does not>" \
  --update-rule "<how cards in this category age or get superseded>"
```

7. Return the normalized category and explain whether this was a new category or a refinement.
8. When a proposed category overlaps an existing one, reuse or refine the existing category instead of creating a synonym.

## Example

```bash
python ./scripts/recall_skill.py define-category api_contracts --description "Stable API shapes and compatibility promises." --weight 1.4
```

## Inputs

- Category name: normalized to lower snake case.
- Description: concrete inclusion rule, not a vague label.
- Weight: positive number; `1.0` normal, `>1.0` stronger, `<1.0` quieter.

## Output Format

Returns JSON containing normalized category and stored description/weight. Mention normalization when
the output name differs from user input.

```json
{"action":"define-category","category":"api_contracts","details":{"description":"Stable API shapes.","weight":1.4}}
```

## Examples

Moderate priority:

```bash
python ./scripts/recall_skill.py define-category release_evidence --description "Verified packaging, install, and release checks." --weight 1.2
```

Quiet background context:

```bash
python ./scripts/recall_skill.py define-category research_notes --description "Exploratory notes not yet promoted to decisions." --weight 0.8
```

Refining an auto-created category:

```bash
python ./scripts/recall_skill.py define-category eval_findings --description "Durable evaluation scores, score drivers, and quality-gate outcomes." --weight 1.3
```

Rejecting a one-off tag:

```json
{"action":"no-category","reason":"Use a tag because this is not a repeated retrieval purpose."}
```

## Edge Cases

- Near-duplicate category: reuse existing category and refine it.
- Empty or punctuation-only name: reject it.
- Zero/negative weight: reject it.
- One-off label: use tags instead of creating category.
- Sensitive or personal category label: reject it and suggest a non-sensitive abstraction.
- Category too broad: narrow the inclusion rule before raising weight.
- Category too narrow: use tags unless multiple future memories need the same retrieval lane.

## Decision Guide

| Need | Choice |
|---|---|
| Existing built-in meaning | Reuse built-in category |
| Repeated distinct retrieval purpose | Define custom category |
| One-off grouping | Add tag instead |
| Broad category dominates results | Lower weight |

## Troubleshooting

- Unexpected normalized name: run `list-categories` and use returned name.
- Category dominates retrieval: lower weight toward `1.0`.
- Category remains too broad: narrow description or split only when durable use cases differ.
- Category cannot be explained in one sentence: it is probably a workflow or document, not a category.
- Two categories match the same memory equally well: merge the meaning into one category and use tags for the distinction.

## Related

- [Save Insight](../save-insight/SKILL.md) for writing category members.
- [Review Memory](../review-memory/SKILL.md) for category counts and quality.
- [Category guide](references/category-design.md) for naming and weighting.
- Sibling routes: skills/save-insight, skills/review-memory, skills/retrieve-memory.
