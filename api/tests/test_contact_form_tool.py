from __future__ import annotations

import unittest
from unittest.mock import patch

from api.services.agent.tools.base import ToolExecutionContext
from api.services.agent.tools.contact_form_tools import BrowserContactFormSendTool


class _ContactConnectorStub:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def submit_contact_form_live_stream(
        self,
        *,
        url: str,
        sender_name: str,
        sender_email: str,
        sender_company: str = "",
        sender_phone: str = "",
        subject: str,
        message: str,
        auto_accept_cookies: bool = True,
        timeout_ms: int = 25000,
        wait_ms: int = 1200,
    ):
        self.calls.append(
            {
                "url": url,
                "sender_name": sender_name,
                "sender_email": sender_email,
                "sender_company": sender_company,
                "sender_phone": sender_phone,
                "subject": subject,
                "message": message,
                "auto_accept_cookies": auto_accept_cookies,
                "timeout_ms": timeout_ms,
                "wait_ms": wait_ms,
            }
        )
        yield {
            "event_type": "browser_open",
            "title": "Open target website for outreach",
            "detail": url,
            "data": {"url": url, "cursor_x": 20, "cursor_y": 18},
            "snapshot_ref": ".maia_agent/browser_captures/test-open.png",
        }
        yield {
            "event_type": "browser_contact_submit",
            "title": "Submit contact form",
            "detail": "Submitted website contact form",
            "data": {"url": url, "cursor_x": 62, "cursor_y": 74},
            "snapshot_ref": ".maia_agent/browser_captures/test-submit.png",
        }
        return {
            "submitted": True,
            "status": "submitted",
            "confirmation_text": "Thank you, we will get in touch.",
            "url": url,
            "title": "Contact",
            "fields_filled": ["name", "email", "company", "phone", "subject", "message"],
        }


class _RegistryStub:
    def __init__(self, connector: _ContactConnectorStub) -> None:
        self._connector = connector

    def build(self, connector_id: str, settings: dict | None = None):
        assert connector_id == "playwright_contact_form"
        assert isinstance(settings, dict)
        return self._connector


class ContactFormToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = ToolExecutionContext(
            user_id="u1",
            tenant_id="t1",
            conversation_id="c1",
            run_id="r1",
            mode="company_agent",
            settings={
                "agent.contact_sender_name": "Maia Outreach",
                "agent.contact_sender_email": "disan@micrurus.com",
            },
        )

    def test_contact_form_tool_streams_live_events_and_returns_submission(self) -> None:
        connector = _ContactConnectorStub()
        registry = _RegistryStub(connector)
        with patch(
            "api.services.agent.tools.contact_form_tools.get_connector_registry",
            return_value=registry,
        ), patch(
            "api.services.agent.tools.contact_form_tools.polish_contact_form_content",
            return_value={
                "subject": "Polished subject",
                "message_text": "Polished message body",
            },
        ):
            tool = BrowserContactFormSendTool()
            result = tool.execute(
                context=self.context,
                prompt="Open https://example.com/contact and submit the contact form.",
                params={"confirmed": True},
            )

        assert result.data.get("submitted") is True
        assert result.data.get("status") == "submitted"
        assert any(event.event_type == "browser_contact_submit" for event in result.events)
        assert connector.calls, "expected connector to be invoked"
        call = connector.calls[0]
        assert call["url"] == "https://example.com/contact"
        assert call["subject"] == "Polished subject"
        assert call["message"] == "Polished message body"
        assert call["sender_phone"] == "+1 415 555 0199"
        latest_submission = self.context.settings.get("__latest_contact_form_submission")
        assert isinstance(latest_submission, dict)
        assert latest_submission.get("status") == "submitted"
        assert latest_submission.get("sender_phone") == "+1 415 555 0199"

    def test_contact_form_tool_uses_explicit_phone_and_company(self) -> None:
        connector = _ContactConnectorStub()
        registry = _RegistryStub(connector)
        with patch(
            "api.services.agent.tools.contact_form_tools.get_connector_registry",
            return_value=registry,
        ), patch(
            "api.services.agent.tools.contact_form_tools.polish_contact_form_content",
            return_value={
                "subject": "Polished subject",
                "message_text": "Polished message body",
            },
        ):
            tool = BrowserContactFormSendTool()
            _ = tool.execute(
                context=self.context,
                prompt="Open https://example.com/contact and submit the contact form.",
                params={
                    "confirmed": True,
                    "sender_company": "Micrurus",
                    "sender_phone": "+1 617 555 0101",
                },
            )

        assert connector.calls, "expected connector to be invoked"
        call = connector.calls[0]
        assert call["sender_company"] == "Micrurus"
        assert call["sender_phone"] == "+1 617 555 0101"


if __name__ == "__main__":
    unittest.main()
