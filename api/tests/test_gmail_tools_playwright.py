from __future__ import annotations

from unittest.mock import patch
import unittest

from api.services.agent.tools.base import ToolExecutionContext
from api.services.agent.tools.gmail_tools import GmailDraftTool, GmailSendTool


class _DesktopConnectorStub:
    def compose_live_stream(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        send: bool,
        timeout_ms: int = 30000,
        wait_ms: int = 1200,
    ):
        del timeout_ms, wait_ms
        yield {
            "event_type": "web_search_started",
            "title": "Open search engine and search Gmail",
            "detail": "Search query: gmail",
            "data": {"query": "gmail"},
            "snapshot_ref": ".maia_agent/browser_captures/test-search.png",
        }
        yield {
            "event_type": "email_open_compose",
            "title": "Open Gmail compose window",
            "detail": "Composer is ready",
            "data": {"to": to, "subject": subject},
            "snapshot_ref": ".maia_agent/browser_captures/test-compose.png",
        }
        if send:
            yield {
                "event_type": "email_click_send",
                "title": "Click Gmail Send",
                "detail": to,
                "data": {"to": to},
                "snapshot_ref": ".maia_agent/browser_captures/test-send.png",
            }
            return {"status": "sent", "url": "https://mail.google.com/mail/u/0/#inbox"}
        return {"status": "draft_saved", "url": "https://mail.google.com/mail/u/0/#drafts"}


class _ApiConnectorShouldNotBeCalled:
    def create_draft(self, **kwargs):
        raise AssertionError(f"Gmail API fallback should not be called: {kwargs}")

    def send_message(self, **kwargs):
        raise AssertionError(f"Gmail API fallback should not be called: {kwargs}")


class _RegistryStub:
    def __init__(self) -> None:
        self.desktop = _DesktopConnectorStub()
        self.gmail_api = _ApiConnectorShouldNotBeCalled()

    def build(self, connector_id: str, settings: dict | None = None):
        del settings
        if connector_id == "gmail_playwright":
            return self.desktop
        if connector_id == "gmail":
            return self.gmail_api
        raise AssertionError(f"Unexpected connector requested: {connector_id}")


class GmailToolsPlaywrightTests(unittest.TestCase):
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

    def test_gmail_draft_prefers_live_desktop_connector(self) -> None:
        registry = _RegistryStub()
        with patch(
            "api.services.agent.tools.gmail_live_desktop.get_connector_registry",
            return_value=registry,
        ), patch("api.services.agent.tools.gmail_tools.get_connector_registry", return_value=registry):
            tool = GmailDraftTool()
            result = tool.execute(
                context=self.context,
                prompt="send report to ssebowadisan1@gmail.com",
                params={"to": "ssebowadisan1@gmail.com"},
            )
        self.assertIn("live desktop session", result.summary.lower())
        self.assertEqual(result.data.get("delivery_mode"), "playwright_desktop")
        self.assertTrue(any(event.snapshot_ref for event in result.events))

    def test_gmail_send_prefers_live_desktop_connector(self) -> None:
        registry = _RegistryStub()
        with patch(
            "api.services.agent.tools.gmail_live_desktop.get_connector_registry",
            return_value=registry,
        ), patch("api.services.agent.tools.gmail_tools.get_connector_registry", return_value=registry):
            tool = GmailSendTool()
            result = tool.execute(
                context=self.context,
                prompt="send report to ssebowadisan1@gmail.com",
                params={"to": "ssebowadisan1@gmail.com", "confirmed": True},
            )
        self.assertIn("live desktop session", result.summary.lower())
        self.assertEqual(result.data.get("delivery_mode"), "playwright_desktop")
        self.assertTrue(any(event.event_type == "email_click_send" for event in result.events))


if __name__ == "__main__":
    unittest.main()
