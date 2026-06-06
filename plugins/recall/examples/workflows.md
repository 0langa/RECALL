# RECALL Example Workflows

These examples use local-only project memory under `.codex_memory/`. Do not save secrets, credentials, tokens, private keys, passwords, or sensitive personal data.

## Save A Requirement

```bash
python ./scripts/memory_manager.py add requirements "Release checks must pass before tagging." --summary "Release checks gate tags." --details "Run tests, smoke, validator, package inspection, and live install verification before a release tag." --tag release --tag validation --source manual --status active --importance 1.0 --confidence 0.9
```

## Save A Risk

```bash
python ./scripts/memory_manager.py add risks "Hook payload shapes can drift between Codex releases." --summary "Hook payload drift is a release risk." --details "Keep hook parsing narrow, tolerate missing fields, and verify against official Codex hook docs before release." --tag hooks --tag codex --source manual --status open --importance 0.8 --confidence 0.8
```

## Save A Verified Command

```bash
python ./scripts/memory_manager.py add commands "Verified: python -m unittest discover -s tests" --summary "Run unittest discovery for the suite." --details "This validates config, storage, retrieval, hooks, package metadata, and smoke harness coverage." --tag tests --tag command --source manual --status active --importance 0.7 --confidence 1.0
```

## Save A Session Summary

```bash
python ./scripts/memory_manager.py add session_summaries "Completed structured memory cards and hook payload hardening." --summary "Task checkpoint for RECALL V1." --details "Structured card metadata, hook parsing, recovery diagnostics, and repair are implemented and tested." --tag session-summary --tag recall-v1 --source manual --status active --importance 0.7 --confidence 0.9
```

## Recall Startup Context

```bash
python ./hooks/scripts/session_start.py --query "current project state requirements risks constraints architecture"
```

## Retrieve By Category

```bash
python ./scripts/memory_manager.py query "what should not be broken" --category requirements --category constraints --status active --summary
```

## Repair Or Inspect The Backend

```bash
python ./scripts/memory_manager.py doctor
python ./scripts/memory_manager.py repair
```

## Tune A Custom Category

Unknown categories are auto-created with a default weight when saving a memory. Refine reused categories with:

```bash
python ./scripts/memory_manager.py define-category api_contracts --description "Stable request and response contracts that must remain compatible." --weight 1.4
```
