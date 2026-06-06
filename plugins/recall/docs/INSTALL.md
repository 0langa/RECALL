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

```bash
codex plugin marketplace add .
codex plugin add recall@recall-local
```

Or open the plugin browser:

```text
/plugins
```

Install `RECALL` from the `RECALL Local` marketplace and start a new thread.

## Hook Trust

RECALL bundles lifecycle hooks in `hooks/hooks.json`. Codex requires non-managed hooks to be reviewed and trusted before they run. In the Codex app, open Settings > Coding > Hooks.

Review the RECALL hook definitions and trust them when you are ready. After hook definitions change, Codex may ask you to review them again.

## Local Runtime Data

Project memories are written to `.codex_memory/` in the active project, not to the plugin folder. This directory is ignored by git in this repo.

If retrieval ever looks stale, first verify through the same bundled skill adapter the installed plugin uses:

```bash
python ./scripts/recall_skill.py retrieve-memory "current project context" --summary
python ./scripts/recall_skill.py doctor
```

If `doctor` reports repairable index issues, use the safe adapter action:

```bash
python ./scripts/recall_skill.py repair
```

For developer/support diagnostics, the internal backend script still exposes lower-level maintenance commands such as `rebuild-index`. Those commands are not the normal end-user workflow.

If a support session needs to normalize category names after manual config edits, run:

```bash
python ./scripts/update_categories.py --root <project-root>
```

RECALL does not register an `UpdateCategories` hook event; category maintenance is an explicit support command, while normal category refinement uses the bundled `define_category` skill.
