"""Review and health application service."""

from __future__ import annotations

import memory_review
from models import ReviewRequest, ReviewResponse


def review_memory(request: ReviewRequest) -> ReviewResponse:
    """Return filtered memory review data without changing its public shape."""

    payload = memory_review.review_memory(
        request.root,
        statuses=list(request.statuses),
        categories=list(request.categories),
        source=request.source,
        limit=request.limit,
    )
    return ReviewResponse(payload)
