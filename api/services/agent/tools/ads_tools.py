from __future__ import annotations

from typing import Any

from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolTraceEvent,
    ToolMetadata,
)


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


class GoogleAdsPerformanceTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="ads.google.performance",
        action_class="read",
        risk_level="medium",
        required_permissions=["ads.read"],
        execution_policy="auto_execute",
        description="Analyze Google Ads metrics and provide optimization guidance.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        connector = get_connector_registry().build("google_ads", settings=context.settings)
        payload = connector.fetch_metrics(params)
        metrics = payload.get("metrics") or []

        total_impressions = 0.0
        total_clicks = 0.0
        total_cost = 0.0
        total_conversions = 0.0

        for row in metrics:
            if not isinstance(row, dict):
                continue
            total_impressions += _to_float(row.get("impressions"))
            total_clicks += _to_float(row.get("clicks"))
            total_cost += _to_float(row.get("cost"))
            total_conversions += _to_float(row.get("conversions"))

        ctr = (total_clicks / total_impressions * 100.0) if total_impressions else 0.0
        cpc = (total_cost / total_clicks) if total_clicks else 0.0
        cpa = (total_cost / total_conversions) if total_conversions else 0.0

        recommendations: list[str] = []
        if ctr < 1.5:
            recommendations.append("Improve ad creative relevance; CTR is below target.")
        if cpc > 2.0:
            recommendations.append("Refine keyword match types and add negative keywords.")
        if total_conversions == 0:
            recommendations.append("Verify conversion tracking and landing page intent alignment.")
        if not recommendations:
            recommendations.append("Performance is stable. Prioritize incremental creative tests.")

        content = (
            "### Google Ads Performance Snapshot\n"
            f"- Impressions: {int(total_impressions)}\n"
            f"- Clicks: {int(total_clicks)}\n"
            f"- Cost: {total_cost:.2f}\n"
            f"- Conversions: {total_conversions:.2f}\n"
            f"- CTR: {ctr:.2f}%\n"
            f"- CPC: {cpc:.2f}\n"
            f"- CPA: {cpa:.2f}\n\n"
            "### Recommendations\n"
            + "\n".join(f"- {item}" for item in recommendations)
        )

        return ToolExecutionResult(
            summary="Computed ads KPIs and recommendations.",
            content=content,
            data={
                "impressions": total_impressions,
                "clicks": total_clicks,
                "cost": total_cost,
                "conversions": total_conversions,
                "ctr": ctr,
                "cpc": cpc,
                "cpa": cpa,
            },
            sources=[],
            next_steps=[
                "Apply one budget reallocation experiment and measure in 7 days.",
                "Run two ad copy variants for lowest CTR ad group.",
            ],
            events=[
                ToolTraceEvent(
                    event_type="tool_progress",
                    title="Fetch ads metrics",
                    detail=f"Loaded {len(metrics)} campaign row(s)",
                    data={"rows": len(metrics)},
                ),
                ToolTraceEvent(
                    event_type="tool_progress",
                    title="Compute KPI summary",
                    detail=f"CTR {ctr:.2f}% | CPC {cpc:.2f} | CPA {cpa:.2f}",
                    data={"ctr": ctr, "cpc": cpc, "cpa": cpa},
                ),
            ],
        )
