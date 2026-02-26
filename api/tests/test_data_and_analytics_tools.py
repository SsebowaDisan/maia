from __future__ import annotations

from unittest.mock import patch

from api.services.agent.tools.analytics_tools import GA4ReportTool
from api.services.agent.tools.base import ToolExecutionContext
from api.services.agent.tools.charts_tools import ChartGenerateTool
from api.services.agent.tools.data_tools import DataAnalysisTool, ReportGenerationTool


def _context() -> ToolExecutionContext:
    return ToolExecutionContext(
        user_id="u1",
        tenant_id="t1",
        conversation_id="c1",
        run_id="r1",
        mode="company_agent",
        settings={},
    )


def test_data_analysis_tool_produces_numeric_summary() -> None:
    result = DataAnalysisTool().execute(
        context=_context(),
        prompt="analyze",
        params={"rows": [{"revenue": 100, "cost": 25}, {"revenue": 200, "cost": 75}]},
    )
    assert "Dataset Analysis" in result.content
    assert result.data["row_count"] == 2
    assert "revenue" in result.data["stats"]


def test_report_generation_tool_persists_latest_report_context() -> None:
    context = _context()
    result = ReportGenerationTool().execute(
        context=context,
        prompt="build report",
        params={"title": "Weekly KPI", "summary": "Pipeline and conversion improved."},
    )
    assert "## Weekly KPI" in result.content
    assert context.settings["__latest_report_title"] == "Weekly KPI"
    assert "Weekly KPI" in context.settings["__latest_report_content"]


def test_chart_generate_tool_returns_artifact_path() -> None:
    result = ChartGenerateTool().execute(
        context=_context(),
        prompt="chart",
        params={"title": "Trend", "labels": ["Mon", "Tue"], "values": [1, 3]},
    )
    assert "Generated" in result.summary
    assert result.data["path"]
    assert result.data["points"] == 2


class _StubGa4Connector:
    def run_report(self, **kwargs):
        del kwargs
        return {
            "dimensionHeaders": [{"name": "country"}],
            "metricHeaders": [{"name": "sessions"}],
            "rows": [
                {
                    "dimensionValues": [{"value": "BE"}],
                    "metricValues": [{"value": "120"}],
                }
            ],
        }


class _StubRegistry:
    def build(self, connector_id: str, settings: dict | None = None):
        del settings
        assert connector_id == "google_analytics"
        return _StubGa4Connector()


def test_ga4_report_tool_summarizes_rows() -> None:
    with patch("api.services.agent.tools.analytics_tools.get_connector_registry", return_value=_StubRegistry()):
        result = GA4ReportTool().execute(
            context=_context(),
            prompt="ga4",
            params={"metrics": ["sessions"], "dimensions": ["country"]},
        )
    assert result.data["row_count"] == 1
    assert "GA4 report summary" in result.content

