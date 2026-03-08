from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PlannedStep:
    tool_id: str
    title: str
    params: dict[str, Any]
    why_this_step: str = ""
    expected_evidence: tuple[str, ...] = ()
