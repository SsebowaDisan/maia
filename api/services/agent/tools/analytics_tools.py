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
from api.services.agent.tools.google_target_resolution import resolve_ga4_reference


class GA4ReportTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="analytics.ga4.report",
        action_class="read",
        risk_level="medium",
        required_permissions=["analytics.read"],
        execution_policy="auto_execute",
        description="Run GA4 Data API report and summarize traffic/conversion metrics.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        property_id = str(params.get("property_id") or "").strip() or None
        if not property_id:
            resolved_ref = resolve_ga4_reference(
                prompt=prompt,
                params=params,
                settings=context.settings,
            )
            if resolved_ref is not None:
                property_id = resolved_ref.resource_id
        dimensions = params.get("dimensions")
        metrics = params.get("metrics")
        date_ranges = params.get("date_ranges")
        limit = int(params.get("limit") or 100)

        connector = get_connector_registry().build("google_analytics", settings=context.settings)
        response = connector.run_report(
            property_id=property_id,
            dimensions=dimensions if isinstance(dimensions, list) else None,
            metrics=metrics if isinstance(metrics, list) else None,
            date_ranges=date_ranges if isinstance(date_ranges, list) else None,
            limit=limit,
        )

        headers = response.get("dimensionHeaders") if isinstance(response, dict) else []
        metric_headers = response.get("metricHeaders") if isinstance(response, dict) else []
        rows = response.get("rows") if isinstance(response, dict) else []
        if not isinstance(headers, list):
            headers = []
        if not isinstance(metric_headers, list):
            metric_headers = []
        if not isinstance(rows, list):
            rows = []

        dim_names = [str(item.get("name") or "dimension") for item in headers if isinstance(item, dict)]
        metric_names = [str(item.get("name") or "metric") for item in metric_headers if isinstance(item, dict)]

        lines = [
            "### GA4 report summary",
            f"- Rows: {len(rows)}",
            f"- Dimensions: {', '.join(dim_names) if dim_names else 'none'}",
            f"- Metrics: {', '.join(metric_names) if metric_names else 'none'}",
            "",
            "### Top rows",
        ]
        for row in rows[:8]:
            if not isinstance(row, dict):
                continue
            dim_vals = row.get("dimensionValues") or []
            met_vals = row.get("metricValues") or []
            if not isinstance(dim_vals, list):
                dim_vals = []
            if not isinstance(met_vals, list):
                met_vals = []
            dims = ", ".join(str((item or {}).get("value") or "") for item in dim_vals[: len(dim_names)])
            mets = ", ".join(str((item or {}).get("value") or "") for item in met_vals[: len(metric_names)])
            lines.append(f"- {dims or 'row'} => {mets}")
        if len(lines) <= 6:
            lines.append("- No rows returned for the selected date range.")

        next_steps = [
            "Compare this report against previous period and flag anomalies.",
            "Push key KPI rows to Sheets or executive document.",
        ]
        context.settings["__latest_analytics_report"] = {
            "property_id": property_id or "",
            "row_count": len(rows),
            "dimensions": dim_names[:12],
            "metrics": metric_names[:12],
        }

        return ToolExecutionResult(
            summary=f"GA4 report executed with {len(rows)} row(s).",
            content="\n".join(lines),
            data={"row_count": len(rows), "dimensions": dim_names, "metrics": metric_names},
            sources=[],
            next_steps=next_steps,
            events=[
                ToolTraceEvent(
                    event_type="tool_progress",
                    title="Run GA4 report",
                    detail=f"Fetched {len(rows)} analytics row(s)",
                    data={"row_count": len(rows)},
                )
            ],
        )
