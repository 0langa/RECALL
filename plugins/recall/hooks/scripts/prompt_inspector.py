#!/usr/bin/env python3
"""Detect explicit memory/category cues in user prompts."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import _recall_path  # noqa: F401
import capture_policy
from hook_io import additional_context, cwd_from_payload, read_hook_input, root_from_payload
import memory_manager
import config as recall_config
import observability
import project_context
import retrieval
from services import lifecycle_service
import session_context
import turn_buffer


RECALL_INVOKE_RE = re.compile(r"(?i)(\[[^\]]*recall[^\]]*\]\(\s*plugin://recall[^)]*\)|@recall\b|plugin://recall[^\s)]*|\$recall:)")
REMEMBER_RE = re.compile(
    r"(?is)(?:^|\n)\s*(?:please\s+)?remember(?:\s+(?:this|that|the following))?\s*[:\-]\s*(?P<content>.+)"
)
CATEGORY_RE = re.compile(
    r"(?is)\bdefine category\s+(?P<name>[a-zA-Z0-9_-]+)(?:\s*:\s*(?P<description>.+))?"
)
INITIALIZE_RE = re.compile(r"(?i)\binitialize\s+(?:this\s+)?project\b")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    parser.add_argument("--category", default="preferences")
    args = parser.parse_args()
    payload, raw = read_hook_input()
    cwd = cwd_from_payload(payload, args.root)
    resolved_root = root_from_payload(payload, args.root)
    prompt = str(payload.get("prompt") or raw).strip()
    if not prompt:
        print(json.dumps({"continue": True}))
        return
    explicit_recall = bool(RECALL_INVOKE_RE.search(prompt))
    cue_text = RECALL_INVOKE_RE.sub("", prompt).strip() if explicit_recall else prompt
    memory_text = capture_policy.normalize_prompt_memory_text(prompt) if explicit_recall else prompt
    initialize = bool(explicit_recall and INITIALIZE_RE.search(cue_text))
    if initialize and cwd:
        root = str(project_context.resolve_project_root(cwd) or Path(cwd).resolve())
        cfg = recall_config.activate_project(root, activated_by="explicit_initialize")
        observability.trace(root, "project_initialized", {"cwd": cwd, "root": root})
        print(json.dumps(additional_context("UserPromptSubmit", f"RECALL activated for project `{root}`.")))
        return

    root = resolved_root
    if explicit_recall and root is None:
        print(
            json.dumps(
                additional_context(
                    "UserPromptSubmit",
                    "RECALL did not create memory because this folder has no project signal. "
                    "Use `@recall initialize this project` to opt in for a new project.",
                )
            )
        )
        return

    if explicit_recall and root is not None and not recall_config.project_is_active(root):
        recall_config.activate_project(root, activated_by="explicit_recall")

    active = bool(root and recall_config.project_is_active(root))
    if not active:
        print(json.dumps({"continue": True}))
        return

    cfg = recall_config.load_config_if_present(root)
    recall_mode = str(cfg.get("recall_mode", "relevant"))

    session_id = str(payload.get("session_id") or "")
    turn_id = str(payload.get("turn_id") or "")
    turn_buffer.mark_active(root, session_id, turn_id, prompt)
    prompt_event = capture_policy.classify_prompt_event(memory_text or cue_text or prompt)
    if prompt_event is not None:
        turn_buffer.append_event(root, session_id, turn_id, prompt_event)
    observability.trace(
        root,
        "prompt_activation",
        {"explicit": explicit_recall, "session_id": session_id, "turn_id": turn_id, "recall_mode": recall_mode},
    )

    category_match = CATEGORY_RE.search(cue_text) if explicit_recall else None
    if category_match:
        details = memory_manager.define_category(
            category_match.group("name"),
            category_match.group("description"),
            1.0,
            root,
        )
        print(
            json.dumps(
                additional_context(
                    "UserPromptSubmit",
                    f"RECALL defined category `{category_match.group('name')}`: {details['description']}",
                )
            )
        )
        return

    remember_match = REMEMBER_RE.search(cue_text) if explicit_recall else None
    if remember_match:
        remembered = remember_match.group("content").strip()
        record = memory_manager.add_record(
            args.category,
            remembered,
            memory_manager.build_card_metadata(
                summary=remembered[:220],
                source="prompt_inspector",
                status="active",
            ),
            root,
        )
        print(
            json.dumps(
                additional_context(
                    "UserPromptSubmit",
                    f"RECALL saved memory #{record.id} in `{record.category}`.",
                )
            )
        )
        return

    retrieval_text = memory_text or cue_text or prompt
    exclusions = capture_policy.retrieval_exclusions(retrieval_text)
    assessment = retrieval.assess_relevance(
        retrieval_text,
        root=root,
        exclude_categories=exclusions,
        statuses=["validated", "active", "open", "resolved"],
    )
    should_retrieve = recall_mode == "always" or (recall_mode == "relevant" and assessment["relevant"])
    if explicit_recall:
        should_retrieve = True
    observability.trace(root, "retrieval_gate", {**assessment, "excluded_categories": exclusions})

    if should_retrieve and capture_policy.persistent_memory_exists(root):
        context = session_context.build_session_context(root, retrieval_text, 8, exclude_categories=exclusions)
        conflicts = lifecycle_service.find_conflicts(root)
        if conflicts:
            context = (context + "\nRECALL alert: unresolved current-truth conflicts require review.").strip()
        if context:
            print(json.dumps(additional_context("UserPromptSubmit", context)))
            return

    if explicit_recall and not assessment["sufficient"]:
        print(json.dumps(additional_context("UserPromptSubmit", "RECALL does not contain enough relevant memory for this request.")))
        return

    print(json.dumps({"continue": True}))


if __name__ == "__main__":
    main()
