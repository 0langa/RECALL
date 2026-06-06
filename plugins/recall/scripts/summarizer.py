#!/usr/bin/env python3
"""Heuristic summarization for RECALL retrieval results."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable

from embedder import tokenize


SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))


def trim_to_budget(text: str, token_budget: int) -> str:
    words = text.split()
    if len(words) <= token_budget:
        return text
    return " ".join(words[:token_budget])


def summarize_texts(texts: Iterable[str], token_budget: int = 1200) -> str:
    token_budget = max(1, token_budget)
    sentences: list[str] = []
    for text in texts:
        sentences.extend(sentence.strip() for sentence in SENTENCE_RE.split(text) if sentence.strip())
    if not sentences:
        return ""

    frequencies = Counter(token for sentence in sentences for token in tokenize(sentence))
    scored = []
    for index, sentence in enumerate(sentences):
        words = tokenize(sentence)
        score = sum(frequencies[word] for word in words) / max(1, len(words))
        scored.append((score, index, sentence))

    selected = sorted(scored, key=lambda item: (-item[0], item[1]))
    output: list[tuple[int, str]] = []
    used_tokens = 0
    for _, index, sentence in selected:
        sentence_tokens = estimate_tokens(sentence)
        if sentence_tokens > token_budget and not output:
            return trim_to_budget(sentence, token_budget)
        if used_tokens + sentence_tokens > token_budget:
            continue
        output.append((index, sentence))
        used_tokens += sentence_tokens
        if used_tokens >= token_budget:
            break

    return "\n".join(sentence for _, sentence in sorted(output))


def summarize_records(records: Iterable[dict[str, Any]], token_budget: int = 1200) -> str:
    prefixed = [
        f"[{record.get('category')} @ {record.get('timestamp')}] {record.get('content', '')}"
        for record in records
    ]
    return summarize_texts(prefixed, token_budget)
