from __future__ import annotations

from typing import Any

from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolMetadata,
)

from .stats_execute import execute_data_science_stats


class DataScienceStatsTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="data.science.stats",
        action_class="read",
        risk_level="low",
        required_permissions=["data.read"],
        execution_policy="auto_execute",
        description=(
            "Compute correlation matrices, descriptive statistics, and distribution tests. "
            "Modes: correlation (Pearson/Spearman), descriptive (mean/median/std/skew/kurtosis), "
            "distribution (Shapiro-Wilk normality)."
        ),
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        return execute_data_science_stats(
            context=context,
            prompt=prompt,
            params=params,
            tool_id=self.metadata.tool_id,
        )
