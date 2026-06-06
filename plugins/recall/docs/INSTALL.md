# Install RECALL Locally

RECALL's installable plugin is kept at `plugins/recall/`. The repo includes a marketplace file at `.agents/plugins/marketplace.json` that points Codex at the plugin folder with `source.path: "./plugins/recall"`.

## Codex App

1. Restart Codex so it can discover the repo marketplace.
2. Open Plugins.
3. Select the `RECALL Local` marketplace.
4. Install `RECALL`.
5. Start a new thread and invoke `@recall` or one of its bundled skills.

## Codex CLI

From the repository root:

```powershell
codex plugin marketplace add .
codex plugin add recall@recall-local
```

Or open the plugin browser:

```text
/plugins
```

Install `RECALL` from the `RECALL Local` marketplace and start a new thread.

## Hook Trust

RECALL bundles lifecycle hooks in `hooks/hooks.json`. Codex requires non-managed hooks to be reviewed and trusted before they run. In the CLI, use:

```text
/hooks
```

Review the RECALL hook definitions and trust them when you are ready. After hook definitions change, Codex may ask you to review them again.

## Local Runtime Data

Project memories are written to `.codex_memory/` in the active project, not to the plugin folder. This directory is ignored by git in this repo.

If retrieval ever looks stale, rebuild and inspect the local index:

```powershell
python .\scripts\memory_manager.py rebuild-index
python .\scripts\memory_manager.py doctor
python .\scripts\memory_manager.py repair
```
