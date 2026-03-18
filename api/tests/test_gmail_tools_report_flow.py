from __future__ import annotations

from pathlib import Path
import tempfile
from unittest.mock import patch
import unittest

from api.services.agent.tools.base import ToolExecutionContext
from api.services.agent.tools.gmail_tools import GmailDraftTool, GmailSendTool


class _StubGmailConnector:
    def __init__(self) -> None:
        self.last_draft: dict[str, str] = {}
        self.last_send: dict[str, str] = {}
        self.last_send_draft: dict[str, str] = {}
        self.last_send_with_attachments: dict[str, object] = {}
        self.attachments: list[dict[str, str]] = []

    def create_draft(self, *, to: str, subject: str, body: str, sender: str = "") -> dict[str, object]:
        self.last_draft = {"to": to, "subject": subject, "body": body, "sender": sender}
        return {"draft": {"id": "d-1", "message": {"id": "m-1"}}}

    def send_message(self, *, to: str, subject: str, body: str, sender: str = "") -> dict[str, str]:
        self.last_send = {"to": to, "subject": subject, "body": body, "sender": sender}
        return {"id": "m-2", "threadId": "t-2"}

    def add_attachment(
        self,
        *,
        draft_id: str,
        file_id: str | None = None,
        local_path: str | None = None,
    ) -> dict[str, object]:
        self.attachments.append(
            {
                "draft_id": draft_id,
                "file_id": str(file_id or ""),
                "local_path": str(local_path or ""),
            }
        )
        return {"ok": True}

    def send_draft(self, *, draft_id: str) -> dict[str, str]:
        self.last_send_draft = {"draft_id": draft_id}
        return {"id": "m-draft-1"}

    def send_message_with_attachments(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        attachments: list[dict[str, str]],
        sender: str = "",
    ) -> dict[str, object]:
        self.last_send_with_attachments = {
            "to": to,
            "subject": subject,
            "body": body,
            "attachments": attachments,
            "sender": sender,
        }
        return {"id": "m-direct-1", "threadId": "t-direct-1", "attachments_count": len(attachments)}


class _StubRegistry:
    def __init__(self, connector: _StubGmailConnector) -> None:
        self.connector = connector

    def build(self, connector_id: str, settings: dict[str, object] | None = None) -> _StubGmailConnector:
        assert connector_id == "gmail"
        return self.connector


class GmailToolsReportFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        handle.write(b"%PDF-1.4\n%stub\n")
        handle.flush()
        handle.close()
        self.latest_pdf_path = Path(handle.name)
        self.context = ToolExecutionContext(
            user_id="u1",
            tenant_id="t1",
            conversation_id="c1",
            run_id="r1",
            mode="company_agent",
            settings={
                "__latest_report_title": "Website Analysis Report",
                "__latest_report_content": "Summary:\nAxon Group provides industrial solutions.",
                "__latest_report_pdf_path": str(self.latest_pdf_path),
            },
        )

    def tearDown(self) -> None:
        if self.latest_pdf_path.exists():
            self.latest_pdf_path.unlink()

    def test_gmail_draft_uses_latest_report_when_body_not_provided(self) -> None:
        connector = _StubGmailConnector()
        registry = _StubRegistry(connector)
        with patch("api.services.agent.tools.gmail_tools.get_connector_registry", return_value=registry):
            tool = GmailDraftTool()
            result = tool.execute(
                context=self.context,
                prompt="send the report to ssebowadisan1@gmail.com",
                params={"to": "ssebowadisan1@gmail.com"},
            )
        self.assertEqual(connector.last_draft.get("subject"), "Website Analysis Report")
        self.assertEqual(
            connector.last_draft.get("body"),
            "Summary:\nAxon Group provides industrial solutions.",
        )
        self.assertIn("Draft ID: d-1", result.content)

    def test_gmail_send_uses_latest_report_when_body_not_provided(self) -> None:
        connector = _StubGmailConnector()
        registry = _StubRegistry(connector)
        with patch("api.services.agent.tools.gmail_tools.get_connector_registry", return_value=registry):
            tool = GmailSendTool()
            result = tool.execute(
                context=self.context,
                prompt="send the report to ssebowadisan1@gmail.com",
                params={"to": "ssebowadisan1@gmail.com", "confirmed": True},
            )
        self.assertEqual(connector.last_send.get("subject"), "Website Analysis Report")
        self.assertEqual(
            connector.last_send.get("body"),
            "Summary:\nAxon Group provides industrial solutions.",
        )
        self.assertIn("Message ID: m-2", result.content)

    def test_gmail_draft_attaches_local_file_when_provided(self) -> None:
        connector = _StubGmailConnector()
        registry = _StubRegistry(connector)
        with patch("api.services.agent.tools.gmail_tools.get_connector_registry", return_value=registry):
            tool = GmailDraftTool()
            result = tool.execute(
                context=self.context,
                prompt="draft with attachment",
                params={
                    "to": "ssebowadisan1@gmail.com",
                    "attachments": [{"local_path": str(self.latest_pdf_path)}],
                },
            )
        self.assertEqual(len(connector.attachments), 1)
        self.assertEqual(connector.attachments[0]["draft_id"], "d-1")
        self.assertEqual(connector.attachments[0]["local_path"], str(self.latest_pdf_path))
        self.assertIn("Attachments: 1", result.content)
        self.assertEqual(result.data.get("attachments_count"), 1)

    def test_gmail_send_uses_draft_flow_when_attachments_present(self) -> None:
        connector = _StubGmailConnector()
        registry = _StubRegistry(connector)
        with patch("api.services.agent.tools.gmail_tools.get_connector_registry", return_value=registry):
            tool = GmailSendTool()
            result = tool.execute(
                context=self.context,
                prompt="send report with attachment",
                params={
                    "to": "ssebowadisan1@gmail.com",
                    "confirmed": True,
                    "attach_latest_report_pdf": True,
                },
            )
        self.assertFalse(connector.last_send)
        self.assertEqual(connector.last_send_draft.get("draft_id"), "d-1")
        self.assertEqual(len(connector.attachments), 1)
        self.assertEqual(connector.attachments[0]["local_path"], str(self.latest_pdf_path))
        self.assertEqual(result.data.get("attachments_count"), 1)
        self.assertEqual(result.data.get("id"), "m-draft-1")
        self.assertIn("Attachments: 1", result.content)

    def test_gmail_send_falls_back_to_direct_send_when_draft_scope_is_missing(self) -> None:
        class _ScopeBlockedConnector(_StubGmailConnector):
            def create_draft(self, *, to: str, subject: str, body: str, sender: str = "") -> dict[str, object]:
                raise RuntimeError("Request had insufficient authentication scopes.")

        connector = _ScopeBlockedConnector()
        registry = _StubRegistry(connector)
        with patch("api.services.agent.tools.gmail_tools.get_connector_registry", return_value=registry):
            tool = GmailSendTool()
            result = tool.execute(
                context=self.context,
                prompt="send report with attachment",
                params={
                    "to": "ssebowadisan1@gmail.com",
                    "confirmed": True,
                    "attach_latest_report_pdf": True,
                },
            )
        self.assertFalse(connector.last_send)
        self.assertFalse(connector.last_send_draft)
        self.assertEqual(result.data.get("id"), "m-direct-1")
        self.assertEqual(result.data.get("thread_id"), "t-direct-1")
        sent_payload = connector.last_send_with_attachments
        attachments = sent_payload.get("attachments")
        self.assertIsInstance(attachments, list)
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].get("local_path"), str(self.latest_pdf_path))
        self.assertIn("Attachments: 1", result.content)


if __name__ == "__main__":
    unittest.main()
