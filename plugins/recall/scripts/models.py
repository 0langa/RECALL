"""Typed application contracts shared by RECALL interfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


RootPath = str | Path | None


@dataclass(frozen=True)
class SaveRequest:
    """Request to persist one memory through application policy."""

    category: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    root: RootPath = None

    def __post_init__(self) -> None:
        if not self.category.strip():
            raise ValueError("category must not be empty")
        if not self.content.strip():
            raise ValueError("content must not be empty")


@dataclass(frozen=True)
class RetrieveRequest:
    """Request for ranked memories."""

    query_text: str
    categories: tuple[str, ...] = ()
    exclude_categories: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ()
    limit: int = 8
    summarize: bool = False
    root: RootPath = None

    def __post_init__(self) -> None:
        if not self.query_text.strip():
            raise ValueError("query_text must not be empty")
        if self.limit <= 0:
            raise ValueError("limit must be positive")


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
class LifecycleRequest:
    """Request for one lifecycle transition."""

    action: Literal["confirm", "resolve", "stale", "supersede", "merge", "prune", "delete"]
    record_id: int
    related_id: int | None = None
    note: str | None = None
    root: RootPath = None

    def __post_init__(self) -> None:
        if self.record_id <= 0:
            raise ValueError("record_id must be positive")


@dataclass(frozen=True)
class HealthRequest:
    """Request for store diagnosis or repair."""

    action: Literal["doctor", "repair"] = "doctor"
    root: RootPath = None


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
RetrieveResponse = ApplicationResponse
SaveResponse = ApplicationResponse
LifecycleResponse = ApplicationResponse
HealthResponse = ApplicationResponse
ContextPacketResponse = ApplicationResponse
