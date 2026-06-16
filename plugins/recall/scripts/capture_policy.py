#!/usr/bin/env python3
"""Capture-mode and deterministic auto-capture policy helpers."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import config as recall_config


AUTO_CAPTURE_MODES = {"minimal", "standard"}
READ_ONLY_COMMAND_RE = re.compile(
    r"(?i)^\s*(?:Get-Content|Get-ChildItem|Select-String|Select-Object|Get-Location|"
    r"rg\b|git\s+status\b|git\s+log\b|git\s+show\b|dir\b|ls\b|pwd\b|cat\b|type\b|"
    r"review-memory\b|retrieve-memory\b|archive-noise\b)"
)
TEST_COMMAND_RE = re.compile(r"(?i)\b(pytest|unittest|npm\s+test|pnpm\s+test|yarn\s+test|go\s+test|cargo\s+test)\b")
BUILD_COMMAND_RE = re.compile(
    r"(?i)\b(build|build_plugin|inspect_package|smoke_recall|validate_plugin|package)\b"
)
GIT_STATE_CHANGE_RE = re.compile(
    r"(?i)^\s*git\s+(commit|switch|checkout|merge|rebase|tag|push|pull|cherry-pick)\b"
)
RELEASE_COMMAND_RE = re.compile(r"(?i)\b(codex\s+plugin|release|marketplace|dist/|recall\.zip)\b")
FAILURE_RE = re.compile(r"(?i)\b(error|exception|traceback|failed|failure|assertionerror)\b")
TEST_SUMMARY_RE = re.compile(r"(?im)^(Ran\s+\d+\s+tests?.*|.*\b\d+\s+passed\b.*|.*\b0 failures\b.*)$")
BUILD_SUMMARY_RE = re.compile(r"(?im)^(.*\b(status|build|package|smoke)\b.*\b(pass|passed|success|succeeded|ok)\b.*)$")
EXIT_CODE_RE = re.compile(r"(?i)\bexit[_ ]code:\s*(-?\d+)\b")
STOP_DURABLE_RE = re.compile(
    r"(?i)\b("
    r"implemented|changed|fixed|verified|tested|built|released|"
    r"commit|branch|push|pull request|pr\b|tag|artifact|"
    r"requirement|decision|risk|blocker|next step|architecture|"
    r"memory|recall|hook|plugin"
    r")\b"
)
PROMPT_REQUIREMENT_RE = re.compile(r"(?i)\b(must|need to|required|acceptance criteria|do not|never)\b")
PROMPT_DECISION_RE = re.compile(r"(?i)\b(decided|we will|use .+ instead|approved|accepted)\b")
PROMPT_CORRECTION_RE = re.compile(r"(?i)\b(correction|actually|instead|no longer|replace|supersede)\b")
COMMAND_QUERY_RE = re.compile(r"(?i)\b(build|test|run|command|install|lint|format|deploy|package|tooling)\b")
PLUGIN_MENTION_RE = re.compile(r"(?i)\[[^\]]*recall[^\]]*\]\(\s*plugin://recall[^)]*\)")
RAW_PLUGIN_RE = re.compile(r"(?i)\bplugin://recall[^\s)]*")
RECALL_TOKEN_RE = re.compile(r"(?i)(?:@recall\b|\$recall:)")
RECALL_ACTIVATION_SENTENCE_RE = re.compile(
    r"(?i)^\s*(?:please\s+)?(?:use|enable|activate)\s+recall(?:\s+(?:for|in|on)\s+(?:this\s+)?(?:project|repo|repository|folder|workspace))?\s*[.!?:;-]*\s*"
)
ORPHANED_ACTIVATION_SENTENCE_RE = re.compile(
    r"(?i)^\s*(?:please\s+)?use\s+(?:for|in|on)\s+(?:this\s+)?(?:project|repo|repository|folder|workspace)\s*[.!?:;-]*\s*"
)
LEADING_MEMORY_PHRASE_RE = re.compile(r"(?i)^\s*(?:remember\s+(?:this|that)\s*[:\-]\s*)")


@dataclass(frozen=True)
class CaptureDecision:
    category: str
    signal: str
    summary: str
    details: str
    tags: list[str]
    importance: float
    confidence: float
    record_kind: str
    auto_capture_policy: str


def capture_mode(root: str | None = None) -> str:
    return str(recall_config.load_config_if_present(root).get("capture_mode", "minimal"))


def persistent_memory_exists(root: str | None = None) -> bool:
    return recall_config.persistent_memory_exists(root)


def auto_capture_allowed(root: str | None = None) -> bool:
    return capture_mode(root) in AUTO_CAPTURE_MODES


def should_activate_turn(
    root: str | None = None,
    *,
    explicit_write: bool = False,
) -> bool:
    mode = capture_mode(root)
    if explicit_write:
        return True
    if mode not in AUTO_CAPTURE_MODES:
        return False
    return persistent_memory_exists(root)


def exit_code(payload: dict[str, Any], output: str) -> int | None:
    response = payload.get("tool_response")
    if isinstance(response, dict):
        value = response.get("exit_code")
        if isinstance(value, int):
            return value
    match = EXIT_CODE_RE.search(output)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def cleaned_lines(output: str) -> list[str]:
    return [line.strip() for line in output.splitlines() if line.strip()]


def first_matching_line(lines: list[str], pattern: re.Pattern[str]) -> str | None:
    for line in lines:
        if pattern.search(line):
            return line.strip()
    return None


def failure_summary(command: str, lines: list[str]) -> str:
    line = first_matching_line(lines, FAILURE_RE)
    if line:
        return line[:220]
    command_text = command or "command"
    return f"Command failed: {command_text}"[:220]


def success_summary(command: str, lines: list[str], *, test: bool = False, build: bool = False) -> str:
    if test:
        line = first_matching_line(lines, TEST_SUMMARY_RE)
        if line:
            return line[:220]
        return f"Tests passed: {command}"[:220]
    if build:
        line = first_matching_line(lines, BUILD_SUMMARY_RE)
        if line:
            return line[:220]
        return f"Build or verification passed: {command}"[:220]
    return f"State-changing command succeeded: {command}"[:220]


def classify_tool_capture(
    *,
    root: str | None,
    payload: dict[str, Any],
    tool_name: str,
    command: str,
    content: str,
    patch_targets: list[str] | None = None,
    mode: str | None = None,
) -> CaptureDecision | None:
    mode = mode or capture_mode(root)
    if mode not in AUTO_CAPTURE_MODES:
        return None

    command = command.strip()
    code = exit_code(payload, content)
    lines = cleaned_lines(content)
    lower_tool = tool_name.lower()

    if tool_name == "apply_patch":
        targets = ", ".join((patch_targets or [])[:6]) or "unknown files"
        return CaptureDecision(
            category="commands",
            signal="file_patch",
            summary=f"Edited file(s): {targets}"[:220],
            details=content,
            tags=["tool-use", "apply_patch", "file-edit", "patch"],
            importance=0.72,
            confidence=0.9,
            record_kind="file_edit",
            auto_capture_policy="file_edit",
        )

    if READ_ONLY_COMMAND_RE.search(command):
        if code is None or code == 0:
            return None
        return CaptureDecision(
            category="debug_history",
            signal="read_failure",
            summary=failure_summary(command, lines),
            details=content,
            tags=["tool-use", lower_tool or "tool", "failure", "read-only"],
            importance=0.7,
            confidence=0.9,
            record_kind="failure",
            auto_capture_policy="failure",
        )

    if code is not None and code != 0:
        is_test = bool(TEST_COMMAND_RE.search(command))
        return CaptureDecision(
            category="debug_history",
            signal="test_fail" if is_test else "error_root_cause",
            summary=failure_summary(command, lines),
            details=content,
            tags=["tool-use", lower_tool or "tool", "failure", *(["tests"] if is_test else [])],
            importance=0.85 if is_test else 0.8,
            confidence=0.92,
            record_kind="failure",
            auto_capture_policy="failure",
        )

    is_test = bool(TEST_COMMAND_RE.search(command))
    if is_test:
        return CaptureDecision(
            category="commands",
            signal="test_pass",
            summary=success_summary(command, lines, test=True),
            details=content,
            tags=["tool-use", lower_tool or "tool", "tests"],
            importance=0.7,
            confidence=0.88,
            record_kind="test_result",
            auto_capture_policy="test_result",
        )

    is_build = bool(BUILD_COMMAND_RE.search(command) or RELEASE_COMMAND_RE.search(command))
    if is_build:
        return CaptureDecision(
            category="commands",
            signal="build_pass",
            summary=success_summary(command, lines, build=True),
            details=content,
            tags=["tool-use", lower_tool or "tool", "build"],
            importance=0.68,
            confidence=0.86,
            record_kind="build_result",
            auto_capture_policy="build_result",
        )

    if GIT_STATE_CHANGE_RE.search(command):
        return CaptureDecision(
            category="project_state",
            signal="git_state_change",
            summary=success_summary(command, lines),
            details=content,
            tags=["tool-use", lower_tool or "tool", "git", "state-change"],
            importance=0.72,
            confidence=0.84,
            record_kind="state_change",
            auto_capture_policy="state_change",
        )

    if mode == "standard" and command:
        return CaptureDecision(
            category="commands",
            signal="state_change",
            summary=success_summary(command, lines),
            details=content,
            tags=["tool-use", lower_tool or "tool", "command"],
            importance=0.55,
            confidence=0.75,
            record_kind="state_change",
            auto_capture_policy="state_change",
        )

    return None


def should_store_precompact(root: str | None = None) -> bool:
    return capture_mode(root) == "standard"


def should_store_stop_note(root: str | None, note: str) -> bool:
    mode = capture_mode(root)
    if mode not in AUTO_CAPTURE_MODES:
        return False
    return bool(note.strip()) and bool(STOP_DURABLE_RE.search(note))


def retrieval_exclusions(prompt: str) -> list[str]:
    return [] if COMMAND_QUERY_RE.search(prompt) else ["commands"]


def normalize_prompt_memory_text(prompt: str) -> str:
    clean = " ".join(prompt.split())
    if not clean:
        return ""
    clean = PLUGIN_MENTION_RE.sub(" ", clean)
    clean = RAW_PLUGIN_RE.sub(" ", clean)
    clean = RECALL_TOKEN_RE.sub(" ", clean)
    clean = re.sub(r"(?i)\brecall-local\b", " ", clean)
    clean = re.sub(r"\[\s*\]\([^)]*\)", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip(" \t\r\n-:;,.")
    clean = RECALL_ACTIVATION_SENTENCE_RE.sub("", clean).strip(" \t\r\n-:;,.")
    clean = ORPHANED_ACTIVATION_SENTENCE_RE.sub("", clean).strip(" \t\r\n-:;,.")
    clean = LEADING_MEMORY_PHRASE_RE.sub("", clean).strip(" \t\r\n-:;,.")
    return clean


def classify_prompt_event(prompt: str) -> dict[str, Any] | None:
    clean = normalize_prompt_memory_text(prompt)
    if not clean:
        return None
    if PROMPT_CORRECTION_RE.search(clean):
        category = "decisions"
        signal = "explicit_correction"
    elif PROMPT_REQUIREMENT_RE.search(clean):
        category = "requirements"
        signal = "explicit_requirement"
    elif PROMPT_DECISION_RE.search(clean):
        category = "decisions"
        signal = "explicit_decision"
    else:
        return None
    return {
        "durable_candidate": True,
        "signal": signal,
        "summary": clean[:220],
        "details": clean[:1200],
        "category_hint": category,
        "tags": ["user-prompt", signal.replace("explicit_", "")],
        "explicit_user_evidence": True,
    }
