"""Local token accounting for benchmark emissions.

No tokenizer dependency (local-first). Absolute accuracy is secondary; the
estimator only needs to be consistent so version-over-version deltas are
meaningful. `estimate` deliberately over-counts slightly for JSON-ish text:
BPE tokenizers split punctuation-dense content harder than prose.
"""

from __future__ import annotations

import math


def measure(text: str) -> dict[str, int]:
    chars = len(text)
    words = len(text.split())
    return {
        "chars": chars,
        "words": words,
        "est_tokens": estimate(text),
    }


def estimate(text: str) -> int:
    if not text:
        return 0
    return max(len(text.split()), math.ceil(len(text) / 4))


def dollars(est_tokens: int, price_per_million: float) -> float:
    return round(est_tokens / 1_000_000 * price_per_million, 6)


def humanize(est_tokens: float) -> str:
    """Short human form for display next to exact numbers: 10474 -> '10.5k'.

    Reports always keep the exact value; this is presentation sugar only.
    """
    value = float(est_tokens)
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}m".replace(".0m", "m")
    if value >= 1_000:
        return f"{value / 1_000:.1f}k".replace(".0k", "k")
    return str(int(round(value)))


def parse_amount(raw: str | float | int) -> int:
    """Parse '150k', '1.2m', '5M', or plain integers into exact token counts."""
    if isinstance(raw, (int, float)):
        return int(raw)
    text = str(raw).strip().lower().replace("_", "").replace(",", "")
    multiplier = 1
    if text.endswith("k"):
        multiplier, text = 1_000, text[:-1]
    elif text.endswith("m"):
        multiplier, text = 1_000_000, text[:-1]
    return int(float(text) * multiplier)
