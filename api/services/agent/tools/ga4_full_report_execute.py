from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from api.services.agent.connectors.base import ConnectorError
from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.tools.base import ToolExecutionContext, ToolExecutionResult, ToolTraceEvent
from api.services.agent.tools.google_target_resolution import resolve_ga4_reference

_SERIES_COLORS = ["#111111", "#374151", "#4b5563", "#6b7280", "#9ca3af", "#1f2937"]


# ---------------------------------------------------------------------------
# GA4 response parsing helpers
# ---------------------------------------------------------------------------

def _parse_ga4_rows(response: dict[str, Any]) -> list[dict[str, str]]:
    """Flatten GA4 runReport response into a list of flat dicts."""
    dim_headers = [str(h.get("name") or "") for h in (response.get("dimensionHeaders") or [])]
    met_headers = [str(h.get("name") or "") for h in (response.get("metricHeaders") or [])]
    result: list[dict[str, str]] = []
    for row in (response.get("rows") or []):
        if not isinstance(row, dict):
            continue
        d: dict[str, str] = {}
        for i, col in enumerate(dim_headers):
            vals = row.get("dimensionValues") or []
            d[col] = str((vals[i] if i < len(vals) else {}).get("value") or "")
        for i, col in enumerate(met_headers):
            vals = row.get("metricValues") or []
            d[col] = str((vals[i] if i < len(vals) else {}).get("value") or "0")
        result.append(d)
    return result


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _pct_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


def _fmt_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s"


# ---------------------------------------------------------------------------
# Chart payload builders (recharts-compatible, no pandas needed)
# ---------------------------------------------------------------------------

def _build_ga4_line_payload(
    rows: list[dict[str, str]], x_col: str, metric_cols: list[str], title: str
) -> dict[str, Any]:
    series = [
        {"key": col, "label": col.replace("_", " ").title(), "type": "line", "color": _SERIES_COLORS[i % len(_SERIES_COLORS)]}
        for i, col in enumerate(metric_cols)
    ]
    points: list[dict[str, Any]] = []
    for row in rows:
        point: dict[str, Any] = {"x": row.get(x_col, "")}
        for col in metric_cols:
            v = _safe_float(row.get(col, 0))
            point[col] = v
        point["y"] = _safe_float(row.get(metric_cols[0], 0)) if metric_cols else 0.0
        points.append(point)
    return {
        "kind": "chart", "library": "recharts", "chart_type": "line",
        "title": title, "x": x_col, "y": metric_cols[0] if metric_cols else "",
        "x_type": "category", "series": series, "points": points,
        "interactive": {"brush": True},
    }


def _build_ga4_bar_payload(
    rows: list[dict[str, str]], x_col: str, y_col: str, title: str, top_n: int = 12
) -> dict[str, Any]:
    top = sorted(rows, key=lambda r: _safe_float(r.get(y_col, 0)), reverse=True)[:top_n]
    points = [
        {"x": str(r.get(x_col, "")), "y": _safe_float(r.get(y_col, 0)), y_col: _safe_float(r.get(y_col, 0))}
        for r in top
    ]
    return {
        "kind": "chart", "library": "recharts", "chart_type": "bar",
        "title": title, "x": x_col, "y": y_col, "x_type": "category",
        "series": [{"key": y_col, "label": y_col.replace("_", " ").title(), "type": "bar", "color": _SERIES_COLORS[0]}],
        "points": points, "interactive": {"brush": True},
    }


def _build_ga4_pie_payload(
    rows: list[dict[str, str]], x_col: str, y_col: str, title: str, top_n: int = 8
) -> dict[str, Any]:
    sorted_rows = sorted(rows, key=lambda r: _safe_float(r.get(y_col, 0)), reverse=True)
    total = sum(_safe_float(r.get(y_col, 0)) for r in sorted_rows) or 1.0
    top = sorted_rows[:top_n]
    slices = [
        {"label": str(r.get(x_col, "")), "value": round(_safe_float(r.get(y_col, 0)), 2),
         "percent": round(_safe_float(r.get(y_col, 0)) / total * 100, 1)}
        for r in top
    ]
    other = sum(_safe_float(r.get(y_col, 0)) for r in sorted_rows[top_n:])
    if other > 0:
        slices.append({"label": "Other", "value": round(other, 2), "percent": round(other / total * 100, 1)})
    return {
        "kind": "chart", "library": "recharts", "chart_type": "pie",
        "title": title, "x": x_col, "y": y_col, "slices": slices,
    }


# ---------------------------------------------------------------------------
# Query helper
# ---------------------------------------------------------------------------

def _run_query(
    connector: Any,
    property_id: str,
    dimensions: list[str],
    metrics: list[str],
    date_range: dict[str, str],
    limit: int = 50,
) -> list[dict[str, str]]:
    try:
        raw = connector.run_report(
            property_id=property_id,
            dimensions=dimensions,
            metrics=metrics,
            date_ranges=[date_range],
            limit=limit,
        )
        return _parse_ga4_rows(raw if isinstance(raw, dict) else {})
    except (ConnectorError, Exception):
        return []


# ---------------------------------------------------------------------------
# Main execute function
# ---------------------------------------------------------------------------

def execute_ga4_full_report(
    *,
    context: ToolExecutionContext,
    prompt: str,
    params: dict[str, Any],
    tool_id: str,
) -> ToolExecutionResult:
    events: list[ToolTraceEvent] = []

    # --- Resolve property ID ---
    property_id = str(params.get("property_id") or "").strip() or None
    if not property_id:
        resolved = resolve_ga4_reference(prompt=prompt, params=params, settings=context.settings)
        if resolved is not None:
            property_id = resolved.resource_id
    if not property_id:
        events.append(ToolTraceEvent(
            event_type="tool_failed", title="GA4 property ID missing",
            detail="Set GOOGLE_ANALYTICS_PROPERTY_ID or pass property_id param.",
            data={"tool_id": tool_id},
        ))
        return ToolExecutionResult(
            summary="GA4 property ID is required.",
            content=(
                "### GA4 Full Report — Configuration Required\n\n"
                "No GA4 property ID was found.\n\n"
                "**To fix**: provide `property_id` in the request, or set the "
                "`GOOGLE_ANALYTICS_PROPERTY_ID` environment variable / credential."
            ),
            data={"available": False, "error": "missing_property_id"},
            sources=[],
            next_steps=["Configure GOOGLE_ANALYTICS_PROPERTY_ID and retry."],
            events=events,
        )

    # --- Build connector ---
    try:
        connector = get_connector_registry().build("google_analytics", settings=context.settings)
    except Exception as exc:
        events.append(ToolTraceEvent(
            event_type="tool_failed", title="GA4 connector unavailable",
            detail=str(exc), data={"tool_id": tool_id},
        ))
        return ToolExecutionResult(
            summary="GA4 connector could not be initialised.",
            content=f"### GA4 Full Report — Auth Error\n\n- Error: {exc}\n\nCheck GA4 OAuth credentials.",
            data={"available": False, "error": str(exc)},
            sources=[],
            next_steps=["Re-authorise Google Analytics via the settings panel."],
            events=events,
        )

    events.append(ToolTraceEvent(
        event_type="prepare_request", title="Prepare GA4 queries",
        detail=f"property={property_id}", data={"property_id": property_id},
    ))

    # --- Date windows ---
    today = date.today()
    current_range = {"startDate": "30daysAgo", "endDate": "today"}
    prev_range = {"startDate": "60daysAgo", "endDate": "31daysAgo"}
    trend_range = {"startDate": "90daysAgo", "endDate": "today"}
    date_range_override = params.get("date_range")
    if isinstance(date_range_override, dict):
        current_range = date_range_override

    events.append(ToolTraceEvent(
        event_type="api_call_started", title="Fetch GA4 data",
        detail="Running 6 analytics queries", data={"property_id": property_id},
    ))

    # --- Run 6 queries ---
    trend_rows = _run_query(connector, property_id,
        ["date"], ["sessions", "totalUsers", "screenPageViews"], trend_range, 90)
    channel_rows = _run_query(connector, property_id,
        ["sessionDefaultChannelGroup"], ["sessions", "conversions", "bounceRate"], current_range, 20)
    channel_prev_rows = _run_query(connector, property_id,
        ["sessionDefaultChannelGroup"], ["sessions", "conversions", "bounceRate"], prev_range, 20)
    pages_rows = _run_query(connector, property_id,
        ["pagePath"], ["screenPageViews", "averageSessionDuration", "bounceRate"], current_range, 20)
    device_rows = _run_query(connector, property_id,
        ["deviceCategory"], ["sessions"], current_range, 10)
    geo_rows = _run_query(connector, property_id,
        ["country"], ["sessions", "totalUsers"], current_range, 12)

    events.append(ToolTraceEvent(
        event_type="api_call_completed", title="GA4 data fetched",
        detail=f"trend={len(trend_rows)}, channels={len(channel_rows)}, pages={len(pages_rows)}",
        data={"trend_rows": len(trend_rows), "channel_rows": len(channel_rows)},
    ))

    # --- Compute KPIs ---
    def _sum(rows: list[dict], col: str) -> float:
        return sum(_safe_float(r.get(col, 0)) for r in rows)

    curr_sessions = _sum(channel_rows, "sessions")
    curr_conversions = _sum(channel_rows, "conversions")
    prev_sessions = _sum(channel_prev_rows, "sessions")
    prev_conversions = _sum(channel_prev_rows, "conversions")
    curr_bounce = (
        sum(_safe_float(r.get("bounceRate", 0)) * _safe_float(r.get("sessions", 0)) for r in channel_rows)
        / curr_sessions if curr_sessions else 0.0
    )
    prev_bounce = (
        sum(_safe_float(r.get("bounceRate", 0)) * _safe_float(r.get("sessions", 0)) for r in channel_prev_rows)
        / prev_sessions if prev_sessions else 0.0
    )
    curr_users = _sum(trend_rows[-30:], "totalUsers") if trend_rows else 0.0
    prev_users = _sum(trend_rows[:30], "totalUsers") if len(trend_rows) >= 60 else 0.0

    kpis = {
        "sessions": round(curr_sessions), "sessions_prev": round(prev_sessions),
        "sessions_change": _pct_change(curr_sessions, prev_sessions),
        "conversions": round(curr_conversions), "conversions_prev": round(prev_conversions),
        "conversions_change": _pct_change(curr_conversions, prev_conversions),
        "bounce_rate": round(curr_bounce * 100, 1), "bounce_rate_prev": round(prev_bounce * 100, 1),
        "bounce_rate_change": _pct_change(curr_bounce, prev_bounce),
        "users": round(curr_users), "users_prev": round(prev_users),
        "users_change": _pct_change(curr_users, prev_users),
    }

    # --- Build chart payloads ---
    charts: dict[str, Any] = {}
    if trend_rows:
        charts["traffic_trend"] = _build_ga4_line_payload(
            trend_rows, "date", ["sessions", "totalUsers", "screenPageViews"],
            "Traffic Trend (Last 90 Days)"
        )
    if channel_rows:
        charts["channel_bar"] = _build_ga4_bar_payload(
            channel_rows, "sessionDefaultChannelGroup", "sessions",
            "Sessions by Channel (Last 30 Days)"
        )
        charts["channel_pie"] = _build_ga4_pie_payload(
            channel_rows, "sessionDefaultChannelGroup", "sessions",
            "Channel Share (Last 30 Days)"
        )
    if pages_rows:
        charts["top_pages"] = _build_ga4_bar_payload(
            pages_rows, "pagePath", "screenPageViews",
            "Top Pages by Views (Last 30 Days)", top_n=15
        )
    if device_rows:
        charts["device_pie"] = _build_ga4_pie_payload(
            device_rows, "deviceCategory", "sessions",
            "Sessions by Device (Last 30 Days)"
        )
    if geo_rows:
        charts["geography"] = _build_ga4_bar_payload(
            geo_rows, "country", "sessions",
            "Top Countries by Sessions (Last 30 Days)", top_n=12
        )

    # --- Assemble report ---
    top_channel = channel_rows[0].get("sessionDefaultChannelGroup", "—") if channel_rows else "—"
    top_page = pages_rows[0].get("pagePath", "—") if pages_rows else "—"
    device_total = max(1.0, sum(_safe_float(x.get("sessions", 0)) for x in device_rows))

    trend_note = f"- {len(trend_rows)} daily data points collected." if trend_rows else "- No trend data available."
    channel_table = [
        f"| {r.get('sessionDefaultChannelGroup', '—')} | {int(_safe_float(r.get('sessions', 0))):,}"
        f" | {int(_safe_float(r.get('conversions', 0))):,} | {round(_safe_float(r.get('bounceRate', 0)) * 100, 1)}% |"
        for r in channel_rows[:10]
    ] or ["| — | — | — | — |"]
    pages_table = [
        f"| {r.get('pagePath', '—')[:60]} | {int(_safe_float(r.get('screenPageViews', 0))):,}"
        f" | {_fmt_duration(_safe_float(r.get('averageSessionDuration', 0)))}"
        f" | {round(_safe_float(r.get('bounceRate', 0)) * 100, 1)}% |"
        for r in pages_rows[:12]
    ] or ["| — | — | — | — |"]
    device_table = [
        f"| {r.get('deviceCategory', '—')} | {int(_safe_float(r.get('sessions', 0))):,}"
        f" | {round(_safe_float(r.get('sessions', 0)) / device_total * 100, 1)}% |"
        for r in device_rows
    ] or ["| — | — | — |"]
    geo_table = [
        f"| {r.get('country', '—')} | {int(_safe_float(r.get('sessions', 0))):,} | {int(_safe_float(r.get('totalUsers', 0))):,} |"
        for r in geo_rows[:10]
    ] or ["| — | — | — |"]

    content_lines = [
        f"# Google Analytics Report — Property `{property_id}`",
        f"*Period: last 30 days vs previous 30 days | Generated {today.isoformat()}*",
        "",
        "## Executive Summary",
        "",
        "| Metric | Current 30d | Previous 30d | Change |",
        "|---|---|---|---|",
        f"| Sessions | {kpis['sessions']:,} | {kpis['sessions_prev']:,} | {_fmt_pct(kpis['sessions_change'])} |",
        f"| Users | {kpis['users']:,} | {kpis['users_prev']:,} | {_fmt_pct(kpis['users_change'])} |",
        f"| Conversions | {kpis['conversions']:,} | {kpis['conversions_prev']:,} | {_fmt_pct(kpis['conversions_change'])} |",
        f"| Bounce Rate | {kpis['bounce_rate']}% | {kpis['bounce_rate_prev']}% | {_fmt_pct(kpis['bounce_rate_change'])} |",
        "",
        "## Traffic Trend (Last 90 Days)",
        "> Line chart — sessions, users, pageviews over time.",
        "", trend_note,
        "",
        "## Channel Performance",
        f"- **Top channel**: {top_channel}",
        "",
        "| Channel | Sessions | Conversions | Bounce Rate |",
        "|---|---|---|---|",
        *channel_table,
        "",
        "## Top Content (Last 30 Days)",
        f"- **Most-viewed page**: {top_page}",
        "",
        "| Page | Pageviews | Avg Duration | Bounce Rate |",
        "|---|---|---|---|",
        *pages_table,
        "",
        "## Audience",
        "",
        "### Device Breakdown",
        "| Device | Sessions | Share |",
        "|---|---|---|",
        *device_table,
        "",
        "### Top Countries",
        "| Country | Sessions | Users |",
        "|---|---|---|",
        *geo_table,
    ]

    context.settings["__latest_analytics_full_report"] = {
        "property_id": property_id,
        "kpis": kpis,
        "chart_keys": list(charts.keys()),
        "top_channel": top_channel,
        "top_page": top_page,
    }

    events.append(ToolTraceEvent(
        event_type="tool_progress", title="GA4 full report ready",
        detail=f"charts={len(charts)}, kpis captured",
        data={"charts": list(charts.keys()), "property_id": property_id},
    ))

    return ToolExecutionResult(
        summary=f"GA4 full report: {kpis['sessions']:,} sessions, {kpis['conversions']:,} conversions, {len(charts)} charts.",
        content="\n".join(content_lines),
        data={
            "property_id": property_id,
            "kpis": kpis,
            "charts": charts,
            "channel_rows": channel_rows[:20],
            "pages_rows": pages_rows[:20],
            "device_rows": device_rows,
            "geo_rows": geo_rows[:12],
            "trend_rows": trend_rows[:90],
        },
        sources=[],
        next_steps=[
            "Use `report.generate` to embed these charts in an executive document.",
            "Use `data.science.stats` on the channel data for statistical insights.",
            "Schedule this report weekly with `calendar.create_event`.",
        ],
        events=events,
    )


__all__ = ["execute_ga4_full_report"]
