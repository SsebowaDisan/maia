from __future__ import annotations

from typing import Any

from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolMetadata,
    ToolTraceEvent,
)
from api.services.agent.tools.research_competitor_profile_tool import CompetitorProfileTool
from api.services.agent.tools.research_web_tool_stream import execute_web_research_stream


class WebResearchTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="marketing.web_research",
        action_class="read",
        risk_level="low",
        required_permissions=["web.read"],
        execution_policy="auto_execute",
        description="Search the web and synthesize source-backed insights.",
    )

    def execute_stream(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ):
        return (
            yield from execute_web_research_stream(
                context=context,
                prompt=prompt,
                params=params,
                get_connector_registry_fn=get_connector_registry,
            )
        )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        stream = self.execute_stream(context=context, prompt=prompt, params=params)
        trace_events: list[ToolTraceEvent] = []
        while True:
            try:
                trace_events.append(next(stream))
            except StopIteration as stop:
                result = stop.value
                break
        result.events = trace_events
        return result
