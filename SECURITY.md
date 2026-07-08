# Security Policy

## Scope

RECALL is a local-first plugin: it stores project memory in the active project's `.recall/` (or legacy `.codex_memory/`) directory and runs entirely on the user's machine. It has no hosted backend, no remote API, and does not phone home. Most security concerns therefore center on the local store and the hooks/MCP server that read and write it — not on server-side infrastructure, because there isn't any.

Areas we consider in scope for a security report:

- Secret/credential leakage into stored memory (write-time or read-time).
- SQL injection, path traversal, or command injection in `plugins/recall/scripts/`.
- A packaged plugin zip shipping runtime artifacts, secrets, or files outside its declared surface (see `scripts/inspect_package.py`).
- A hook or MCP tool call that can write outside the active project's memory directory.

Out of scope: vulnerabilities in Codex, Claude Code, or Kimi Code themselves — report those to the respective vendor.

## Supported Versions

Only the latest tagged release on the `main` branch receives security fixes. There is no long-term support branch.

## Reporting a Vulnerability

Open a [GitHub Security Advisory](https://github.com/0langa/RECALL/security/advisories/new) on this repository, or a private report to the repository owner if that option isn't available to you. Please do not open a public issue for a suspected vulnerability until a fix has shipped.

Include: the affected version/commit, reproduction steps, and the store backend (SQLite or JSONL) if relevant.

## Data Handling

See [`plugins/recall/docs/PRIVACY.md`](plugins/recall/docs/PRIVACY.md) for what RECALL stores and does not send. RECALL redacts common secret-like patterns at write time and at read time (retrieval and review output); this is a safety net, not a guarantee — do not deliberately store credentials, tokens, or private keys.
