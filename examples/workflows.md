# RECALL Example Workflows

## Save A Decision

```powershell
python .\scripts\memory_manager.py add decisions "Use SQLite first, with JSONL as an inspectable fallback backend."
```

## Save A Verified Command

```powershell
python .\scripts\memory_manager.py add commands "Verified: python -m unittest discover -s tests"
```

## Recall Startup Context

```powershell
python .\hooks\scripts\session_start.py --query "current project state, requirements, risks, and constraints"
```

## Repair The Index

```powershell
python .\scripts\memory_manager.py rebuild-index
python .\scripts\memory_manager.py doctor
```

## Retrieve By Category

```powershell
python .\scripts\memory_manager.py query "what should not be broken" --category requirements --category constraints --summary
```

## Tune A Custom Category

```powershell
python .\scripts\memory_manager.py define-category api_contracts --description "Stable request and response contracts that must remain compatible." --weight 1.4
```
