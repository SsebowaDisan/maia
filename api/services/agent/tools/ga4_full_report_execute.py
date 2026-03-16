from __future__ import annotations

import os
import re
from datetime import date, timedelta
from dataclasses import dataclass
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

@dataclass(frozen=True)
class _QueryResult:
    rows: list[dict[str, str]]
    error: str | None = None


def _run_query(
    connector: Any,
    property_id: str,
    dimensions: list[str],
    metrics: list[str],
    date_range: dict[str, str],
    limit: int = 50,
) -> _QueryResult:
    try:
        raw = connector.run_report(
            property_id=property_id,
            dimensions=dimensions,
            metrics=metrics,
            date_ranges=[date_range],
            limit=limit,
        )
        return _QueryResult(rows=_parse_ga4_rows(raw if isinstance(raw, dict) else {}))
    except (ConnectorError, Exception) as exc:
        return _QueryResult(
            rows=[],
            error=f"{type(exc).__name__}: {exc}",
        )


def _is_access_error(message: str) -> bool:
    lowered = message.lower()
    return (
        "403" in lowered
        or "forbidden" in lowered
        or "permission" in lowered
        or "access denied" in lowered
        or "insufficient permission" in lowered
        or "unauthorized" in lowered
    )


def _collect_query_results(
    *,
    connector: Any,
    property_id: str,
    current_range: dict[str, str],
    prev_range: dict[str, str],
    trend_range: dict[str, str],
) -> dict[str, _QueryResult]:
    return {
        "trend": _run_query(
            connector,
            property_id,
            ["date"],
            ["sessions", "totalUsers", "screenPageViews"],
            trend_range,
            90,
        ),
        "channels_current": _run_query(
            connector,
            property_id,
            ["sessionDefaultChannelGroup"],
            ["sessions", "conversions", "bounceRate"],
            current_range,
            20,
        ),
        "channels_previous": _run_query(
            connector,
            property_id,
            ["sessionDefaultChannelGroup"],
            ["sessions", "conversions", "bounceRate"],
            prev_range,
            20,
        ),
        "pages": _run_query(
            connector,
            property_id,
            ["pagePath"],
            ["screenPageViews", "averageSessionDuration", "bounceRate"],
            current_range,
            20,
        ),
        "devices": _run_query(
            connector,
            property_id,
            ["deviceCategory"],
            ["sessions"],
            current_range,
            10,
        ),
        "geography": _run_query(
            connector,
            property_id,
            ["country"],
            ["sessions", "totalUsers"],
            current_range,
            12,
        ),
    }


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
    # Fallback: check user settings key then env var (mirrors connector._property_id() logic)
    if not property_id:
        property_id = (
            str(context.settings.get("agent.google_analytics_property_id") or "").strip()
            or str(context.settings.get("GOOGLE_ANALYTICS_PROPERTY_ID") or "").strip()
            or str(os.getenv("GOOGLE_ANALYTICS_PROPERTY_ID", "")).strip()
            or None
        )
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

    # --- Pre-flight: verify auth + property before running 6 queries ---
    health = connector.health_check()
    if not health.ok:
        events.append(ToolTraceEvent(
            event_type="tool_failed", title="GA4 auth or property check failed",
            detail=health.message, data={"tool_id": tool_id},
        ))
        return ToolExecutionResult(
            summary="GA4 authentication or property check failed.",
            content=(
                "### GA4 Full Report — Connection Error\n\n"
                f"- Error: {health.message}\n\n"
                "**Possible causes**:\n"
                "- Google Analytics OAuth scope (`analytics.readonly`) not granted — reconnect Google and enable Analytics\n"
                "- Service account not added to the GA4 property in Google Analytics Property Access Management\n"
                "- `GOOGLE_ANALYTICS_PROPERTY_ID` not set\n"
            ),
            data={"available": False, "error": health.message},
            sources=[],
            next_steps=[
                "In Google Analytics → Admin → Property Access Management, add the service account email with Viewer role.",
                "Or reconnect Google OAuth in Settings and grant the Analytics read scope.",
                "Set GOOGLE_ANALYTICS_PROPERTY_ID to your GA4 numeric property ID.",
            ],
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
        # Derive aligned comparison and trend windows from the custom range.
        try:
            _ga4_relative = re.compile(r"^(\d+)daysAgo$")

            def _resolve_date(value: str) -> date:
                if value == "today":
                    return today
                if value == "yesterday":
                    return today - timedelta(days=1)
                m = _ga4_relative.match(value)
                if m:
                    return today - timedelta(days=int(m.group(1)))
                return date.fromisoformat(value)

            _start = _resolve_date(str(current_range.get("startDate", "30daysAgo")))
            _end = _resolve_date(str(current_range.get("endDate", "today")))
            _window = max(1, (_end - _start).days + 1)
            _prev_end = _start - timedelta(days=1)
            _prev_start = _prev_end - timedelta(days=_window - 1)
            _trend_start = _start - timedelta(days=_window * 2)
            prev_range = {
                "startDate": _prev_start.isoformat(),
                "endDate": _prev_end.isoformat(),
            }
            trend_range = {
                "startDate": _trend_start.isoformat(),
                "endDate": _end.isoformat(),
            }
        except Exception:
            # Fall back to defaults if date parsing fails.
            pass

    events.append(ToolTraceEvent(
        event_type="api_call_started", title="Fetch GA4 data",
        detail="Running 6 analytics queries", data={"property_id": property_id},
    ))

    # --- Run 6 queries ---
    query_results = _collect_query_results(
        connector=connector,
        property_id=property_id,
        current_range=current_range,
        prev_range=prev_range,
        trend_range=trend_range,
    )
    query_failures = {
        name: result.error
        for name, result in query_results.items()
        if result.error
    }
    trend_rows = query_results["trend"].rows
    channel_rows = query_results["channels_current"].rows
    channel_prev_rows = query_results["channels_previous"].rows
    pages_rows = query_results["pages"].rows
    device_rows = query_results["devices"].rows
    geo_rows = query_results["geography"].rows
    any_rows_available = any(result.rows for result in query_results.values())
    any_failure = bool(query_failures)
    all_failures_are_access = bool(query_failures) and all(
        _is_access_error(message or "")
        for message in query_failures.values()
    )

    auth_mode = " ".join(str(context.settings.get("agent.google_auth_mode") or "").split()).strip().lower()
    if (not any_rows_available) and (not any_failure) and auth_mode == "service_account":
        oauth_settings = dict(context.settings)
        oauth_settings["agent.google_auth_mode"] = "oauth"
        try:
            oauth_connector = get_connector_registry().build("google_analytics", settings=oauth_settings)
            oauth_query_results = _collect_query_results(
                connector=oauth_connector,
                property_id=property_id,
                current_range=current_range,
                prev_range=prev_range,
                trend_range=trend_range,
            )
            oauth_has_rows = any(result.rows for result in oauth_query_results.values())
            if oauth_has_rows:
                query_results = oauth_query_results
                query_failures = {
                    name: result.error
                    for name, result in query_results.items()
                    if result.error
                }
                trend_rows = query_results["trend"].rows
                channel_rows = query_results["channels_current"].rows
                channel_prev_rows = query_results["channels_previous"].rows
                pages_rows = query_results["pages"].rows
                device_rows = query_results["devices"].rows
                geo_rows = query_results["geography"].rows
                any_rows_available = True
                any_failure = bool(query_failures)
                all_failures_are_access = bool(query_failures) and all(
                    _is_access_error(message or "")
                    for message in query_failures.values()
                )
                events.append(
                    ToolTraceEvent(
                        event_type="tool_progress",
                        title="Retried GA4 queries with OAuth session",
                        detail="Service-account query returned no rows; OAuth retry returned data.",
                        data={"property_id": property_id},
                    )
                )
        except Exception as exc:
            events.append(
                ToolTraceEvent(
                    event_type="tool_progress",
                    title="OAuth retry skipped",
                    detail=f"Retry could not be completed: {exc}",
                    data={"property_id": property_id},
                )
            )

    events.append(ToolTraceEvent(
        event_type="api_call_completed", title="GA4 data fetched",
        detail=(
            f"trend={len(trend_rows)}, channels={len(channel_rows)}, pages={len(pages_rows)}, "
            f"failures={len(query_failures)}"
        ),
        data={
            "trend_rows": len(trend_rows),
            "channel_rows": len(channel_rows),
            "query_failures": query_failures,
        },
    ))

    if not any_rows_available and any_failure:
        failure_lines = [
            f"- **{name}**: {error}"
            for name, error in query_failures.items()
        ]
        events.append(ToolTraceEvent(
            event_type="tool_failed",
            title="GA4 report queries failed",
            detail="No GA4 rows returned from any report query.",
            data={"query_failures": query_failures, "tool_id": tool_id},
        ))
        if all_failures_are_access:
            remediation = [
                "Grant your connected Google account (or service account) Viewer access in GA4 Property Access Management.",
                "Confirm the numeric property ID is correct for the property you can access.",
                "Reconnect Google integration and ensure `analytics.readonly` scope is granted.",
            ]
            summary = "GA4 data access is blocked by permissions."
            heading = "### GA4 Full Report — Permission Blocked"
        else:
            remediation = [
                "Confirm the GA4 property ID is valid and active.",
                "Retry after checking Google Analytics API quota and connector authentication.",
                "Inspect per-query failures below and rerun the report.",
            ]
            summary = "GA4 full report failed because all report queries errored."
            heading = "### GA4 Full Report — Query Failure"
        return ToolExecutionResult(
            summary=summary,
            content="\n".join(
                [
                    heading,
                    "",
                    "No GA4 data could be retrieved for this run.",
                    "",
                    "#### Query failures",
                    *failure_lines,
                    "",
                    "#### How to fix",
                    *[f"- {item}" for item in remediation],
                ]
            ),
            data={
                "available": False,
                "error": "ga4_queries_failed",
                "property_id": property_id,
                "query_failures": query_failures,
            },
            sources=[],
            next_steps=remediation,
            events=events,
        )

    # --- Detect zero-data case (queries all succeeded but returned no rows) ---
    data_empty = not any_rows_available

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
    ]

    if data_empty:
        content_lines.extend([
            "> **DATA NOT AVAILABLE** — All GA4 queries returned 0 rows for this period.",
            "> All metrics below are zero. Do not draw performance conclusions or trend claims from this report.",
            "> Verify that the service account (or OAuth user) has Viewer access on this property, and that data collection is active for the selected date range.",
            "",
        ])

    if query_failures:
        content_lines.extend(
            [
                "## Data Quality Notes",
                "Some GA4 queries failed, but this report includes all available successful data.",
                "",
                "| Query | Status |",
                "|---|---|",
                *[
                    f"| {query_name} | failed ({error}) |"
                    for query_name, error in query_failures.items()
                ],
                "",
            ]
        )

    content_lines.extend(
        [
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
    )

    context.settings["__latest_analytics_full_report"] = {
        "property_id": property_id,
        "kpis": kpis,
        "data_empty": data_empty,
        "chart_keys": list(charts.keys()),
        "top_channel": top_channel,
        "top_page": top_page,
        "query_failures": query_failures,
        "channel_rows": channel_rows[:20],
        "pages_rows": pages_rows[:20],
        "device_rows": device_rows[:10],
        "geo_rows": geo_rows[:12],
        "trend_rows": trend_rows[:90],
    }

    events.append(ToolTraceEvent(
        event_type="tool_progress", title="GA4 full report ready",
        detail=f"charts={len(charts)}, kpis captured, query_failures={len(query_failures)}",
        data={
            "charts": list(charts.keys()),
            "property_id": property_id,
            "query_failures": query_failures,
        },
    ))

    summary_prefix = "No data available — " if data_empty else ""
    return ToolExecutionResult(
        summary=f"{summary_prefix}GA4 full report: {kpis['sessions']:,} sessions, {kpis['conversions']:,} conversions, {len(charts)} charts.",
        content="\n".join(content_lines),
        data={
            "property_id": property_id,
            "kpis": kpis,
            "data_empty": data_empty,
            "charts": charts,
            "query_failures": query_failures,
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
