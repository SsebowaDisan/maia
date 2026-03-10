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


def test_report_generation_uses_ga4_insight_highlights_without_external_sources() -> None:
    context = _context()
    context.settings["__latest_analytics_full_report"] = {
        "property_id": "479179141",
        "kpis": {
            "sessions": 302,
            "users": 164,
            "conversions": 28,
            "bounce_rate": 38.1,
            "sessions_change": -24.3,
            "users_change": -62.6,
            "conversions_change": -39.1,
            "bounce_rate_change": 43.3,
        },
        "chart_keys": ["traffic_trend", "channel_bar", "channel_pie"],
        "top_channel": "Paid Search",
        "top_page": "/",
        "channel_rows": [
            {"sessionDefaultChannelGroup": "Paid Search", "sessions": "103", "conversions": "4", "bounceRate": "0.369"},
            {"sessionDefaultChannelGroup": "Organic Search", "sessions": "97", "conversions": "11", "bounceRate": "0.309"},
        ],
        "pages_rows": [
            {"pagePath": "/", "screenPageViews": "142", "averageSessionDuration": "91", "bounceRate": "0.254"},
        ],
        "device_rows": [
            {"deviceCategory": "desktop", "sessions": "189"},
            {"deviceCategory": "mobile", "sessions": "99"},
        ],
        "geo_rows": [
            {"country": "Belgium", "sessions": "200", "totalUsers": "130"},
        ],
    }

    result = ReportGenerationTool().execute(
        context=context,
        prompt="build report",
        params={"title": "GA4 Executive Brief", "summary": "Summarize analytics"},
    )

    assert "Traffic baseline: 302 sessions, 164 users, and 28 conversions" in result.content
    assert "#### Channel Performance" in result.content
    assert "#### Top Pages" in result.content
    assert "#### Device Split" in result.content
    assert "#### Top Countries" in result.content
    assert "Key findings will appear here once evidence is synthesized." not in result.content
