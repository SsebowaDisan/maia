from __future__ import annotations

from unittest.mock import patch

from api.services.agent.tools.base import ToolExecutionContext
from api.services.agent.tools.business_office_tools import (
    BusinessInvoiceWorkflowTool,
    BusinessMeetingSchedulerTool,
    BusinessProposalWorkflowTool,
)


def _context() -> ToolExecutionContext:
    return ToolExecutionContext(
        user_id="u1",
        tenant_id="t1",
        conversation_id="c1",
        run_id="run-office-001",
        mode="company_agent",
        settings={},
    )


class _WorkspaceStub:
    def append_sheet_values(self, *, spreadsheet_id: str, sheet_range: str, values):
        _ = spreadsheet_id, sheet_range, values
        return {"updates": {"updatedRows": 3}}

    def create_docs_document(self, title: str):
        _ = title
        return {"documentId": "doc-123"}

    def docs_insert_text(self, *, document_id: str, text: str):
        _ = document_id, text
        return {"ok": True}


class _CalendarStub:
    def create_event(
        self,
        *,
        summary: str,
        start_iso: str,
        end_iso: str,
        description: str = "",
        attendees: list[str] | None = None,
        calendar_id: str = "primary",
    ):
        _ = summary, start_iso, end_iso, description, attendees, calendar_id
        return {"id": "evt-123", "htmlLink": "https://calendar.google.com/event?eid=evt-123"}


class _GmailStub:
    def create_draft(self, *, to: str, subject: str, body: str, sender: str = ""):
        _ = to, subject, body, sender
        return {"draft": {"id": "draft-xyz", "message": {"id": "msg-xyz"}}}


class _InvoiceStub:
    def post_invoice(self, payload):
        _ = payload
        return {"provider": "xero", "status": "accepted", "invoice_reference": "INV-TEST"}


class _RegistryStub:
    def build(self, connector_id: str, settings=None):
        _ = settings
        if connector_id == "google_workspace":
            return _WorkspaceStub()
        if connector_id == "google_calendar":
            return _CalendarStub()
        if connector_id == "gmail":
            return _GmailStub()
        if connector_id == "invoice":
            return _InvoiceStub()
        raise AssertionError(f"Unexpected connector id: {connector_id}")


def test_business_invoice_workflow_emits_visible_events_and_sheet_logging() -> None:
    tool = BusinessInvoiceWorkflowTool()
    with patch(
        "api.services.agent.tools.business_office_tools.get_connector_registry",
        return_value=_RegistryStub(),
    ), patch(
        "api.services.agent.tools.invoice_tools.get_connector_registry",
        return_value=_RegistryStub(),
    ):
        result = tool.execute(
            context=_context(),
            prompt="Create and send invoice INV-123 to customer@example.com for USD 500",
            params={"spreadsheet_id": "sheet-123", "send": True},
        )
    event_types = [event.event_type for event in result.events]
    assert "doc_open" in event_types
    assert "sheets.append_completed" in event_types
    assert "tool_progress" in event_types
    assert result.data["delivery"]["requested"] is True


def test_business_meeting_scheduler_creates_calendar_and_agenda() -> None:
    tool = BusinessMeetingSchedulerTool()
    with patch(
        "api.services.agent.tools.business_office_tools.get_connector_registry",
        return_value=_RegistryStub(),
    ):
        result = tool.execute(
            context=_context(),
            prompt="Schedule a meeting with teamlead@example.com",
            params={},
        )
    event_types = [event.event_type for event in result.events]
    assert "tool_completed" in event_types
    assert "docs.create_completed" in event_types
    assert result.data["event_id"] == "evt-123"
    assert result.data["agenda_doc_id"] == "doc-123"


def test_business_proposal_workflow_creates_doc_and_email_draft() -> None:
    tool = BusinessProposalWorkflowTool()
    with patch(
        "api.services.agent.tools.business_office_tools.get_connector_registry",
        return_value=_RegistryStub(),
    ):
        result = tool.execute(
            context=_context(),
            prompt="Create a proposal and send to ceo@example.com",
            params={"title": "Acme Expansion Proposal"},
        )
    event_types = [event.event_type for event in result.events]
    assert "docs.create_completed" in event_types
    assert "email_draft_create" in event_types
    assert result.data["email_draft_id"] == "draft-xyz"
