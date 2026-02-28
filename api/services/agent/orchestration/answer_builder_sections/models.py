from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.models import AgentAction, AgentSource
from api.services.agent.planner import PlannedStep


@dataclass(frozen=True)
class AnswerBuildContext:
    request: ChatRequest
    planned_steps: list[PlannedStep]
    executed_steps: list[dict[str, Any]]
    actions: list[AgentAction]
    sources: list[AgentSource]
    next_steps: list[str]
    runtime_settings: dict[str, Any]
    verification_report: dict[str, Any] | None = None
