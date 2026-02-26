from __future__ import annotations

from unittest.mock import patch
import unittest

from api.services.agent.tools.base import ToolExecutionContext
from api.services.agent.tools.gmail_tools import GmailDraftTool, GmailSendTool


class _StubGmailConnector:
    def __init__(self) -> None:
        self.last_draft: dict[str, str] = {}
        self.last_send: dict[str, str] = {}

    def create_draft(self, *, to: str, subject: str, body: str, sender: str = "") -> dict[str, object]:
        self.last_draft = {"to": to, "subject": subject, "body": body, "sender": sender}
        return {"draft": {"id": "d-1", "message": {"id": "m-1"}}}

    def send_message(self, *, to: str, subject: str, body: str, sender: str = "") -> dict[str, str]:
        self.last_send = {"to": to, "subject": subject, "body": body, "sender": sender}
        return {"id": "m-2", "threadId": "t-2"}


class _StubRegistry:
    def __init__(self, connector: _StubGmailConnector) -> None:
        self.connector = connector

    def build(self, connector_id: str, settings: dict[str, object] | None = None) -> _StubGmailConnector:
        assert connector_id == "gmail"
        return self.connector


class GmailToolsReportFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = ToolExecutionContext(
            user_id="u1",
            tenant_id="t1",
            conversation_id="c1",
            run_id="r1",
            mode="company_agent",
            settings={
                "__latest_report_title": "Website Analysis Report",
                "__latest_report_content": "Summary:\nAxon Group provides industrial solutions.",
            },
        )

    def test_gmail_draft_uses_latest_report_when_body_not_provided(self) -> None:
        connector = _StubGmailConnector()
        registry = _StubRegistry(connector)
        with patch("api.services.agent.tools.gmail_tools.get_connector_registry", return_value=registry):
            tool = GmailDraftTool()
            result = tool.execute(
                context=self.context,
                prompt="send the report to ssebowadisan1@gmail.com",
                params={"to": "ssebowadisan1@gmail.com", "live_desktop": False},
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
                params={"to": "ssebowadisan1@gmail.com", "confirmed": True, "live_desktop": False},
            )
        self.assertEqual(connector.last_send.get("subject"), "Website Analysis Report")
        self.assertEqual(
            connector.last_send.get("body"),
            "Summary:\nAxon Group provides industrial solutions.",
        )
        self.assertIn("Message ID: m-2", result.content)


if __name__ == "__main__":
    unittest.main()
