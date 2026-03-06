from __future__ import annotations

from unittest.mock import patch
import unittest

from api.services.agent.tools.base import ToolExecutionContext
from api.services.agent.tools.browser_tools import PlaywrightInspectTool


class _BrowserConnectorStub:
    def browse_live_stream(self, **kwargs):
        interaction_actions = kwargs.get("interaction_actions")
        yield {
            "event_type": "browser_open",
            "title": "Open browser",
            "detail": "ok",
            "data": {"url": "https://example.com", "interaction_actions": interaction_actions},
            "snapshot_ref": "",
        }
        return {
            "url": "https://example.com",
            "title": "Example",
            "text_excerpt": "Example page content",
            "screenshot_path": "",
            "pages": [],
            "render_quality": "high",
            "content_density": 0.6,
            "blocked_signal": False,
            "blocked_reason": "",
            "stages": {"initial_render": True},
        }


class _AlwaysBlockedConnectorStub:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def browse_live_stream(self, **kwargs):
        url = str(kwargs.get("url") or "")
        self.urls.append(url)
        yield {
            "event_type": "browser_open",
            "title": "Open browser",
            "detail": url,
            "data": {"url": url},
            "snapshot_ref": "",
        }
        return {
            "url": url,
            "title": "Security check",
            "text_excerpt": "Performing security verification. Verify you are human.",
            "screenshot_path": "",
            "cursor_x": 44.0,
            "cursor_y": 26.0,
            "pages": [],
            "render_quality": "blocked",
            "content_density": 0.0,
            "blocked_signal": True,
            "blocked_reason": "bot_challenge",
            "stages": {"initial_render": True},
        }


class _BlockedThenRecoveredConnectorStub:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def browse_live_stream(self, **kwargs):
        url = str(kwargs.get("url") or "")
        self.urls.append(url)
        yield {
            "event_type": "browser_open",
            "title": "Open browser",
            "detail": url,
            "data": {"url": url},
            "snapshot_ref": "",
        }
        if url.rstrip("/") == "https://example.com/path":
            return {
                "url": url,
                "title": "Security check",
                "text_excerpt": "Verify you are human.",
                "screenshot_path": "",
                "pages": [],
                "render_quality": "blocked",
                "content_density": 0.0,
                "blocked_signal": True,
                "blocked_reason": "bot_challenge",
                "stages": {"initial_render": True},
            }
        return {
            "url": url,
            "title": "Example home",
            "text_excerpt": "Welcome to Example. Services and contact details.",
            "screenshot_path": "",
            "pages": [],
            "render_quality": "high",
            "content_density": 0.7,
            "blocked_signal": False,
            "blocked_reason": "",
            "stages": {"initial_render": True},
        }


class _RegistryStub:
    def build(self, connector_id: str, settings=None):
        del settings
        if connector_id != "playwright_browser":
            raise AssertionError(f"unexpected connector {connector_id}")
        return _BrowserConnectorStub()


class BrowserToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = ToolExecutionContext(
            user_id="u1",
            tenant_id="t1",
            conversation_id="c1",
            run_id="r1",
            mode="company_agent",
            settings={},
        )

    def test_browser_tool_passes_interaction_actions(self) -> None:
        with patch("api.services.agent.tools.browser_tools.get_connector_registry", return_value=_RegistryStub()):
            result = PlaywrightInspectTool().execute(
                context=self.context,
                prompt="inspect https://example.com",
                params={
                    "url": "https://example.com",
                    "interaction_actions": [{"type": "click", "selector": "a[href='/about']"}],
                },
            )
        assert result.data.get("interaction_actions")
        event_types = [event.event_type for event in result.events]
        assert "tool_progress" in event_types
        assert "browser_interaction_policy" in event_types
        assert "browser_open" in event_types
        browser_open_event = next(event for event in result.events if event.event_type == "browser_open")
        assert browser_open_event.data.get("action") == "navigate"
        assert browser_open_event.data.get("action_phase") == "active"
        assert browser_open_event.data.get("action_status") == "ok"

    def test_browser_tool_emits_human_verification_event_when_blocked(self) -> None:
        blocked_connector = _AlwaysBlockedConnectorStub()

        class _BlockedRegistry:
            def build(self, connector_id: str, settings=None):
                del settings
                if connector_id != "playwright_browser":
                    raise AssertionError(f"unexpected connector {connector_id}")
                return blocked_connector

        with patch("api.services.agent.tools.browser_tools.get_connector_registry", return_value=_BlockedRegistry()):
            result = PlaywrightInspectTool().execute(
                context=self.context,
                prompt="inspect https://example.com/path",
                params={
                    "url": "https://example.com/path",
                    "blocked_retry_attempts": 1,
                    "blocked_root_retry_attempts": 1,
                    "human_handoff_on_blocked": True,
                },
            )
        event_types = [event.event_type for event in result.events]
        assert "browser_human_verification_required" in event_types
        assert bool(result.data.get("human_handoff_required")) is True
        assert bool(self.context.settings.get("__barrier_handoff_required")) is True
        assert blocked_connector.urls
        assert "https://example.com/" in blocked_connector.urls
        handoff_event = next(event for event in result.events if event.event_type == "browser_human_verification_required")
        assert handoff_event.data.get("cursor_x") == 44.0
        assert handoff_event.data.get("cursor_y") == 26.0

    def test_browser_tool_recovers_on_root_retry_without_handoff(self) -> None:
        recovery_connector = _BlockedThenRecoveredConnectorStub()

        class _RecoveryRegistry:
            def build(self, connector_id: str, settings=None):
                del settings
                if connector_id != "playwright_browser":
                    raise AssertionError(f"unexpected connector {connector_id}")
                return recovery_connector

        with patch("api.services.agent.tools.browser_tools.get_connector_registry", return_value=_RecoveryRegistry()):
            result = PlaywrightInspectTool().execute(
                context=self.context,
                prompt="inspect https://example.com/path",
                params={
                    "url": "https://example.com/path",
                    "blocked_retry_attempts": 0,
                    "blocked_root_retry_attempts": 1,
                    "human_handoff_on_blocked": True,
                },
            )
        event_types = [event.event_type for event in result.events]
        assert "browser_human_verification_required" not in event_types
        assert bool(result.data.get("human_handoff_required")) is False
        assert bool(result.data.get("blocked_root_retry_improved")) is True

    def test_browser_tool_uses_trusted_site_mode_instead_of_handoff(self) -> None:
        blocked_connector = _AlwaysBlockedConnectorStub()

        class _BlockedRegistry:
            def build(self, connector_id: str, settings=None):
                del settings
                if connector_id != "playwright_browser":
                    raise AssertionError(f"unexpected connector {connector_id}")
                return blocked_connector

        self.context.settings["browser.trusted_site_domains"] = ["example.com"]
        with patch("api.services.agent.tools.browser_tools.get_connector_registry", return_value=_BlockedRegistry()):
            result = PlaywrightInspectTool().execute(
                context=self.context,
                prompt="inspect https://example.com/path",
                params={
                    "url": "https://example.com/path",
                    "blocked_retry_attempts": 0,
                    "blocked_root_retry_attempts": 0,
                    "human_handoff_on_blocked": True,
                },
            )
        event_types = [event.event_type for event in result.events]
        assert "browser_human_verification_required" not in event_types
        assert bool(result.data.get("trusted_site_mode")) is True
        assert bool(result.data.get("human_handoff_required")) is False
        assert "Trusted-site mode is enabled" in str(result.data.get("human_handoff_note") or "")


if __name__ == "__main__":
    unittest.main()
