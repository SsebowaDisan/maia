from __future__ import annotations

from unittest.mock import patch
import unittest

from api.services.agent.tools.base import ToolExecutionContext
from api.services.agent.tools.gmail_tools import GmailDraftTool, GmailSendTool


class _ApiConnectorStub:
    def __init__(self) -> None:
        self.last_draft: dict[str, str] = {}
        self.last_send: dict[str, str] = {}

    def create_draft(self, *, to: str, subject: str, body: str, sender: str = "") -> dict[str, object]:
        self.last_draft = {"to": to, "subject": subject, "body": body, "sender": sender}
        return {"draft": {"id": "d-1", "message": {"id": "m-1"}}}

    def send_message(self, *, to: str, subject: str, body: str, sender: str = "") -> dict[str, str]:
        self.last_send = {"to": to, "subject": subject, "body": body, "sender": sender}
        return {"id": "m-2", "threadId": "t-2"}


class _RegistryStub:
    def __init__(self) -> None:
        self.api = _ApiConnectorStub()
        self.built: list[str] = []

    def build(self, connector_id: str, settings: dict | None = None) -> _ApiConnectorStub:
        del settings
        self.built.append(connector_id)
        if connector_id != "gmail":
            raise AssertionError(f"Unexpected connector requested: {connector_id}")
        return self.api


class GmailToolsApiOnlyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = ToolExecutionContext(
            user_id="u1",
            tenant_id="t1",
            conversation_id="c1",
            run_id="r1",
            mode="company_agent",
            settings={
                "__latest_report_title": "Website Analysis Report",
                "__latest_report_content": "Summary: Axon Group industrial solutions.",
                "agent.gmail.desktop_live": True,
            },
        )

    def test_gmail_draft_uses_api_even_when_live_desktop_requested(self) -> None:
        registry = _RegistryStub()
        with patch("api.services.agent.tools.gmail_tools.get_connector_registry", return_value=registry):
            tool = GmailDraftTool()
            result = tool.execute(
                context=self.context,
                prompt="send report to ssebowadisan1@gmail.com",
                params={"to": "ssebowadisan1@gmail.com", "live_desktop": True},
            )
        self.assertEqual(registry.built, ["gmail"])
        self.assertEqual(result.data.get("delivery_mode"), "gmail_api")
        self.assertIn("gmail draft created", result.summary.lower())
        self.assertNotIn("live desktop", result.summary.lower())

    def test_gmail_send_uses_api_even_when_live_desktop_requested(self) -> None:
        registry = _RegistryStub()
        with patch("api.services.agent.tools.gmail_tools.get_connector_registry", return_value=registry):
            tool = GmailSendTool()
            result = tool.execute(
                context=self.context,
                prompt="send report to ssebowadisan1@gmail.com",
                params={"to": "ssebowadisan1@gmail.com", "confirmed": True, "live_desktop": True},
            )
        self.assertEqual(registry.built, ["gmail"])
        self.assertEqual(result.data.get("delivery_mode"), "gmail_api")
        self.assertIn("gmail message sent", result.summary.lower())
        self.assertNotIn("live desktop", result.summary.lower())


if __name__ == "__main__":
    unittest.main()
