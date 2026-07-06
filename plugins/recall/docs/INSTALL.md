# Install RECALL

RECALL's installable plugin is kept at `plugins/recall/`. The same folder contains the shared RECALL core, Codex integration files, Kimi Code integration files, and Claude Code integration files. A local checkout is added as a Codex marketplace from the repository root with `codex plugin marketplace add .`; there is no checked-in `.agents/plugins/marketplace.json`.

## Install From GitHub

```bash
codex plugin marketplace add 0langa/RECALL --ref v1.3.0
codex plugin add recall@recall-local
```

You can also use the HTTPS Git URL:

```bash
codex plugin marketplace add https://github.com/0langa/RECALL --ref v1.3.0
codex plugin add recall@recall-local
```

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

## Kimi Code

From Kimi Code, install the plugin directory or GitHub repository path:

```text
/plugins install <path-to-RECALL>/plugins/recall
/reload
```

The Kimi manifest is `kimi.plugin.json`. It loads the `using-recall` Skill at session start and declares a local MCP server named `recall`. Kimi plugin installation does not execute scripts. The MCP server starts after `/reload` or in a new session when enabled by Kimi Code.

When invoking RECALL MCP tools from Kimi, pass the active repository root as `root`. Kimi-originated writes are stamped with `origin_provider: "kimi"` by the MCP adapter.

Optional Kimi hook setup is documented in [KIMI_CODE.md](KIMI_CODE.md). Hooks are configured in `~/.kimi-code/config.toml`; Kimi plugin manifests do not install hook rules.
After editing a local checkout, reinstall or reload Kimi's managed plugin copy
before testing. Kimi and Codex should use the same project root so both agents
share `.recall/` memory instead of creating provider-specific stores.

## Hook Trust

RECALL bundles lifecycle hooks in `hooks/hooks.json`. Codex requires non-managed hooks to be reviewed and trusted before they run. In the Codex app, open Settings > Coding > Hooks.

Review the RECALL hook definitions and trust them when you are ready. After hook definitions change, Codex may ask you to review them again.

## Local Runtime Data

Project memories are written to `.recall/` in new projects, not to the plugin folder. Existing `.codex_memory/` stores remain supported as a legacy fallback when `.recall/` does not exist. Once `.recall/` exists, `.recall/` is the active store and `.codex_memory/` is legacy history unless you explicitly migrate or inspect it. Ignore both `.recall/` and `.codex_memory/` in project repositories.

See [E2E_VERIFICATION_LOG.md](E2E_VERIFICATION_LOG.md) for the latest Codex/Kimi
live verification notes.

If retrieval ever looks stale, first verify through the same bundled skill adapter the installed plugin uses:

Run these examples from the installed/source plugin root so `./scripts/recall_skill.py` resolves. If your shell is in the active project instead, use the adapter's absolute path and pass `--root <project-root>`.

```bash
python ./scripts/recall_skill.py retrieve-memory "current project context" --summary
python ./scripts/recall_skill.py doctor
```

If `doctor` reports repairable index issues, use the safe adapter action:

```bash
python ./scripts/recall_skill.py repair
```

For developer/support diagnostics, lower-level backend modules remain internal support plumbing. They are not the normal end-user workflow.

To review and clean up project memory from the same public adapter used by bundled skills:

The public plugin surface is seven skills. Lifecycle and cleanup commands such as `confirm-memory`, `resolve-memory`, `supersede-memory`, `merge-memories`, `prune-memory`, `edit-memory`, `delete-memory`, and `archive-noise` live under the `manage-memory` skill rather than separate skill folders. Use `memory-hygiene` before mutation when the right routing or cleanup action is unclear.

```bash
python ./scripts/recall_skill.py review-memory --limit 20
python ./scripts/recall_skill.py confirm-memory <id>
python ./scripts/recall_skill.py resolve-memory <id> --note "<why this is resolved>"
python ./scripts/recall_skill.py supersede-memory <old-id> <new-id>
python ./scripts/recall_skill.py merge-memories <primary-id> <secondary-id> [<secondary-id>...]
python ./scripts/recall_skill.py prune-memory <id> --note "<why this was archived>"
```

Pruning is non-destructive; it archives the memory rather than deleting project data.

To plan and safely apply hygiene:

```bash
python ./scripts/recall_skill.py hygiene-scan --limit 80
python ./scripts/recall_skill.py hygiene-plan --scope project
python ./scripts/recall_skill.py hygiene-apply --safe
```

If a support session needs to normalize category names after manual config edits, run:

```bash
python ./scripts/update_categories.py --root <project-root>
```

RECALL does not register an `UpdateCategories` hook event; category maintenance is an explicit support command, while normal category refinement uses the bundled `define-category` skill.
