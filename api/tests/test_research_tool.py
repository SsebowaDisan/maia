from __future__ import annotations

from unittest.mock import patch
import unittest

from api.services.agent.tools.base import ToolExecutionContext
from api.services.agent.tools.research_tools import WebResearchTool


class _BraveConnectorStub:
    def __init__(self) -> None:
        self.counts: list[int] = []

    def web_search(self, *, query: str, count: int = 8) -> dict[str, object]:
        self.counts.append(int(count))
        return {
            "results": [
                {
                    "title": "Axon Group - Industrial solutions",
                    "description": f"Overview for {query}",
                    "url": "https://axongroup.com/",
                }
            ]
        }


class _BraveMixedConnectorStub:
    def web_search(self, *, query: str, count: int = 8) -> dict[str, object]:
        del count
        return {
            "results": [
                {
                    "title": "Axon Group - Industrial solutions",
                    "description": f"Overview for {query}",
                    "url": "https://axongroup.com/",
                },
                {
                    "title": "AXON stock quote",
                    "description": "NASDAQ:AXON coverage",
                    "url": "https://www.cnn.com/markets/stocks/AXON",
                },
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

    def names(self) -> list[str]:
        # Supplemental connectors disabled in test stubs
        return ["brave_search", "bing_search"]

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

    def test_search_budget_caps_total_requested_result_slots(self) -> None:
        brave = _BraveConnectorStub()
        registry = _RegistryStub(brave=brave, bing=_BingConnectorStub())
        with patch("api.services.agent.tools.research_tools.get_connector_registry", return_value=registry):
            result = WebResearchTool().execute(
                context=self.context,
                prompt="research axon group",
                params={
                    "query": "axon group",
                    "max_query_variants": 20,
                    "results_per_query": 25,
                    "search_budget": 60,
                    "query_variants": [
                        "axon group market overview",
                        "axon group products",
                        "axon group competitors",
                        "axon group news",
                        "axon group pricing",
                        "axon group strategy",
                    ],
                },
            )
        self.assertLessEqual(sum(brave.counts), 60)
        self.assertEqual(int(result.data.get("search_budget_requested") or 0), 60)
        self.assertLessEqual(int(result.data.get("search_budget_effective") or 0), 60)

    def test_brave_emits_live_browser_navigation_scroll_and_click_events(self) -> None:
        registry = _RegistryStub(brave=_BraveConnectorStub(), bing=_BingConnectorStub())
        with patch("api.services.agent.tools.research_tools.get_connector_registry", return_value=registry):
            result = WebResearchTool().execute(
                context=self.context,
                prompt="research axon group",
                params={
                    "query": "axon group",
                    "query_variants": ["axon group"],
                    "max_query_variants": 2,
                    "results_per_query": 8,
                },
            )

        event_types = [event.event_type for event in result.events]
        self.assertIn("browser_navigate", event_types)
        self.assertIn("browser_scroll", event_types)
        self.assertIn("browser_hover", event_types)
        self.assertIn("browser_click", event_types)
        self.assertIn("web_result_opened", event_types)

        search_navigate_events = [
            event
            for event in result.events
            if event.event_type == "browser_navigate"
            and str(event.data.get("url") or "").startswith("https://search.brave.com/search?")
        ]
        self.assertTrue(search_navigate_events)

        opened_source_events = [
            event
            for event in result.events
            if event.event_type == "web_result_opened"
            and str(event.data.get("url") or "").startswith("https://axongroup.com/")
        ]
        self.assertTrue(opened_source_events)

        cursor_events = [
            event
            for event in result.events
            if event.event_type
            in {
                "browser_navigate",
                "browser_hover",
                "browser_scroll",
                "browser_click",
                "web_result_opened",
            }
        ]
        self.assertTrue(cursor_events)
        for event in cursor_events:
            self.assertIn("scene_surface", event.data)
            self.assertEqual(str(event.data.get("scene_surface")), "website")
            self.assertIsInstance(event.data.get("cursor_x"), float)
            self.assertIsInstance(event.data.get("cursor_y"), float)
            self.assertGreaterEqual(float(event.data.get("cursor_x") or 0.0), 0.0)
            self.assertGreaterEqual(float(event.data.get("cursor_y") or 0.0), 0.0)

    def test_strict_domain_scope_filters_off_domain_sources(self) -> None:
        registry = _RegistryStub(brave=_BraveMixedConnectorStub(), bing=_BingConnectorStub())
        with patch("api.services.agent.tools.research_tools.get_connector_registry", return_value=registry):
            result = WebResearchTool().execute(
                context=self.context,
                prompt="analyze axongroup",
                params={
                    "query": "axon group overview",
                    "domain_scope": ["axongroup.com"],
                    "domain_scope_mode": "strict",
                    "target_url": "https://axongroup.com/",
                    "query_variants": ["axon group overview"],
                    "max_query_variants": 2,
                    "results_per_query": 8,
                },
            )

        urls = [
            str(item.get("url") or "")
            for item in (result.data.get("items") or [])
            if isinstance(item, dict)
        ]
        self.assertTrue(urls)
        self.assertTrue(all("axongroup.com" in url for url in urls))
        self.assertGreater(int(result.data.get("domain_scope_filtered_out") or 0), 0)


if __name__ == "__main__":
    unittest.main()
