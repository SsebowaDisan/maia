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


if __name__ == "__main__":
    unittest.main()
