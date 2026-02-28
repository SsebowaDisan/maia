from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class StepGuardOutcome:
    decision: str
    params: dict[str, Any]
