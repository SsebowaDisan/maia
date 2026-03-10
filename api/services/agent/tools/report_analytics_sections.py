from __future__ import annotations

"""GA4 / analytics data-source report sections.

Pattern for adding a new data source (e.g. SAP, Salesforce):
  1. Create report_<source>_sections.py alongside this file.
  2. Implement the three functions: section_lines, insight_highlights, insight_paragraphs.
  3. Each function must guard on its own settings key and return [] when absent.
  4. Wire the new functions into data_tools_helpers.py re-export shim and data_tools.py.
"""

from typing import Any


def _analytics_section_lines(settings: dict[str, Any]) -> list[str]:
    """Render GA4 data tables (profile, visualization, full report breakdown)."""
    lines: list[str] = []
    profile = settings.get("__latest_data_profile")
    if isinstance(profile, dict):
        lines.extend(
            [
                "### Data Profile Snapshot",
                "| Metric | Value |",
                "|---|---|",
                f"| Rows | {int(profile.get('row_count') or 0)} |",
                f"| Columns | {int(profile.get('column_count') or 0)} |",
                f"| Numeric columns | {len(profile.get('numeric_columns') or [])} |",
            ]
        )
        correlations = profile.get("top_correlations")
        if isinstance(correlations, list) and correlations:
            lines.extend(["", "| Strong correlation | Value |", "|---|---|"])
            for item in correlations[:6]:
                if not isinstance(item, dict):
                    continue
                left = " ".join(str(item.get("left") or "").split()).strip()
                right = " ".join(str(item.get("right") or "").split()).strip()
                value = item.get("correlation")
                if not left or not right:
                    continue
                lines.append(f"| {left} vs {right} | {value} |")

    visualization = settings.get("__latest_data_visualization")
    if isinstance(visualization, dict):
        lines.extend(
            [
                "",
                "### Visualization Snapshot",
                "| Field | Value |",
                "|---|---|",
                f"| Chart type | {str(visualization.get('chart_type') or 'n/a')} |",
                f"| Rows plotted | {int(visualization.get('row_count') or 0)} |",
                f"| X axis | {str(visualization.get('x') or 'n/a')} |",
                f"| Y axis | {str(visualization.get('y') or 'n/a')} |",
                f"| Artifact path | {str(visualization.get('path') or 'n/a')} |",
            ]
        )

    ga4_report = settings.get("__latest_analytics_report")
    if isinstance(ga4_report, dict):
        dimensions = ga4_report.get("dimensions")
        metrics = ga4_report.get("metrics")
        lines.extend(
            [
                "",
                "### Analytics API Snapshot",
                "| Metric | Value |",
                "|---|---|",
                f"| Property ID | {str(ga4_report.get('property_id') or 'n/a')} |",
                f"| Rows returned | {int(ga4_report.get('row_count') or 0)} |",
                f"| Dimensions | {', '.join(str(item) for item in (dimensions or [])[:8]) or 'n/a'} |",
                f"| Metrics | {', '.join(str(item) for item in (metrics or [])[:8]) or 'n/a'} |",
            ]
        )

    ga4_full_report = settings.get("__latest_analytics_full_report")
    if not isinstance(ga4_full_report, dict) or not ga4_full_report:
        return lines

    kpis = ga4_full_report.get("kpis")
    kpi_rows = kpis if isinstance(kpis, dict) else {}
    query_failures = (
        ga4_full_report.get("query_failures")
        if isinstance(ga4_full_report.get("query_failures"), dict)
        else {}
    )
    chart_keys = (
        [str(item).strip() for item in ga4_full_report.get("chart_keys", []) if str(item).strip()]
        if isinstance(ga4_full_report.get("chart_keys"), list)
        else []
    )
    lines.extend(
        [
            "",
            "### GA4 Full Report Snapshot",
            "| Metric | Value |",
            "|---|---|",
            f"| Property ID | {str(ga4_full_report.get('property_id') or 'n/a')} |",
            f"| Sessions (30d) | {kpi_rows.get('sessions', 'n/a')} |",
            f"| Users (30d) | {kpi_rows.get('users', 'n/a')} |",
            f"| Conversions (30d) | {kpi_rows.get('conversions', 'n/a')} |",
            f"| Bounce rate (30d) | {kpi_rows.get('bounce_rate', 'n/a')}% |",
            f"| Top channel | {str(ga4_full_report.get('top_channel') or 'n/a')} |",
            f"| Top page | {str(ga4_full_report.get('top_page') or 'n/a')} |",
            f"| Chart payloads | {len(chart_keys)} |",
        ]
    )
    if chart_keys:
        lines.append(f"| Chart keys | {', '.join(chart_keys[:8])} |")
    if query_failures:
        lines.extend(["", "| Failed query | Detail |", "|---|---|"])
        for query_name, detail in list(query_failures.items())[:6]:
            lines.append(f"| {str(query_name)} | {str(detail)} |")

    channel_rows = (
        ga4_full_report.get("channel_rows")
        if isinstance(ga4_full_report.get("channel_rows"), list)
        else []
    )
    if channel_rows:
        lines.extend(
            [
                "",
                "#### Channel Performance",
                "| Channel | Sessions | Conversions | Bounce Rate |",
                "|---|---|---|---|",
            ]
        )
        for row in channel_rows[:8]:
            if not isinstance(row, dict):
                continue
            channel = str(row.get("sessionDefaultChannelGroup") or "n/a")
            sessions = int(float(row.get("sessions") or 0))
            conversions = int(float(row.get("conversions") or 0))
            bounce = round(float(row.get("bounceRate") or 0) * 100, 1)
            lines.append(f"| {channel} | {sessions:,} | {conversions:,} | {bounce}% |")

    pages_rows = (
        ga4_full_report.get("pages_rows")
        if isinstance(ga4_full_report.get("pages_rows"), list)
        else []
    )
    if pages_rows:
        lines.extend(
            [
                "",
                "#### Top Pages",
                "| Page | Views | Avg Session Duration | Bounce Rate |",
                "|---|---|---|---|",
            ]
        )
        for row in pages_rows[:10]:
            if not isinstance(row, dict):
                continue
            page = str(row.get("pagePath") or "n/a")
            views = int(float(row.get("screenPageViews") or 0))
            duration_seconds = int(float(row.get("averageSessionDuration") or 0))
            minutes, seconds = divmod(max(duration_seconds, 0), 60)
            bounce = round(float(row.get("bounceRate") or 0) * 100, 1)
            lines.append(f"| {page[:80]} | {views:,} | {minutes}m {seconds:02d}s | {bounce}% |")

    device_rows = (
        ga4_full_report.get("device_rows")
        if isinstance(ga4_full_report.get("device_rows"), list)
        else []
    )
    if device_rows:
        total_sessions = max(
            1.0,
            sum(float(row.get("sessions") or 0) for row in device_rows if isinstance(row, dict)),
        )
        lines.extend(["", "#### Device Split", "| Device | Sessions | Share |", "|---|---|---|"])
        for row in device_rows[:8]:
            if not isinstance(row, dict):
                continue
            device = str(row.get("deviceCategory") or "n/a")
            sessions = float(row.get("sessions") or 0)
            share = round((sessions / total_sessions) * 100, 1)
            lines.append(f"| {device} | {int(sessions):,} | {share}% |")

    geo_rows = (
        ga4_full_report.get("geo_rows")
        if isinstance(ga4_full_report.get("geo_rows"), list)
        else []
    )
    if geo_rows:
        lines.extend(["", "#### Top Countries", "| Country | Sessions | Users |", "|---|---|---|"])
        for row in geo_rows[:10]:
            if not isinstance(row, dict):
                continue
            country = str(row.get("country") or "n/a")
            sessions = int(float(row.get("sessions") or 0))
            users = int(float(row.get("totalUsers") or 0))
            lines.append(f"| {country} | {sessions:,} | {users:,} |")
    return lines


def _analytics_insight_highlights(settings: dict[str, Any]) -> list[str]:
    ga4_full_report = settings.get("__latest_analytics_full_report")
    if not isinstance(ga4_full_report, dict) or not ga4_full_report:
        return []
    if ga4_full_report.get("data_empty"):
        return [
            "GA4 returned 0 rows for this property and period — no performance data is available.",
            "Do not draw trend conclusions from this report. Verify property access and that data collection is active.",
        ]
    kpis = ga4_full_report.get("kpis")
    if not isinstance(kpis, dict):
        kpis = {}
    chart_keys = (
        [str(item).strip() for item in ga4_full_report.get("chart_keys", []) if str(item).strip()]
        if isinstance(ga4_full_report.get("chart_keys"), list)
        else []
    )

    def _fmt_change(value: Any) -> str:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return "n/a"
        prefix = "+" if numeric > 0 else ""
        return f"{prefix}{numeric:.1f}%"

    sessions = int(float(kpis.get("sessions") or 0))
    users = int(float(kpis.get("users") or 0))
    conversions = int(float(kpis.get("conversions") or 0))
    bounce_rate = float(kpis.get("bounce_rate") or 0)
    top_channel = str(ga4_full_report.get("top_channel") or "n/a")
    top_page = str(ga4_full_report.get("top_page") or "n/a")

    highlights = [
        f"Traffic baseline: {sessions:,} sessions, {users:,} users, and {conversions:,} conversions in the last 30 days.",
        (
            "Period-over-period movement: sessions "
            f"{_fmt_change(kpis.get('sessions_change'))}, users {_fmt_change(kpis.get('users_change'))}, "
            f"conversions {_fmt_change(kpis.get('conversions_change'))}."
        ),
        (
            f"Engagement quality: weighted bounce rate is {bounce_rate:.1f}% "
            f"({_fmt_change(kpis.get('bounce_rate_change'))} vs previous period)."
        ),
        f"Primary acquisition channel: {top_channel}. Highest-traffic page: {top_page}.",
    ]
    if chart_keys:
        highlights.append(
            f"Visualization coverage: {len(chart_keys)} chart payloads prepared ({', '.join(chart_keys[:6])})."
        )
    return highlights


def _analytics_insight_paragraphs(settings: dict[str, Any]) -> list[str]:
    ga4_full_report = settings.get("__latest_analytics_full_report")
    if not isinstance(ga4_full_report, dict) or not ga4_full_report:
        return []
    if ga4_full_report.get("data_empty"):
        return [
            "GA4 returned zero rows for this property and period. "
            "No traffic, conversion, or engagement data is available. "
            "Performance claims cannot be made from this run — verify property access before interpreting any figures.",
        ]
    kpis = ga4_full_report.get("kpis")
    if not isinstance(kpis, dict):
        return []

    def _signed_percent(value: Any) -> str:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return "n/a"
        prefix = "+" if numeric > 0 else ""
        return f"{prefix}{numeric:.1f}%"

    sessions = int(float(kpis.get("sessions") or 0))
    users = int(float(kpis.get("users") or 0))
    conversions = int(float(kpis.get("conversions") or 0))
    bounce_rate = float(kpis.get("bounce_rate") or 0)
    top_channel = str(ga4_full_report.get("top_channel") or "n/a")
    top_page = str(ga4_full_report.get("top_page") or "n/a")

    return [
        (
            f"Performance summary: the latest 30-day window captured {sessions:,} sessions, "
            f"{users:,} users, and {conversions:,} conversions. "
            "These are the core operating baselines for traffic quality and demand capture."
        ),
        (
            "Trend interpretation: period-over-period movement indicates "
            f"sessions {_signed_percent(kpis.get('sessions_change'))}, users {_signed_percent(kpis.get('users_change'))}, "
            f"and conversions {_signed_percent(kpis.get('conversions_change'))}. "
            f"Bounce rate is {bounce_rate:.1f}% ({_signed_percent(kpis.get('bounce_rate_change'))} vs previous period), "
            "which should be reviewed alongside landing-page intent alignment."
        ),
        (
            f"Acquisition and content concentration: top channel is {top_channel} and the highest-traffic page is "
            f"{top_page}. Prioritize budget and content iterations around these high-impact surfaces while monitoring "
            "secondary channels for diversification opportunities."
        ),
    ]
