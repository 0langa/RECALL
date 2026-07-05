"""Canonical emission-channel taxonomy.

Mirrors token_usage_surfaces.md: every agent-visible byte RECALL can emit is
tagged with exactly one channel so reports can split fixed per-session
overhead from marginal per-turn cost and attribute regressions precisely.
"""

from __future__ import annotations

# Fixed per-session overhead: paid whenever a session starts in an activated
# project, whether or not memory is ever used.
FIXED_CHANNELS = {
    "session_start_context",      # SessionStart hook additionalContext
    "mcp_initialize_instructions",  # MCP initialize handshake `instructions`
    "mcp_tools_list",             # tools/list schemas + descriptions
    "skill_registry_metadata",    # skill names/descriptions/frontmatter
    "skill_body_autoload",        # using-recall auto-load (Kimi sessionStart)
}

# Marginal: emitted per turn / per call, conditional on behavior.
MARGINAL_CHANNELS = {
    "prompt_injection",           # UserPromptSubmit auto memory context
    "prompt_hook_message",        # saved/defined/capture-off/no-project/insufficient messages
    "conflict_alert",             # conflict alert line appended to injections
    "tool_result_retrieve",
    "tool_result_context_packet",
    "tool_result_save",
    "tool_result_update",
    "tool_result_review",
    "tool_result_hygiene",
    "tool_result_contract",
    "tool_result_initialize",
    "tool_result_categories",     # list/define categories
    "tool_result_diagnostics",    # doctor/repair/backup/restore/debug-tail/etc.
    "stop_system_message",        # quiet finalizer "RECALL saved N memories."
    "stop_finalizer_prompt",      # debug-mode block prompt (expensive)
    "hook_error_message",
    "skill_body_invoked",         # SKILL.md loaded on explicit skill activation
}

ALL_CHANNELS = FIXED_CHANNELS | MARGINAL_CHANNELS


def is_fixed(channel: str) -> bool:
    return channel in FIXED_CHANNELS


def validate(channel: str) -> str:
    if channel not in ALL_CHANNELS:
        raise ValueError(f"Unknown emission channel: {channel}")
    return channel
