#!/usr/bin/env python3
"""Capture-mode and deterministic auto-capture policy helpers."""

from __future__ import annotations

from dataclasses import dataclass
import re
import shlex
from typing import Any

import config as recall_config


# capture_mode contract (enforced here, not in agent instructions):
#   standard: full automatic capture — per-tool evidence, prompt signals,
#             stop notes, and session summaries.
#   minimal:  no per-tool evidence buffering (PostToolUse is off); prompt
#             signals, stop notes, and session summaries still run.
#   manual:   only explicit cues (@recall / remember this) and skill/MCP
#             saves; no automatic hook capture at all.
#   off:      no hook capture of any kind, including explicit prompt cues;
#             hooks only read. Skill and MCP saves remain available because
#             they are explicit agent/user actions, not background capture.
# Retrieval/injection is governed separately by recall_mode.
AUTO_CAPTURE_MODES = {"minimal", "standard"}
TOOL_CAPTURE_MODES = {"standard"}
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
BUILD_SUMMARY_RE = re.compile(r"(?im)^(.*\b(status|build|package|smoke)\b.*\b(pass|passed|success|successfully|succeeded|ok)\b.*)$")
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
INFORMATION_REQUEST_RE = re.compile(
    r"(?i)(\?|"
    r"\b(?:what|which|how|why|where|when|who|summarize|explain|check\s+what|look\s+up|find\s+out)\b)"
)
RELEASE_CONTEXT_RE = re.compile(r"(?i)\b(release|tag|branch policy|requirement|requirements|constraint|constraints|policy)\b")
EXECUTION_ONLY_RE = re.compile(
    r"(?i)^\s*(?:ok(?:ay)?\s+)?(?:"
    r"run\b.*\b(?:test|tests|unit tests|integration suite|pytest|suite)\b|"
    r"apply\b.*\b(?:fix|patch)\b.*\b(?:rerun|run)\b|"
    r"rerun\b|"
    r"execute\b.*\b(?:test|tests|suite|pytest)\b"
    r")"
)
CONDITIONAL_COMMAND_MEMORY_RE = re.compile(
    r"(?is)\bremember\b.+\bonly\s+if\b.+\b(?:works?|passes?|succeeds?|success|actually\s+works?)\b|"
    r"\bonly\s+remember\b.+\bif\b.+\b(?:works?|passes?|succeeds?|success|actually\s+works?)\b|"
    r"\bremember\b.+\bif\s+(?:it|that|the\s+command)\s+(?:actually\s+)?(?:works?|passes?|succeeds?)\b"
)
RELEASE_NOTES_PATH_RE = re.compile(r"(?i)\brelease\s+notes?\b.*?\b(?:docs|doc)[\\/][A-Za-z0-9_.\\/-]+\.md\b")
MARKDOWN_PATH_RE = re.compile(r"(?i)\b(?:docs|doc)[\\/][A-Za-z0-9_.\\/-]+\.md\b")
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
TRANSIENT_TASK_CONTROL_RE = re.compile(
    r"(?i)\b("
    r"run\s+(?:exactly\s+)?(?:this\s+)?(?:shell\s+)?command|"
    r"execute\s+(?:exactly\s+)?(?:this\s+)?(?:shell\s+)?command|"
    r"use\s+(?:shell|bash)\s+only|"
    r"do\s+not\s+(?:call|use)\s+(?:recall\s+)?(?:mcp|tools?|skills?)|"
    r"reply\s+(?:only|with|in)\b"
    r")\b"
)
# Admission concerns the user's asserted project facts, not isolated keywords.
# These deliberately conservative English rules are not a semantic classifier.
PROJECT_SUBJECT_RE = re.compile(
    r"(?i)\b(project|repo(?:sitory)?|release|notes|policy|requirement|constraint|"
    r"api|app(?:lication)?|service|backend|storage|database|sqlite|jsonl|code|plugin|hook|"
    r"finalizer|retry|build|schema|config(?:uration)?|memory|tests?|parser|"
    r"network|credentials|dependencies|runtime)\b"
)
FACT_PREDICATE_RE = re.compile(
    r"(?i)\b(is|are|was|were|uses?|lives?|stays?|belongs?|requires?|must|"
    r"supports?|keeps?|runs?|moved|decided|approved|accepted|prefer|should\s+instead)\b"
)
UNRESOLVED_PROMPT_RE = re.compile(
    r"(?i)\b(maybe|perhaps|possibly|probably|might|could|would|whether|"
    r"unsure|uncertain|not\s+sure|no\s+idea|wonder|propos(?:e|al|ed)|"
    r"consider(?:ing)?|hypothetical|pending\s+approval|not\s+(?:yet\s+)?(?:decided|approved|accepted)|"
    r"haven['’]t\s+(?:decided|approved|accepted)|let['’]s|let\s+us|suggest(?:ion|ed)?|"
    r"recommend(?:ation)?|we\s+should|if\s+we|if\s+the\s+project)\b"
)
PROMPT_FRAME_RE = re.compile(
    r"(?i)^\s*(?:(?:here\s+(?:is|are)|this\s+is|these\s+are|the\s+following\s+(?:is|are))\s+)?(?:an?\s+)?"
    r"(?:examples?(?:\s+(?:text|instructions?))?|quoted?(?:\s+(?:text|instructions?))?|proposals?|hypothetical)\b"
)
TRANSIENT_SCOPE_RE = re.compile(
    r"(?i)\b(?:for\s+(?:this|the\s+next|one)\s+(?:task|turn|reply|response|session)|"
    r"this\s+(?:task|turn|reply|response|session)|next\s+(?:turn|reply|response|session)\s+only|future\s+interview)\b"
)
# Conditional plans have no faithful current-truth state in the card schema.
# Admit a small, explicit runtime-rule form; abstain on conditional choices.
PROMPT_CONDITION_RE = re.compile(r"(?i)\b(?:if|unless|provided\s+that|subject\s+to)\b")
CHOICE_CONDITION_RE = re.compile(r"(?i)\b(?:approv\w*|accept\w*|decid\w*|adopt\w*|benchmarks?)\b")
RUNTIME_RULE_RE = re.compile(
    r"(?i)\b(?:api|app(?:lication)?|service|parser|runtime|hook)\s+must\s+(?:not\s+)?"
    r"(?:return|reject|raise|retry|emit|preserve)\b"
)
FRAME_END_RE = re.compile(r"(?i)^\s*end\s+(?:of\s+)?(?:the\s+)?(?:examples?|quotes?|proposals?)\s*[.:]?\s*$")
DURABLE_CORRECTION_RE = re.compile(
    r"(?i)\b(?:uses?|requires?|lives?|belongs?|stays?|stores?|supports?|"
    r"targets?|defaults?\s+to|keeps?|moved|replace|supersede)\b"
)
QUESTION_START_RE = re.compile(
    r"(?i)^\s*(?:(?:actually|correction|instead|so|but|and)\s*[:,]?\s*)*"
    r"(?:what|which|how|why|where|when|who|is|are|was|were|do(?!\s+not\b)|does|did|"
    r"can|could|should|would|will|have|has|explain|tell\s+me|find\s+out)\b"
)
TURN_OUTPUT_RE = re.compile(
    r"(?i)\b(?:you\s+must\s+)?(?:answer|respond|reply|output|print)\b.*"
    r"\b(?:only|json|sentence|bullet|format|question|response)\b"
)


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


def material_command_kind(command: str) -> str | None:
    """Accept a material executable/argument shape, never a keyword in echo text."""
    try:
        words = shlex.split(command, posix=False)
    except ValueError:
        return None
    if not words:
        return None
    executable = words[0].strip("\"'").replace("\\", "/").rsplit("/", 1)[-1].lower().removesuffix(".exe")
    arguments = [word.strip("\"'").lower() for word in words[1:]]
    args = " ".join(arguments)
    if executable in {"python", "python3", "py"}:
        script = arguments[0].replace("\\", "/").rsplit("/", 1)[-1] if arguments else ""
        if (len(arguments) >= 2 and arguments[0] == "-m" and arguments[1] in {"pytest", "unittest"}) or script == "run_tests.py":
            return "test"
        if script in {"build_plugin.py", "smoke_recall.py", "inspect_package.py", "validate_plugin.py"}:
            return "build"
    if executable in {"pytest", "unittest"}:
        return "test"
    if executable in {"npm", "pnpm", "yarn", "cargo", "go", "dotnet"}:
        if re.match(r"(?:run\s+)?test\b", args):
            return "test"
        if re.match(r"(?:run\s+)?(?:build|pack|publish)\b", args):
            return "build"
    if executable == "gh" and re.match(r"release\s+(?:create|upload)\b", args):
        return "release"
    return None


def observed_material_success(command: str, response: dict[str, Any]) -> bool:
    kind = material_command_kind(command)
    code = response.get("exit_code")
    if kind is None or type(code) is not int or code != 0 or response.get("success") is False:
        return False
    output = "\n".join(str(response.get(key) or "") for key in ("stdout", "stderr", "output", "message"))
    if not output.strip():
        return False
    if kind == "test":
        return bool(re.search(r"(?im)(\b\d+\s+passed\b|^Ran\s+\d+\s+tests?\b|\b0 failures\b|\"passed\"\s*:\s*true)", output)) and not bool(re.search(r"(?i)\b(?:[1-9]\d*\s+failed|FAILED\s*\()", output))
    if kind == "release":
        return bool(re.search(r"(?i)(https://\S+/releases/|\brelease\b.*\b(?:created|uploaded|published|success)\b)", output))
    return bool(BUILD_SUMMARY_RE.search(output) or re.search(r'(?i)"(?:passed|success)"\s*:\s*true', output))


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
    if mode not in TOOL_CAPTURE_MODES:
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

    response = payload.get("tool_response")
    if not isinstance(response, dict) or not observed_material_success(command, response):
        return None

    is_test = material_command_kind(command) == "test"
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

    is_build = material_command_kind(command) in {"build", "release"}
    if is_build:
        return CaptureDecision(
            category="commands",
            signal="release_pass" if material_command_kind(command) == "release" else "build_pass",
            summary=success_summary(command, lines, build=True),
            details=content,
            tags=["tool-use", lower_tool or "tool", "build"],
            importance=0.68,
            confidence=0.86,
            record_kind="build_result",
            auto_capture_policy="build_result",
        )

    return None


def should_store_precompact(root: str | None = None) -> bool:
    return capture_mode(root) in AUTO_CAPTURE_MODES


def explicit_capture_allowed(root: str | None = None) -> bool:
    """Explicit prompt cues (remember this / define category) work in every
    mode except off; off means hooks never write."""
    return capture_mode(root) != "off"


def should_store_stop_note(root: str | None, note: str) -> bool:
    mode = capture_mode(root)
    if mode not in AUTO_CAPTURE_MODES:
        return False
    return bool(note.strip()) and bool(STOP_DURABLE_RE.search(note))


def retrieval_exclusions(prompt: str) -> list[str]:
    return [] if COMMAND_QUERY_RE.search(prompt) else ["commands"]


def suppress_auto_retrieval(prompt: str) -> bool:
    """Skip memory injection for execution-only prompts.

    RECALL should not spend tokens on context for plain "run/rerun tests" or
    "apply the fix" turns. Questions and release/requirement/policy prompts
    can still benefit from memory; explicit @recall bypasses this in the hook.
    """
    clean = normalize_prompt_memory_text(prompt)
    if not clean:
        return False
    if INFORMATION_REQUEST_RE.search(clean) or RELEASE_CONTEXT_RE.search(clean):
        return False
    return bool(EXECUTION_ONLY_RE.search(clean))


def no_memory_requested(prompt: str) -> bool:
    """Match task controls outside quotes/examples; do this before any capture."""
    text = unquoted_prompt_text(prompt)
    return bool(re.search(
        r"(?i)\b(?:no[- ]memory|without\s+(?:using\s+)?memory|(?:do\s+not|don['’]t|never)\s+"
        r"(?:(?:read|write|use|save|store|capture|retrieve|access|consult|load|inject)\b[\w\s,/&-]{0,45})"
        r"(?:memory|\.?recall)\b|(?:disable|skip|avoid)\s+(?:all\s+)?(?:memory|\.?recall)\b)", text))


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


def claim_metadata(category: str, text: str) -> dict[str, str]:
    normalized_category = recall_config.normalize_category(category)
    if normalized_category not in {"requirements", "constraints", "decisions"}:
        return {}
    if not RELEASE_NOTES_PATH_RE.search(text):
        return {}
    path_match = MARKDOWN_PATH_RE.search(text)
    if not path_match:
        return {}
    return {
        "claim_key": "release_notes.path",
        "claim_value": path_match.group(0).replace("\\", "/"),
    }


def unquoted_prompt_text(prompt: str) -> str:
    """Keep prose boundaries; quoted examples and fenced blocks are not user assertions.

    A line with prose quotation marks is omitted as a unit, avoiding accidental
    adoption of a quoted instruction or joining text across an omitted span.
    Inline code remains usable for factual paths and literal values.
    """
    lines: list[str] = []
    fence = ""
    quoted = False
    for line in prompt.splitlines():
        stripped = line.lstrip()
        marker = re.match(r"(`{3,}|~{3,})", stripped)
        if marker:
            token = marker.group(0)
            if not fence:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = ""
            lines.append("")
            continue
        if fence:
            continue
        prose = re.sub(r"`[^`]*`", "", line)
        marks = re.findall(r'''["“”]|(?<!\w)['‘]|['’](?!\w)''', prose)
        if marks or quoted or stripped.startswith(">"):
            if len(marks) % 2:
                quoted = not quoted
            lines.append("")
            continue
        lines.append(line)
    return _unframed_prompt_text("\n".join(lines))


def _unframed_prompt_text(prompt: str) -> str:
    """Keep example headings attached to their bodies, including blank lines.

    A plain frame lasts until an explicit end or a new Markdown section. A
    Markdown frame also includes its nested sections. Ambiguous scope abstains.
    This runs before explicit cue detection as well as automatic admission.
    """
    lines: list[str] = []
    frame_level: int | None = None
    for line in prompt.splitlines():
        heading = re.match(r"^\s*(#{1,6})\s+(.+)", line)
        if frame_level is not None:
            if FRAME_END_RE.fullmatch(line):
                frame_level = None
                lines.append("")
                continue
            if heading and (frame_level == 0 or len(heading[1]) <= frame_level):
                frame_level = None
            else:
                lines.append("")
                continue
        if PROMPT_FRAME_RE.search(heading[2] if heading else line):
            frame_level = len(heading[1]) if heading else 0
            lines.append("")
        else:
            # Headings delimit example scope above; labels are not assertions.
            lines.append("" if heading else line)
    return "\n".join(lines)


def _uncommitted_prompt_condition(syntax: str) -> bool:
    conditions = list(PROMPT_CONDITION_RE.finditer(syntax))
    if not conditions:
        return False
    if not RUNTIME_RULE_RE.search(syntax):
        return True
    # Even a runtime-shaped consequent can depend on a future approval gate.
    # For leading conditions the comma ends the condition, not the assertion.
    return any(CHOICE_CONDITION_RE.search(syntax[m.end():].split(",", 1)[0]) for m in conditions)


def accepted_prompt_statements(prompt: str, *, preserve_punctuation: bool = False) -> list[str]:
    """Extract separable assertions without carrying questions or task controls.

    Example scope survives paragraph boundaries. Conditional choices cannot
    become current policy; explicit runtime rules retain their condition.
    """
    accepted: list[str] = []
    for paragraph in re.split(r"\n\s*\n", unquoted_prompt_text(prompt)):
        if PROMPT_FRAME_RE.search(paragraph) or re.match(
            r"(?i)^\s*(?:(?:actually|correction)\s*[:,]?\s*)?"
            r"(?:suppose|imagine|maybe|perhaps|let['’]s|let\s+us|we\s+could|i\s+suggest)\b", paragraph
        ):
            continue
        # Preserve offsets instead of replacing user text with restorable tokens.
        masked = re.sub(r"`[^`]*`", lambda match: "x" * len(match.group(0)), paragraph)
        # Line-based statements cannot safely detach either side of a wrapped
        # condition. Keep the paragraph uncommitted when its scope is unclear.
        if "\n" in masked.strip() and PROMPT_CONDITION_RE.search(masked):
            continue
        start = 0
        for boundary in re.finditer(r"(?<=[.!?])\s+|\n+", masked + "\n"):
            sentence = paragraph[start:boundary.start()]
            syntax = normalize_prompt_memory_text(masked[start:boundary.start()])
            start = boundary.end()
            if not syntax or re.search(r"\?(?:\s|$)", syntax) or QUESTION_START_RE.search(syntax):
                continue
            if (UNRESOLVED_PROMPT_RE.search(syntax) or TRANSIENT_TASK_CONTROL_RE.search(syntax)
                    or TURN_OUTPUT_RE.search(syntax) or TRANSIENT_SCOPE_RE.search(syntax)
                    or CONDITIONAL_COMMAND_MEMORY_RE.search(syntax)
                    or _uncommitted_prompt_condition(syntax)):
                continue
            # A correction marker alone cannot make transient observations into decisions.
            if not FACT_PREDICATE_RE.search(syntax) and not PROMPT_REQUIREMENT_RE.search(syntax):
                continue
            clean = normalize_prompt_memory_text(sentence)
            if preserve_punctuation and sentence.rstrip().endswith((".", "!")):
                clean += sentence.rstrip()[-1]
            accepted.append(clean)
    return accepted


def _classify_prompt_statement(clean: str) -> dict[str, Any] | None:
    if not PROJECT_SUBJECT_RE.search(clean):
        return None
    requirement_claim = claim_metadata("requirements", clean)
    if PROMPT_CORRECTION_RE.search(clean):
        if not (requirement_claim or PROMPT_REQUIREMENT_RE.search(clean)
                or PROMPT_DECISION_RE.search(clean) or DURABLE_CORRECTION_RE.search(clean)):
            return None
        category = "requirements" if requirement_claim else "decisions"
        signal = "explicit_correction"
    elif PROMPT_REQUIREMENT_RE.search(clean):
        category = "requirements"
        signal = "explicit_requirement"
    elif PROMPT_DECISION_RE.search(clean):
        category = "decisions"
        signal = "explicit_decision"
    else:
        return None
    event = {
        "durable_candidate": True,
        "signal": signal,
        "summary": clean[:220],
        "details": clean[:1200],
        "category_hint": category,
        "tags": ["user-prompt", signal.replace("explicit_", "")],
        "explicit_user_evidence": True,
    }
    event.update(requirement_claim if category == "requirements" and requirement_claim else claim_metadata(category, clean))
    return event


def classify_prompt_event(prompt: str) -> dict[str, Any] | None:
    # Keep a single coherent category in the existing one-event prompt contract.
    # Ambiguous or differently categorized trailing clauses are not bundled into it.
    event: dict[str, Any] | None = None
    statements: list[str] = []
    for statement in accepted_prompt_statements(prompt):
        candidate = _classify_prompt_statement(statement)
        if candidate is None:
            continue
        if event is None:
            event = candidate
        if candidate["category_hint"] == event["category_hint"]:
            statements.append(statement)
    if event is not None:
        text = ". ".join(statements)
        event.update(summary=text[:220], details=text[:1200])
    return event
