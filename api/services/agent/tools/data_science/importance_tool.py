from __future__ import annotations

from typing import Any

from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolMetadata,
)

from .importance_execute import execute_data_science_feature_importance


class DataScienceFeatureImportanceTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="data.science.feature_importance",
        action_class="read",
        risk_level="medium",
        required_permissions=["data.read"],
        execution_policy="auto_execute",
        description=(
            "Rank input features by predictive importance using a Random Forest. "
            "Requires `target` column. Supports classification and regression."
        ),
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        return execute_data_science_feature_importance(
            context=context,
            prompt=prompt,
            params=params,
            tool_id=self.metadata.tool_id,
        )
