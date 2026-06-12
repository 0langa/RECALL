---
name: define-category
description: Use this skill proactively when creating a reusable category, when configuring retrieval weight, when refining an auto-created definition, or when organizing repeated memory types. Trigger when category configuration is needed; invoke automatically for durable taxonomy work, not one-off tags.
---

# Define Category

Use this skill when the user wants a new memory category or wants to tune how strongly an existing category is retrieved.

RECALL is local-only project memory. Category definitions are stored in the active project's `.codex_memory/memory_config.json` file and never require hosted services or external APIs. Do not put secrets, credentials, tokens, private keys, passwords, or sensitive personal data in category names or descriptions.

## Execution Path

Use this skill as the public RECALL category-management interface. When shell execution is needed, run the bundled skill adapter from the installed plugin root or source plugin root. Treat lower-level backend scripts as internal support code, not as the user-facing RECALL workflow.

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

## Edge Cases

- Near-duplicate category: reuse existing category and refine it.
- Empty or punctuation-only name: reject it.
- Zero/negative weight: reject it.
- One-off label: use tags instead of creating category.

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

## Related

- [Save Insight](../save-insight/SKILL.md) for writing category members.
- [Review Memory](../review-memory/SKILL.md) for category counts and quality.
- [Category guide](references/category-design.md) for naming and weighting.
