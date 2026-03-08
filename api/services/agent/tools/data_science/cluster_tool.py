from __future__ import annotations

from typing import Any

from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolMetadata,
)

from .cluster_execute import execute_data_science_cluster


class DataScienceClusterTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="data.science.cluster",
        action_class="read",
        risk_level="medium",
        required_permissions=["data.read"],
        execution_policy="auto_execute",
        description=(
            "Cluster tabular data with K-Means or DBSCAN and return labelled segments. "
            "Supports automatic k selection (elbow method) and DBSCAN epsilon estimation."
        ),
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        return execute_data_science_cluster(
            context=context,
            prompt=prompt,
            params=params,
            tool_id=self.metadata.tool_id,
        )
