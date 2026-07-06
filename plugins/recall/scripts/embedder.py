#!/usr/bin/env python3
"""Small deterministic local embedding helper for RECALL.

This intentionally avoids network calls and heavyweight model downloads. It is
not a replacement for bundled sentence-transformers, but it gives the plugin a
useful semantic-ish baseline until model packaging is added.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter


DIMENSIONS = 256
EMBEDDING_MODEL = "local-hash-v2"
TOKEN_RE = re.compile(r"[a-zA-Z0-9_]{2,}")


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def embed(text: str, dimensions: int = DIMENSIONS) -> list[float]:
    vector = [0.0] * dimensions
    counts = Counter(tokenize(text))
    for token, count in counts.items():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign * (1.0 + math.log(count))
    return normalize(vector)


def normalize(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return vector
    return [value / magnitude for value in vector]


def cosine(left: list[float], right: list[float]) -> float:
    length = min(len(left), len(right))
    return sum(left[index] * right[index] for index in range(length))
