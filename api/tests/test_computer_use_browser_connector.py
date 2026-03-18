from __future__ import annotations

import base64
from unittest.mock import patch
import unittest

from api.services.agent.connectors.computer_use_browser_connector import ComputerUseBrowserConnector


def _screenshot_b64() -> str:
    return base64.b64encode(b"stub-png").decode("ascii")


class _SessionStub:
    def __init__(self, session_id: str, start_url: str) -> None:
        self.session_id = session_id
        self._url = start_url

    def navigate(self, url: str) -> str:
        self._url = url
        return "ok"

    def screenshot_b64(self) -> str:
        return _screenshot_b64()

    def page_title(self) -> str:
        return "Example"

    def current_url(self) -> str:
        return self._url


class _RegistryStub:
    def __init__(self) -> None:
        self.created: list[str] = []
        self.closed: list[str] = []
        self._sessions: dict[str, _SessionStub] = {}

    def create(self, *, user_id: str, start_url: str):
        session_id = f"s-{len(self.created) + 1}"
        self.created.append(session_id)
        session = _SessionStub(session_id=session_id, start_url=start_url)
        self._sessions[session_id] = session
        return session

    def close(self, session_id: str) -> bool:
        self.closed.append(session_id)
        self._sessions.pop(session_id, None)
        return True


class ComputerUseBrowserConnectorTests(unittest.TestCase):
    def test_exposes_legacy_compat_methods(self) -> None:
        connector = ComputerUseBrowserConnector(settings={})
        assert hasattr(connector, "browse_and_capture")
        assert hasattr(connector, "browse_live_stream")
        assert hasattr(connector, "submit_contact_form_live_stream")

    def test_browse_and_capture_uses_compatible_stream_contract(self) -> None:
        registry = _RegistryStub()

        def _run_agent_loop(session, task, **kwargs):
            _ = task, kwargs
            yield {"event_type": "screenshot", "iteration": 1, "screenshot_b64": _screenshot_b64(), "url": session.current_url()}
            yield {
                "event_type": "action",
                "iteration": 1,
                "action": "left_click",
                "input": {"coordinate": [640, 400]},
            }
            yield {"event_type": "text", "iteration": 1, "text": "Example company profile details."}
            yield {"event_type": "done", "iteration": 1, "url": session.current_url()}

        connector = ComputerUseBrowserConnector(settings={"__agent_user_id": "u-1"})
        with patch(
            "api.services.computer_use.session_registry.get_session_registry",
            return_value=registry,
        ), patch(
            "api.services.computer_use.agent_loop.run_agent_loop",
            side_effect=_run_agent_loop,
        ):
            capture = connector.browse_and_capture(url="https://example.com")

        assert capture["url"] == "https://example.com"
        assert "Example company profile details." in str(capture.get("text_excerpt") or "")
        assert capture.get("render_quality") in {"low", "medium", "high", "blocked"}
        assert "s-1" in registry.closed

    def test_submit_contact_form_stream_returns_expected_payload_keys(self) -> None:
        registry = _RegistryStub()

        def _run_agent_loop(session, task, **kwargs):
            _ = task, kwargs
            yield {"event_type": "screenshot", "iteration": 1, "screenshot_b64": _screenshot_b64(), "url": session.current_url()}
            yield {"event_type": "action", "iteration": 1, "action": "type"}
            yield {"event_type": "action", "iteration": 1, "action": "left_click"}
            yield {"event_type": "text", "iteration": 1, "text": "Thank you, your message has been sent."}
            yield {"event_type": "done", "iteration": 1, "url": session.current_url()}

        connector = ComputerUseBrowserConnector(settings={"__agent_user_id": "u-1"})
        with patch(
            "api.services.computer_use.session_registry.get_session_registry",
            return_value=registry,
        ), patch(
            "api.services.computer_use.agent_loop.run_agent_loop",
            side_effect=_run_agent_loop,
        ):
            stream = connector.submit_contact_form_live_stream(
                url="https://example.com/contact",
                sender_name="Micrurus Team",
                sender_email="team@example.com",
                sender_company="Micrurus",
                sender_phone="+14155550199",
                subject="Intro",
                message="Hello from Micrurus",
            )
            while True:
                try:
                    _ = next(stream)
                except StopIteration as stop:
                    result = stop.value
                    break

        assert bool(result.get("submitted")) is True
        assert result.get("status") == "submitted"
        assert "confirmation_text" in result
        assert isinstance(result.get("fields_filled"), list)
        assert "s-1" in registry.closed


if __name__ == "__main__":
    unittest.main()
