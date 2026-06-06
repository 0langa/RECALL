# RECALL Repository

This repository is a Codex plugin marketplace wrapper. The installable plugin lives at:

```text
plugins/recall/
```

Codex reads the repo marketplace from `.agents/plugins/marketplace.json`, which points to `./plugins/recall` following the official repo marketplace layout.

## Common Commands

macOS/Linux:

```bash
cd ./plugins/recall
python -m unittest discover -s tests
python ./scripts/smoke_recall.py --json
./build_plugin.sh
```

Windows PowerShell:

```powershell
cd .\plugins\recall
python -m unittest discover -s tests
python .\scripts\smoke_recall.py --json
.\build_plugin.ps1
```

From the repo root, the build wrappers delegate to `plugins/recall`:

```bash
./build_plugin.sh
```

```powershell
.\build_plugin.ps1
```

See [plugins/recall/README.md](plugins/recall/README.md) for plugin usage, install, hooks, storage, and release details.
