from __future__ import annotations

from typing import Any

from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolMetadata,
)

from .visualization_execute import execute_data_science_visualization


def _normalize_columns_list(raw: Any) -> list[str]:
    if isinstance(raw, str):
        values = [item.strip() for item in raw.split(",")]
        return [item for item in values if item]
    if isinstance(raw, list):
        values = [" ".join(str(item).split()).strip() for item in raw]
        return [item for item in values if item]
    return []


class DataScienceVisualizationTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="data.science.visualize",
        action_class="draft",
        risk_level="low",
        required_permissions=["analytics.write"],
        execution_policy="auto_execute",
        description="Generate dataset charts for exploratory analysis and reporting.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        return execute_data_science_visualization(
            context=context,
            prompt=prompt,
            params=params,
            tool_id=self.metadata.tool_id,
            normalize_columns_list_fn=_normalize_columns_list,
        )
