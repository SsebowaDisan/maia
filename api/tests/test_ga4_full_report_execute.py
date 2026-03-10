from __future__ import annotations

from typing import Any
from unittest.mock import patch

from api.services.agent.connectors.base import ConnectorError, ConnectorHealth
from api.services.agent.tools.base import ToolExecutionContext
from api.services.agent.tools.ga4_full_report_execute import execute_ga4_full_report


def _context() -> ToolExecutionContext:
    return ToolExecutionContext(
        user_id="user-1",
        tenant_id="tenant-1",
        conversation_id="conv-1",
        run_id="run-1",
        mode="company_agent",
        settings={},
    )


def _ga_response(
    *,
    dimension: str,
    metrics: list[str],
    rows: list[tuple[str, list[str]]],
) -> dict[str, Any]:
    return {
        "dimensionHeaders": [{"name": dimension}],
        "metricHeaders": [{"name": metric_name} for metric_name in metrics],
        "rows": [
            {
                "dimensionValues": [{"value": dimension_value}],
                "metricValues": [{"value": metric_value} for metric_value in metric_values],
            }
            for dimension_value, metric_values in rows
        ],
    }


class _PermissionDeniedConnector:
    connector_id = "google_analytics"

    def health_check(self) -> ConnectorHealth:
        return ConnectorHealth(self.connector_id, True, "configured")

    def run_report(self, **kwargs: Any) -> dict[str, Any]:
        del kwargs
        raise ConnectorError("request failed (403): insufficient permissions for this property")


class _PartialDataConnector:
    connector_id = "google_analytics"

    def health_check(self) -> ConnectorHealth:
        return ConnectorHealth(self.connector_id, True, "configured")

    def run_report(
        self,
        *,
        property_id: str | None = None,
        date_ranges: list[dict[str, str]] | None = None,
        dimensions: list[str] | None = None,
        metrics: list[str] | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        del property_id, limit
        dim = (dimensions or [""])[0]
        metric_names = list(metrics or [])
        start = ((date_ranges or [{}])[0]).get("startDate")

        if dim == "country":
            raise ConnectorError("request failed (429): quota exhausted")
        if dim == "date":
            return _ga_response(
                dimension="date",
                metrics=metric_names,
                rows=[
                    ("20260301", ["100", "80", "120"]),
                    ("20260302", ["120", "90", "150"]),
                    ("20260303", ["110", "85", "140"]),
                ],
            )
        if dim == "sessionDefaultChannelGroup":
            if start == "60daysAgo":
                return _ga_response(
                    dimension="sessionDefaultChannelGroup",
                    metrics=metric_names,
                    rows=[
                        ("Organic Search", ["80", "12", "0.42"]),
                        ("Direct", ["50", "8", "0.35"]),
                    ],
                )
            return _ga_response(
                dimension="sessionDefaultChannelGroup",
                metrics=metric_names,
                rows=[
                    ("Organic Search", ["120", "18", "0.40"]),
                    ("Direct", ["70", "10", "0.36"]),
                ],
            )
        if dim == "pagePath":
            return _ga_response(
                dimension="pagePath",
                metrics=metric_names,
                rows=[
                    ("/home", ["200", "65", "0.33"]),
                    ("/pricing", ["120", "58", "0.38"]),
                ],
            )
        if dim == "deviceCategory":
            return _ga_response(
                dimension="deviceCategory",
                metrics=metric_names,
                rows=[
                    ("desktop", ["140"]),
                    ("mobile", ["50"]),
                ],
            )
        raise ConnectorError(f"unexpected dimensions: {dim}")


class _StubRegistry:
    def __init__(self, connector: Any) -> None:
        self._connector = connector

    def build(self, connector_id: str, settings: dict[str, Any] | None = None) -> Any:
        del settings
        assert connector_id == "google_analytics"
        return self._connector


class _AuthModeAwareRegistry:
    def build(self, connector_id: str, settings: dict[str, Any] | None = None) -> Any:
        assert connector_id == "google_analytics"
        mode = " ".join(str((settings or {}).get("agent.google_auth_mode") or "").split()).strip().lower()
        if mode == "oauth":
            return _PartialDataConnector()
        return _ServiceAccountZeroRowsConnector()


class _ServiceAccountZeroRowsConnector:
    connector_id = "google_analytics"

    def health_check(self) -> ConnectorHealth:
        return ConnectorHealth(self.connector_id, True, "configured")

    def run_report(
        self,
        *,
        property_id: str | None = None,
        date_ranges: list[dict[str, str]] | None = None,
        dimensions: list[str] | None = None,
        metrics: list[str] | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        del property_id, date_ranges, limit
        return _ga_response(dimension=(dimensions or ["dimension"])[0], metrics=list(metrics or []), rows=[])


def test_ga4_full_report_returns_explicit_permission_block_when_all_queries_fail() -> None:
    with patch(
        "api.services.agent.tools.ga4_full_report_execute.get_connector_registry",
        return_value=_StubRegistry(_PermissionDeniedConnector()),
    ):
        result = execute_ga4_full_report(
            context=_context(),
            prompt="prepare full ga report",
            params={"property_id": "123456789"},
            tool_id="analytics.ga4.full_report",
        )

    assert result.data["available"] is False
    assert result.data["error"] == "ga4_queries_failed"
    assert "Permission Blocked" in result.content
    assert "Query failures" in result.content
    assert len(result.data["query_failures"]) == 6
    assert any(event.event_type == "tool_failed" for event in result.events)


def test_ga4_full_report_keeps_tables_and_charts_when_partially_successful() -> None:
    with patch(
        "api.services.agent.tools.ga4_full_report_execute.get_connector_registry",
        return_value=_StubRegistry(_PartialDataConnector()),
    ):
        result = execute_ga4_full_report(
            context=_context(),
            prompt="prepare full ga report",
            params={"property_id": "123456789"},
            tool_id="analytics.ga4.full_report",
        )

    assert result.data.get("available") is not False
    assert "## Data Quality Notes" in result.content
    assert "| Metric | Current 30d | Previous 30d | Change |" in result.content
    assert "query_failures" in result.data
    assert "geography" in result.data["query_failures"]
    assert result.data["charts"]


def test_ga4_full_report_retries_with_oauth_when_service_account_returns_no_rows() -> None:
    context = _context()
    context.settings["agent.google_auth_mode"] = "service_account"
    with patch(
        "api.services.agent.tools.ga4_full_report_execute.get_connector_registry",
        return_value=_AuthModeAwareRegistry(),
    ):
        result = execute_ga4_full_report(
            context=context,
            prompt="prepare full ga report",
            params={"property_id": "123456789"},
            tool_id="analytics.ga4.full_report",
        )

    assert result.data.get("available") is not False
    assert result.data["kpis"]["sessions"] > 0
    assert result.data["charts"]
    assert any(
        event.title == "Retried GA4 queries with OAuth session"
        for event in result.events
    )
