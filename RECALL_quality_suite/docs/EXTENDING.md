# Extending the Suite

## Add a new unit/integration check

Create a file under:

```text
recall_quality_suite/tests/test_<area>_contract.py
```

Use only stdlib `unittest` unless the project intentionally adopts a new test dependency.

Import helpers from:

```python
from _harness import plugin_root, run_json, run_text, temp_project
```

If the new check changes required workflow or release truth, update the control docs in `docs/` and `rubrics/` in the same change.

## Add a new source-blind memory case

Edit:

```text
recall_quality_suite/fixtures/source_blind_memory_cards.json
```

Each card should include:

```json
{
  "category": "architecture",
  "content": "Concrete project-specific memory.",
  "summary": "Short summary.",
  "details": "Longer structured details.",
  "tags": ["stable-contract"],
  "source": "plugins/recall/README.md",
  "status": "active",
  "importance": 0.9,
  "confidence": 0.95
}
```

Use `source` for project-history-backed cards so the blind-memory pack preserves where the fact came from.

Then update `tests/test_source_blind_retrieval_contract.py`.

Prefer real project-history-backed cases once they can be verified. Do not keep the fixture set permanently synthetic.

## Add a new performance threshold

Edit:

```text
recall_quality_suite/perf/perf_thresholds.json
```

Keep thresholds conservative across Windows/macOS/Linux. Do not use thresholds that only pass on the maintainer's fastest machine.
Keep the quick profile strict enough for developer-loop regression detection and the full profile appropriate for release evidence.

## Add a release blocker

Edit:

```text
recall_quality_suite/rubrics/production_release_criteria.md
```

Record what is blocked, which stage is blocked, and what evidence exposed the issue.
