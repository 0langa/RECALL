"""Run journal: records every agent-visible emission with channel + size + timing."""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from . import channels, tokens


_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:\+00:00|Z)?")
_TMP_RE = re.compile(r"[A-Za-z]:\\\\?[^\"\s]*recall-bench-[^\"\s]*|/[^\"\s]*recall-bench-[^\"\s]*")
_SCORE_RE = re.compile(r"\"score\": \d+\.\d+")


def normalize_for_hash(text: str) -> str:
    """Strip run-volatile substrings so identical behavior hashes identically.

    Removes wall-clock timestamps, temp project paths, and float scores whose
    low decimals move with record age. Ranking changes still change the hash
    because result ids and order remain in the text.
    """
    text = _TS_RE.sub("<TS>", text)
    text = _TMP_RE.sub("<TMP>", text)
    text = _SCORE_RE.sub('"score": <S>', text)
    return text


class Recorder:
    def __init__(self, journal_path: Path) -> None:
        self.journal_path = journal_path
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.journal_path.open("w", encoding="utf-8", newline="\n")
        self._emission_hash = hashlib.sha256()
        self.entries = 0

    def record(
        self,
        *,
        channel: str,
        text: str,
        scenario: str,
        session: int,
        turn: int | None = None,
        surface: str = "",
        duration_ms: float | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "kind": "emission",
            "channel": channels.validate(channel),
            "fixed": channels.is_fixed(channel),
            "scenario": scenario,
            "session": session,
            "turn": turn,
            "surface": surface,
            **tokens.measure(text),
            "text": text,
        }
        if duration_ms is not None:
            entry["duration_ms"] = round(duration_ms, 2)
        if extra:
            entry["extra"] = extra
        self._write(entry)
        # Emission hash covers behavior-relevant content only (not timing),
        # so identical seeds must produce identical hashes across runs.
        self._emission_hash.update(
            json.dumps(
                {
                    "channel": entry["channel"],
                    "scenario": entry["scenario"],
                    "session": entry["session"],
                    "turn": entry["turn"],
                    "text": normalize_for_hash(entry["text"]),
                },
                sort_keys=True,
            ).encode("utf-8")
        )
        self.entries += 1
        return entry

    def event(self, kind: str, payload: dict[str, Any]) -> None:
        """Non-emission observations: latencies, store snapshots, decisions."""
        self._write({"kind": kind, **payload})

    def latency(self, *, operation: str, duration_ms: float, scenario: str, session: int, turn: int | None = None) -> None:
        self.event(
            "latency",
            {
                "operation": operation,
                "duration_ms": round(duration_ms, 2),
                "scenario": scenario,
                "session": session,
                "turn": turn,
            },
        )

    def emission_hash(self) -> str:
        return self._emission_hash.hexdigest()

    def close(self) -> None:
        self._handle.close()

    def _write(self, entry: dict[str, Any]) -> None:
        self._handle.write(json.dumps(entry, sort_keys=True) + "\n")
        self._handle.flush()


class Timer:
    def __enter__(self) -> "Timer":
        self.start = time.perf_counter()
        return self

    def __exit__(self, *exc: object) -> None:
        self.duration_ms = (time.perf_counter() - self.start) * 1000.0


def read_journal(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries
