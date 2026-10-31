"""Typed application contracts shared by RECALL interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


RootPath = str | Path | None


@dataclass(frozen=True)
class ReviewRequest:
    """Request for memory review or audit filtering."""

    root: RootPath = None
    statuses: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    source: str | None = None
    limit: int = 20

    def __post_init__(self) -> None:
        if self.limit <= 0:
            raise ValueError("limit must be positive")


@dataclass(frozen=True)
class ContextPacketRequest:
    """Request for a bounded context packet."""

    query_text: str
    token_budget: int = 1200
    categories: tuple[str, ...] = ()
    root: RootPath = None

    def __post_init__(self) -> None:
        if not self.query_text.strip():
            raise ValueError("query_text must not be empty")
        if self.token_budget <= 0:
            raise ValueError("token_budget must be positive")


@dataclass(frozen=True)
class ApplicationResponse:
    """Serializable application response."""

    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return the public JSON-compatible payload."""

        return self.payload


ReviewResponse = ApplicationResponse
ContextPacketResponse = ApplicationResponse
