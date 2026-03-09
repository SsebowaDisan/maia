from api.services.agent.tools.base import ToolExecutionContext
from api.services.agent.tools.data_tools import ReportGenerationTool


def _context() -> ToolExecutionContext:
    return ToolExecutionContext(
        user_id="u1",
        tenant_id="t1",
        conversation_id="c1",
        run_id="r1",
        mode="company_agent",
        settings={},
    )


def test_report_generation_includes_ga4_full_report_snapshot() -> None:
    context = _context()
    context.settings["__latest_analytics_full_report"] = {
        "property_id": "479179141",
        "kpis": {
            "sessions": 12345,
            "users": 9876,
            "conversions": 321,
            "bounce_rate": 47.2,
        },
        "chart_keys": ["traffic_trend", "channel_bar"],
        "top_channel": "Organic Search",
        "top_page": "/home",
    }
    result = ReportGenerationTool().execute(
        context=context,
        prompt="build report",
        params={"title": "GA4 Executive Brief", "summary": "Summarize analytics"},
    )

    assert "### GA4 Full Report Snapshot" in result.content
    assert "| Property ID | 479179141 |" in result.content
    assert "| Sessions (30d) | 12345 |" in result.content
