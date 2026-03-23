from __future__ import annotations

from unittest.mock import patch
import unittest

from api.services.agent.tools.base import ToolExecutionContext, ToolExecutionError
from api.services.agent.tools.web_extract_tools import WebStructuredExtractTool


class _BrowserConnectorStub:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def browse_and_capture(self, **kwargs):
        url = str(kwargs.get("url") or "")
        self.calls.append(url)
        if "empty" in url:
            return {
                "url": url,
                "title": "Blocked",
                "text_excerpt": "",
                "render_quality": "low",
                "content_density": 0.05,
                "blocked_signal": True,
            }
        return {
            "url": url or "https://example.com/about",
            "title": "Example About",
            "text_excerpt": "Example Corp is based in Berlin. Revenue in 2025 was 12.5M.",
            "render_quality": "high",
            "content_density": 0.71,
            "blocked_signal": False,
        }


class _RegistryStub:
    def __init__(self) -> None:
        self.connector = _BrowserConnectorStub()

    def build(self, connector_id: str, settings=None):
        del settings
        if connector_id != "computer_use_browser":
            raise AssertionError(f"unexpected connector {connector_id}")
        return self.connector


class WebStructuredExtractToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = ToolExecutionContext(
            user_id="u1",
            tenant_id="t1",
            conversation_id="c1",
            run_id="r1",
            mode="company_agent",
            settings={},
        )

    def test_extracts_structured_values_from_page_text(self) -> None:
        with patch(
            "api.services.agent.tools.web_extract_tools.call_json_response",
            return_value={
                "values": {"company_name": "Example Corp", "hq_city": "Berlin", "revenue_m": 12.5},
                "confidence": 0.88,
                "evidence": [{"field": "hq_city", "quote": "based in Berlin", "confidence": 0.9}],
                "gaps": [],
            },
        ):
            result = WebStructuredExtractTool().execute(
                context=self.context,
                prompt="extract company profile",
                params={
                    "page_text": "Example Corp is based in Berlin. Revenue in 2025 was 12.5M.",
                    "field_schema": {
                        "company_name": "string",
                        "hq_city": "string",
                        "revenue_m": "number",
                    },
                },
            )
        assert result.data["values"]["company_name"] == "Example Corp"
        assert result.data["values"]["hq_city"] == "Berlin"
        assert result.data["values"]["revenue_m"] == 12.5
        assert float(result.data.get("schema_coverage") or 0.0) >= 0.9
        assert float(result.data.get("quality_score") or 0.0) > 0.0
        assert str(result.data.get("quality_band") or "") in {"medium", "high"}
        assert bool(str(result.data.get("extraction_fingerprint") or "").strip())
        event_types = [event.event_type for event in result.events]
        assert "prepare_request" in event_types
        assert "api_call_started" in event_types
        assert "api_call_completed" in event_types
        assert "normalize_response" in event_types

    def test_uses_browser_capture_when_url_only(self) -> None:
        registry = _RegistryStub()
        with patch(
            "api.services.agent.tools.web_extract_tools.get_connector_registry",
            return_value=registry,
        ), patch(
            "api.services.agent.tools.web_extract_tools.call_json_response",
            return_value={
                "values": {"company_name": "Example Corp"},
                "confidence": 0.7,
                "evidence": [{"field": "company_name", "quote": "Example Corp"}],
                "gaps": [],
            },
        ):
            result = WebStructuredExtractTool().execute(
                context=self.context,
                prompt="extract",
                params={"url": "https://example.com/about", "field_schema": {"company_name": "string"}},
            )
        assert result.data["url"] == "https://example.com/about"
        assert result.data["values"]["company_name"] == "Example Corp"
        assert registry.connector.calls == ["https://example.com/about"]

    def test_uses_candidate_urls_when_primary_extract_url_missing(self) -> None:
        registry = _RegistryStub()
        with patch(
            "api.services.agent.tools.web_extract_tools.get_connector_registry",
            return_value=registry,
        ), patch(
            "api.services.agent.tools.web_extract_tools.call_json_response",
            return_value={
                "values": {"company_name": "Example Corp"},
                "confidence": 0.7,
                "evidence": [{"field": "company_name", "quote": "Example Corp"}],
                "gaps": [],
            },
        ):
            result = WebStructuredExtractTool().execute(
                context=self.context,
                prompt="extract",
                params={
                    "candidate_urls": [
                        "https://example.com/empty",
                        "https://example.com/about",
                    ],
                    "field_schema": {"company_name": "string"},
                },
            )
        assert result.data["url"] == "https://example.com/about"
        assert result.data["candidate_urls"] == [
            "https://example.com/empty",
            "https://example.com/about",
        ]
        assert registry.connector.calls == [
            "https://example.com/empty",
            "https://example.com/about",
        ]

    def test_requires_url_or_page_text(self) -> None:
        with self.assertRaises(ToolExecutionError):
            WebStructuredExtractTool().execute(
                context=self.context,
                prompt="extract",
                params={},
            )


if __name__ == "__main__":
    unittest.main()
