"""Prompt construction for the RECALL Stop-hook finalizer."""

from __future__ import annotations


def build_finalizer_prompt(packet_path: str) -> str:
    return "\n".join(
        [
            "RECALL_FINALIZER_REQUEST",
            "",
            "Codex must run one memory-finalization pass before ending this turn.",
            "",
            "Read this local RECALL finalizer packet:",
            packet_path,
            "",
            "Constraints:",
            "- Do not edit project source files.",
            "- Only write RECALL memory through the adapter path listed in the packet.",
            "- Use `save-turn-card` for new durable memory cards.",
            "- Store nothing if no durable memory is justified.",
            "- Prefer updating, confirming, superseding, merging, resolving, or pruning existing memories "
            "over creating duplicates.",
            "- Store at most 5 new memory cards.",
            "- Do not store secrets, credentials, tokens, private keys, passwords, or sensitive personal data.",
            "- Keep cards future-useful: decision, requirement, risk, command, architecture, "
            "lesson learned, or project state.",
            "- End after the memory pass; do not continue normal implementation work.",
            "",
            "Required workflow:",
            "1. Read the packet.",
            "2. Review relevant existing memories using the packet adapter.",
            "3. Decide whether any durable memory update is needed.",
            "4. Apply the smallest useful memory changes through the adapter.",
            "5. Reply with a short finalization summary.",
        ]
    )
