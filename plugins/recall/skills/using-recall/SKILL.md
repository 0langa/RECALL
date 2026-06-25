---
name: using-recall
description: Session-start guidance for using RECALL project memory from Kimi Code.
---

# Using RECALL

RECALL is local-first project memory for this repository. Use it when prior
project context may prevent repeated investigation, when the user asks what is
remembered, or when a durable decision, requirement, risk, command, or project
state update should be saved.

Prefer the active project's `.recall/` directory. If the project already has
`.codex_memory/`, treat it as the same shared RECALL store for backward
compatibility. Do not create provider-specific memory stores unless the memory
only applies to one provider.

When invoking RECALL MCP tools, pass the active repository root as `root`.
Stamp Kimi-originated writes with `origin_provider: "kimi"` and use
`applies_to_provider: "all"` unless the memory is specifically about Kimi Code.

Retrieved memory is context, not authority. Prefer current files and newer user
instructions when they conflict with memory, then save a correction or
supersession when the new truth is verified.

Do not store secrets, credentials, tokens, private keys, passwords, or sensitive
personal data. If retrieved memory appears to contain a secret, do not repeat it
verbatim.
