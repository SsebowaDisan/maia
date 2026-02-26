from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from api.services.agent.tools.base import ToolExecutionContext
from api.services.agent.tools.document_highlight_tools import DocumentHighlightExtractTool
from api.services.agent.tools.document_tools import DocumentCreateTool
from api.services.agent.tools.invoice_tools import InvoiceCreateTool, InvoiceSendTool
from api.services.agent.tools.data_tools import ReportGenerationTool
from api.services.agent.tools.workspace_tools import WorkspaceResearchNotesTool, WorkspaceSheetsTrackStepTool


def _context() -> ToolExecutionContext:
    return ToolExecutionContext(
        user_id="u1",
        tenant_id="t1",
        conversation_id="c1",
        run_id="run-123456",
        mode="company_agent",
        settings={},
    )


def test_document_create_tool_writes_local_markdown() -> None:
    result = DocumentCreateTool().execute(
        context=_context(),
        prompt="draft",
        params={"title": "Ops Brief", "body": "Key operations updates.", "provider": "local"},
    )
    path = Path(result.data["path"])
    assert path.exists()
    assert path.read_text(encoding="utf-8").startswith("# Ops Brief")


def test_document_create_tool_includes_copied_highlights() -> None:
    context = _context()
    context.settings["__copied_highlights"] = [
        {
            "source": "website",
            "color": "green",
            "word": "axon",
            "text": "Axon Group provides industrial solutions.",
            "reference": "https://axongroup.com",
        }
    ]
    result = DocumentCreateTool().execute(
        context=context,
        prompt="draft",
        params={
            "title": "Highlight Draft",
            "body": "Captured highlights below.",
            "provider": "local",
            "include_copied_highlights": True,
        },
    )
    path = Path(result.data["path"])
    content = path.read_text(encoding="utf-8")
    assert "## Copied Highlights" in content
    assert "[green]" in content
    assert "Axon Group provides industrial solutions." in content


def test_document_highlight_extract_tool_stashes_copied_entries(monkeypatch) -> None:
    context = _context()
    context.settings["__selected_file_ids"] = ["file-1"]
    monkeypatch.setattr(
        "api.services.agent.tools.document_highlight_tools._load_source_chunks",
        lambda **_: [
            {
                "source_id": "file-1",
                "source_name": "CompanyProfile.pdf",
                "page_label": "1",
                "text": "Axon Group delivers control and heat exchange industrial systems.",
            }
        ],
    )
    result = DocumentHighlightExtractTool().execute(
        context=context,
        prompt="highlight key words",
        params={"words": ["Axon", "control"], "highlight_color": "green"},
    )
    assert result.data.get("highlight_color") == "green"
    assert result.data.get("highlighted_words")
    assert context.settings.get("__copied_highlights")
    assert any(event.event_type == "highlights_detected" for event in result.events)


def test_invoice_create_tool_generates_pdf_artifact() -> None:
    result = InvoiceCreateTool().execute(
        context=_context(),
        prompt="invoice",
        params={
            "invoice_number": "INV-TEST-001",
            "customer": "Acme",
            "currency": "USD",
            "line_items": [{"description": "Service", "quantity": 2, "unit_price": 50}],
            "tax_rate": 10,
        },
    )
    pdf_path = Path(result.data["pdf_path"])
    assert pdf_path.exists()
    assert pdf_path.suffix.lower() == ".pdf"
    assert result.data["total"] == "110.00"


class _StubInvoiceConnector:
    def post_invoice(self, payload):
        return {"provider": "stub-accounting", "status": "queued", "invoice_number": payload["invoice_number"]}


class _StubWorkspaceConnector:
    def __init__(self) -> None:
        self.docs_insert_calls = []
        self.sheet_append_calls = []

    def create_docs_document(self, *, title: str):
        del title
        return {"documentId": "doc-1"}

    def docs_insert_text(self, *, document_id: str, text: str):
        self.docs_insert_calls.append((document_id, text))

    def create_spreadsheet(self, *, title: str, sheet_title: str):
        del title, sheet_title
        return {"spreadsheet_id": "sheet-1", "spreadsheet_url": "https://example.com/sheet-1"}

    def append_sheet_values(self, *, spreadsheet_id: str, sheet_range: str, values: list[list[object]]):
        self.sheet_append_calls.append((spreadsheet_id, sheet_range, values))
        return {"updates": {"updatedRows": len(values)}}


class _RegistryStub:
    def __init__(self, workspace: _StubWorkspaceConnector) -> None:
        self.workspace = workspace

    def build(self, connector_id: str, settings: dict | None = None):
        del settings
        if connector_id == "invoice":
            return _StubInvoiceConnector()
        if connector_id == "google_workspace":
            return self.workspace
        raise AssertionError(connector_id)


def test_invoice_send_tool_uses_invoice_connector() -> None:
    workspace = _StubWorkspaceConnector()
    with patch("api.services.agent.tools.invoice_tools.get_connector_registry", return_value=_RegistryStub(workspace)):
        result = InvoiceSendTool().execute(
            context=_context(),
            prompt="send INV-TEST-001",
            params={"invoice_number": "INV-TEST-001"},
        )
    assert "queued" in result.content


def test_workspace_research_notes_tool_appends_note() -> None:
    workspace = _StubWorkspaceConnector()
    context = _context()
    with patch("api.services.agent.tools.workspace_tools.get_connector_registry", return_value=_RegistryStub(workspace)):
        result = WorkspaceResearchNotesTool().execute(
            context=context,
            prompt="note",
            params={"note": "Important finding from source."},
        )
    assert result.data["document_id"] == "doc-1"
    assert workspace.docs_insert_calls


def test_workspace_sheets_track_step_tool_appends_rows() -> None:
    workspace = _StubWorkspaceConnector()
    context = _context()
    with patch("api.services.agent.tools.workspace_tools.get_connector_registry", return_value=_RegistryStub(workspace)):
        result = WorkspaceSheetsTrackStepTool().execute(
            context=context,
            prompt="track",
            params={"step_name": "Analyze", "status": "completed", "detail": "done"},
        )
    assert result.data["spreadsheet_id"] == "sheet-1"
    assert len(workspace.sheet_append_calls) >= 2  # header row + step row


def test_report_generation_respects_location_objective_without_hardcoded_phrase() -> None:
    context = _context()
    context.settings["__latest_browser_findings"] = {
        "title": "Axon Group | Industrial solutions square",
        "url": "https://axongroup.com/products-and-solutions",
        "keywords": ["axon", "solutions", "control"],
        "excerpt": "About Axon Our solutions Fluids Air Powder Noise Heat exchange Control.",
    }
    result = ReportGenerationTool().execute(
        context=context,
        prompt="Analyze axon and tell where they are located",
        params={
            "title": "Website Analysis Report",
            "summary": "Find where the company is located and report verified location evidence.",
        },
    )
    report_text = str(result.content or "")
    assert "No explicit headquarters/address was confirmed" in report_text
    assert "appears to focus on industrial solutions and related services" not in report_text
