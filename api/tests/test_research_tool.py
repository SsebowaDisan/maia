from __future__ import annotations

from unittest.mock import patch
import unittest

from api.services.agent.tools.base import ToolExecutionContext
from api.services.agent.tools.research_tools import WebResearchTool


class _BraveConnectorStub:
    def web_search(self, *, query: str, count: int = 8) -> dict[str, object]:
        del count
        return {
            "results": [
                {
                    "title": "Axon Group - Industrial solutions",
                    "description": f"Overview for {query}",
                    "url": "https://axongroup.com/",
                }
            ]
        }


class _BingConnectorStub:
    def search_web(self, *, query: str, count: int = 8) -> dict[str, object]:
        del count
        return {
            "webPages": {
                "value": [
                    {
                        "name": "Axon Group",
                        "snippet": f"Bing snippet for {query}",
                        "url": "https://axongroup.com/about-axon",
                    }
                ]
            }
        }


class _FailingConnector:
    def web_search(self, **kwargs):
        raise RuntimeError(f"connector unavailable {kwargs}")

    def search_web(self, **kwargs):
        raise RuntimeError(f"connector unavailable {kwargs}")


class _RegistryStub:
    def __init__(self, *, brave: object, bing: object) -> None:
        self._brave = brave
        self._bing = bing

    def build(self, connector_id: str, settings: dict | None = None):
        del settings
        if connector_id == "brave_search":
            return self._brave
        if connector_id == "bing_search":
            return self._bing
        raise AssertionError(f"Unexpected connector requested: {connector_id}")


class ResearchToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = ToolExecutionContext(
            user_id="u1",
            tenant_id="t1",
            conversation_id="c1",
            run_id="r1",
            mode="company_agent",
            settings={},
        )

    def test_brave_is_primary_provider(self) -> None:
        registry = _RegistryStub(brave=_BraveConnectorStub(), bing=_BingConnectorStub())
        with patch("api.services.agent.tools.research_tools.get_connector_registry", return_value=registry):
            result = WebResearchTool().execute(
                context=self.context,
                prompt="research axon group",
                params={"query": "axon group"},
            )
        self.assertEqual(result.data.get("provider"), "brave_search")
        self.assertNotIn("duckduckgo.com/?q=", result.content.lower())

    def test_no_duckduckgo_manual_fallback_when_providers_missing(self) -> None:
        registry = _RegistryStub(brave=_FailingConnector(), bing=_FailingConnector())
        with patch("api.services.agent.tools.research_tools.get_connector_registry", return_value=registry):
            result = WebResearchTool().execute(
                context=self.context,
                prompt="research axon group",
                params={"query": "axon group"},
            )
        self.assertIn("No web search data available", result.content)
        self.assertNotIn("duckduckgo.com/?q=", result.content.lower())
        provider_failures = result.data.get("provider_failures") or []
        self.assertTrue(provider_failures)
        self.assertEqual(provider_failures[-1].get("reason"), "provider_unavailable")

    def test_brave_failure_can_fallback_to_bing_when_enabled(self) -> None:
        registry = _RegistryStub(brave=_FailingConnector(), bing=_BingConnectorStub())
        with patch("api.services.agent.tools.research_tools.get_connector_registry", return_value=registry):
            result = WebResearchTool().execute(
                context=self.context,
                prompt="research axon group",
                params={
                    "query": "axon group",
                    "provider": "brave_search",
                    "allow_provider_fallback": True,
                },
            )
        self.assertEqual(result.data.get("provider"), "bing_search")
        failures = result.data.get("provider_failures") or []
        self.assertGreaterEqual(len(failures), 1)
        self.assertEqual(failures[0].get("provider"), "brave_search")
        self.assertEqual(failures[0].get("reason"), "provider_unavailable")

    def test_brave_failure_hard_fails_when_fallback_disabled(self) -> None:
        registry = _RegistryStub(brave=_FailingConnector(), bing=_BingConnectorStub())
        with patch("api.services.agent.tools.research_tools.get_connector_registry", return_value=registry):
            result = WebResearchTool().execute(
                context=self.context,
                prompt="research axon group",
                params={
                    "query": "axon group",
                    "provider": "brave_search",
                    "allow_provider_fallback": False,
                },
            )
        self.assertIn("No web search data available", result.content)
        self.assertEqual(result.data.get("provider"), "brave_search")
        attempts = result.data.get("provider_attempted") or []
        self.assertEqual(attempts, ["brave_search"])


if __name__ == "__main__":
    unittest.main()
