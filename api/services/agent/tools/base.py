from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generator, Literal

from api.services.agent.models import AgentAction, AgentSource, utc_now
from api.services.agent.policy import ActionClass


@dataclass(frozen=True)
class ToolMetadata:
    tool_id: str
    action_class: ActionClass
    risk_level: Literal["low", "medium", "high"]
    required_permissions: list[str]
    execution_policy: Literal["auto_execute", "confirm_before_execute"]
    description: str


@dataclass
class ToolExecutionContext:
    user_id: str
    tenant_id: str
    conversation_id: str
    run_id: str
    mode: str
    settings: dict[str, Any]


@dataclass
class ToolTraceEvent:
    event_type: str
    title: str
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    snapshot_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "title": self.title,
            "detail": self.detail,
            "data": self.data,
            "snapshot_ref": self.snapshot_ref,
        }


@dataclass
class ToolExecutionResult:
    summary: str
    content: str
    data: dict[str, Any]
    sources: list[AgentSource]
    next_steps: list[str]
    events: list[ToolTraceEvent] = field(default_factory=list)


class ToolExecutionError(RuntimeError):
    pass


class AgentTool:
    metadata: ToolMetadata

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        raise NotImplementedError

    def execute_stream(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> Generator[ToolTraceEvent, None, ToolExecutionResult]:
        result = self.execute(context=context, prompt=prompt, params=params)
        for event in list(result.events or []):
            yield event
        return result

    def to_action(
        self,
        *,
        status: Literal["success", "failed", "skipped"],
        summary: str,
        started_at: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentAction:
        return AgentAction(
            tool_id=self.metadata.tool_id,
            action_class=self.metadata.action_class,
            status=status,
            summary=summary,
            started_at=started_at,
            ended_at=utc_now().isoformat(),
            metadata=metadata or {},
        )
