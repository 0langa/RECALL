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
