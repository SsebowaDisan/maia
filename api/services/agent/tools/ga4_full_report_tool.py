from __future__ import annotations

from typing import Any

from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolMetadata,
)

from .ga4_full_report_execute import execute_ga4_full_report


class GA4FullReportTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="analytics.ga4.full_report",
        action_class="read",
        risk_level="medium",
        required_permissions=["analytics.read"],
        execution_policy="auto_execute",
        description=(
            "Comprehensive GA4 analytics report: traffic trends (90-day line chart), "
            "channel breakdown (bar + pie), top pages by views, device and geographic "
            "audience breakdown, and period-over-period KPI comparison. "
            "Returns 6 recharts-compatible chart payloads plus a structured markdown report."
        ),
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        return execute_ga4_full_report(
            context=context,
            prompt=prompt,
            params=params,
            tool_id=self.metadata.tool_id,
        )
