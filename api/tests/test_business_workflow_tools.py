from __future__ import annotations

from unittest.mock import patch

from api.services.agent.tools.base import ToolExecutionContext
from api.services.agent.tools.business_workflow_tools import (
    BusinessCloudIncidentDigestEmailTool,
    BusinessGa4KpiSheetReportTool,
    BusinessRoutePlanTool,
)


def _context() -> ToolExecutionContext:
    return ToolExecutionContext(
        user_id="u1",
        tenant_id="t1",
        conversation_id="c1",
        run_id="run-biz-001",
        mode="company_agent",
        settings={},
    )


class _MapsStub:
    def distance_matrix(self, *, origins, destinations, mode):
        _ = origins, mode
        return {
            "rows": [
                {
                    "elements": [
                        {"status": "OK", "distance": {"text": "10 km"}, "duration": {"text": "20 mins", "value": 1200}},
                        {"status": "OK", "distance": {"text": "30 km"}, "duration": {"text": "45 mins", "value": 2700}},
                    ][: len(destinations)]
                }
            ]
        }


class _WorkspaceStub:
    def create_spreadsheet(self, *, title: str, sheet_title: str = "Tracker"):
        _ = title, sheet_title
        return {
            "spreadsheet_id": "sheet-created-1",
            "spreadsheet_url": "https://docs.google.com/spreadsheets/d/sheet-created-1/edit",
        }

    def append_sheet_values(self, *, spreadsheet_id: str, sheet_range: str, values):
        _ = spreadsheet_id, sheet_range, values
        return {"updates": {"updatedRows": 5}}


class _AnalyticsStub:
    def run_report(self, **kwargs):
        _ = kwargs
        return {
            "rows": [
                {
                    "dimensionValues": [{"value": "2026-03-01"}],
                    "metricValues": [{"value": "100"}, {"value": "80"}, {"value": "5"}],
                }
            ]
        }


class _GoogleApiHubStub:
    def call_json_api(self, **kwargs):
        _ = kwargs
        return {
            "entries": [
                {"severity": "ERROR", "timestamp": "2026-03-01T10:00:00Z", "textPayload": "Service unavailable"},
                {"severity": "WARNING", "timestamp": "2026-03-01T10:10:00Z", "textPayload": "Retry loop"},
            ]
        }


class _GmailStub:
    def create_draft(self, *, to: str, subject: str, body: str, sender: str = ""):
        _ = to, subject, body, sender
        return {"draft": {"id": "draft-123", "message": {"id": "msg-1"}}}

    def send_message(self, *, to: str, subject: str, body: str, sender: str = ""):
        _ = to, subject, body, sender
        return {"id": "msg-123", "threadId": "th-1"}


class _RegistryStub:
    def build(self, connector_id: str, settings=None):
        _ = settings
        if connector_id == "google_maps":
            return _MapsStub()
        if connector_id == "google_workspace":
            return _WorkspaceStub()
        if connector_id == "google_analytics":
            return _AnalyticsStub()
        if connector_id == "google_api_hub":
            return _GoogleApiHubStub()
        if connector_id == "gmail":
            return _GmailStub()
        raise AssertionError(f"Unexpected connector id: {connector_id}")


def test_business_route_plan_emits_api_and_sheet_events() -> None:
    tool = BusinessRoutePlanTool()
    with patch(
        "api.services.agent.tools.business_workflow_tools.get_connector_registry",
        return_value=_RegistryStub(),
    ):
        result = tool.execute(
            context=_context(),
            prompt="Plan route from Kampala office to Entebbe Airport and Jinja",
            params={"spreadsheet_id": "sheet-123"},
        )
    event_types = [event.event_type for event in result.events]
    assert "api_call_started" in event_types
    assert "api_call_completed" in event_types
    assert "sheets.append_completed" in event_types
    started = next(event for event in result.events if event.event_type == "api_call_started")
    assert started.data.get("scene_surface") == "browser"


def test_business_ga4_weekly_report_creates_sheet_when_missing() -> None:
    tool = BusinessGa4KpiSheetReportTool()
    with patch(
        "api.services.agent.tools.business_workflow_tools.get_connector_registry",
        return_value=_RegistryStub(),
    ):
        result = tool.execute(
            context=_context(),
            prompt="Create weekly GA4 KPI report in sheets",
            params={},
        )
    assert result.data["spreadsheet_id"] == "sheet-created-1"
    event_types = [event.event_type for event in result.events]
    assert "api_call_started" in event_types
    assert "sheets.append_completed" in event_types


def test_business_cloud_incident_digest_creates_draft_with_visible_events() -> None:
    tool = BusinessCloudIncidentDigestEmailTool()
    with patch(
        "api.services.agent.tools.business_workflow_tools.get_connector_registry",
        return_value=_RegistryStub(),
    ):
        result = tool.execute(
            context=_context(),
            prompt="Send cloud incident digest email to ops@example.com",
            params={"project_id": "demo-project", "to": "ops@example.com", "send": False},
        )
    event_types = [event.event_type for event in result.events]
    assert "api_call_started" in event_types
    assert "api_call_completed" in event_types
    assert "email_draft_create" in event_types
    assert "email_ready_to_send" in event_types
    assert result.data["delivery"]["sent"] is False
