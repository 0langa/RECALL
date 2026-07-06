"""Secret redaction shared by every persistence and export path."""

from __future__ import annotations

import re
from typing import Any


SECRET_PATTERNS = [
    # keyword followed by : or =
    re.compile(r"(?i)(api[_-]?key|access[_-]?key|secret[_-]?key|token|password|passwd|secret|bearer|authorization)\s*[:=]\s*['\"]?[^'\"\s]+"),
    # keyword followed by "is" / "was" / "=" style verbal assignment
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?key|secret[_-]?key|token|password|passwd|secret)\b\s+(?:is|was|=|:)\s+['\"]?\S{8,}"),
    # OpenAI project / user keys
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    # AWS access key ID
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    # AWS secret access key (40 chars base64-ish, at least one digit + one letter)
    re.compile(r"\b(?=[A-Za-z0-9/+]*[A-Za-z])(?=[A-Za-z0-9/+]*[0-9])[A-Za-z0-9/+]{40}\b"),
    # JWT: three base64url segments joined by dots (min 4/4/4)
    re.compile(r"\beyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\b"),
    # GitHub / GitLab tokens
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|glpat)_[A-Za-z0-9]{20,}\b"),
    # Private key blocks
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----"),
]

# Values that make the keyword=value patterns above match ordinary source
# code (type annotations, slice reassignment) rather than a real secret.
_NOT_A_SECRET_VALUE = {
    "str", "int", "float", "bool", "bytes", "list", "dict", "set", "tuple",
    "any", "none", "object", "optional", "callable",
}
_SEPARATOR_RE = re.compile(r"^\s*(?:is|was|[:=])\s*")


def _is_plausible_secret(match: "re.Match[str]") -> bool:
    """Filter type-annotation and self-reassignment false positives (a bare
    "token" parameter typed as a builtin, or reassigned from itself) out of
    the first two keyword-based patterns; every other pattern is
    structurally specific enough (sk-, AKIA, JWT shape, ...) to trust as-is.
    """
    if match.lastindex is None:
        return True
    keyword = match.group(1)
    remainder = match.group(0)[match.end(1) - match.start(0):]
    value = _SEPARATOR_RE.sub("", remainder, count=1).strip("'\"")
    value = re.split(r"[,);\s]", value, maxsplit=1)[0]
    if not value:
        return False
    if value.lower() in _NOT_A_SECRET_VALUE:
        return False
    if value.lower().startswith(keyword.lower()):
        return False
    return True


def _first_plausible_match(pattern: "re.Pattern[str]", text: str) -> "re.Match[str] | None":
    for match in pattern.finditer(text):
        if _is_plausible_secret(match):
            return match
    return None


def redact_text(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: "[REDACTED]" if _is_plausible_secret(match) else match.group(0), redacted)
    return redacted


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {str(key): redact_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(item) for item in value]
    return value


def contains_secret(*values: str | None) -> bool:
    for value in values:
        if not value:
            continue
        if any(_first_plausible_match(pattern, value) is not None for pattern in SECRET_PATTERNS):
            return True
    return False
