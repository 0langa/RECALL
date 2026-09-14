"""Guard public memory actions before a storage transaction can begin."""
from __future__ import annotations

from functools import wraps
import inspect
from pathlib import Path
from typing import Any, Callable, ParamSpec, TypeVar

import config
import turn_policy

P = ParamSpec("P")
R = TypeVar("R")


class MemoryDisabledError(ValueError):
    def __init__(self) -> None:
        super().__init__("RECALL is disabled for this turn.")

    def to_dict(self) -> dict[str, Any]:
        return turn_policy.disabled_result()


def require_memory(root: str | Path | None) -> Path:
    resolved = config.project_root(root)
    if turn_policy.policy_status(resolved)["disabled"]:
        raise MemoryDisabledError()
    return resolved


def memory_action(function: Callable[P, R]) -> Callable[P, R]:
    """Place outside @atomic_write; internal storage remains the import boundary."""
    signature = inspect.signature(function)

    @wraps(function)
    def guarded(*args: P.args, **kwargs: P.kwargs) -> R:
        bound = signature.bind(*args, **kwargs)
        require_memory(bound.arguments.get("root"))
        return function(*args, **kwargs)

    return guarded
