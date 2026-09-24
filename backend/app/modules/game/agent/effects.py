"""The graph's next-step effect union (sprint 011/07, WI1) -- what
`advance` (`agent/advance.py`) produces on every visit and what the router
(`agent/flow_nodes.py`) dispatches on. `DecisionRequest` (`decisions.py`),
`Operation` (`flow_state.py`) and `BeatRequest` (`narration.py`) are reused
unchanged and re-exported here so a caller needs only this module; this is
also where `flow_state.NextEffect = Any` gets its real shape without a
circular import (`flow_state` is a leaf module; this one sits above it).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from .decisions import DecisionRequest
from .flow_state import Operation, Usage
from .narration import BeatRequest

__all__ = [
    "PlayerWait",
    "TurnComplete",
    "ResumeResult",
    "NextEffect",
    "DecisionRequest",
    "Operation",
    "BeatRequest",
    "add_usage",
]


@dataclass(frozen=True)
class PlayerWait:
    request_id: str
    kind: Literal["roll", "choice"]
    public_payload: Mapping[str, Any]


@dataclass(frozen=True)
class TurnComplete:
    status: Literal["open", "terminal", "execution_error"]


@dataclass(frozen=True)
class ResumeResult:
    request_id: str
    value: Any


NextEffect = DecisionRequest | Operation | PlayerWait | BeatRequest | TurnComplete


def add_usage(current: Usage | None, added: Usage) -> Usage:
    """Accumulates one model call's `Usage` onto the turn's running total.
    `cost` stays `None` unless at least one side actually carries a cost
    (← `model_call.to_usage`, which may not always price a call)."""
    if current is None:
        return added
    cost: Decimal | None
    if current.cost is None and added.cost is None:
        cost = None
    else:
        cost = (current.cost or Decimal(0)) + (added.cost or Decimal(0))
    return Usage(
        prompt_tokens=current.prompt_tokens + added.prompt_tokens,
        completion_tokens=current.completion_tokens + added.completion_tokens,
        cost=cost,
    )
