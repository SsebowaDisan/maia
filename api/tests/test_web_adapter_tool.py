from __future__ import annotations

from unittest.mock import patch
import unittest

from api.services.agent.models import AgentSource
from api.services.agent.tools.base import ToolExecutionContext, ToolExecutionResult, ToolTraceEvent
from api.services.agent.tools.web_adapter_tools import WebDatasetAdapterTool


class WebDatasetAdapterToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = ToolExecutionContext(
            user_id="u1",
            tenant_id="t1",
            conversation_id="c1",
            run_id="r1",
            mode="company_agent",
            settings={},
        )

    def _stub_extraction_result(self) -> ToolExecutionResult:
        return ToolExecutionResult(
            summary="stub",
            content="stub content",
            data={"url": "https://example.com", "values": {"repo_name": "maia"}, "confidence": 0.66},
            sources=[
                AgentSource(
                    source_type="web",
                    label="Example",
                    url="https://example.com",
                    score=0.66,
                    metadata={},
                )
            ],
            next_steps=[],
            events=[
                ToolTraceEvent(
                    event_type="normalize_response",
                    title="Structured extraction complete",
                    data={"tool_id": "web.extract.structured", "scene_surface": "preview"},
                )
            ],
        )

    def test_uses_requested_adapter_when_provided(self) -> None:
        with patch(
            "api.services.agent.tools.web_adapter_tools.WebStructuredExtractTool.execute",
            return_value=self._stub_extraction_result(),
        ):
            result = WebDatasetAdapterTool().execute(
                context=self.context,
                prompt="extract",
                params={
                    "url": "https://github.com/org/repo",
                    "adapter": "github_repository",
                },
            )
        assert result.data.get("adapter") == "github_repository"
        assert result.data.get("adapter_selected_by_llm") is False
        assert result.data.get("values", {}).get("repo_name") == "maia"
        assert float(result.data.get("adapter_selection_confidence") or 0.0) == 1.0

    def test_uses_llm_adapter_selection_when_not_provided(self) -> None:
        with patch(
            "api.services.agent.tools.web_adapter_tools.call_json_response",
            return_value={"adapter": "reuters_article", "confidence": 0.86, "reason": "News domain match"},
        ), patch(
            "api.services.agent.tools.web_adapter_tools.WebStructuredExtractTool.execute",
            return_value=self._stub_extraction_result(),
        ):
            result = WebDatasetAdapterTool().execute(
                context=self.context,
                prompt="extract article",
                params={"url": "https://www.reuters.com/world/"},
        )
        assert result.data.get("adapter") == "reuters_article"
        assert result.data.get("adapter_selected_by_llm") is True
        assert float(result.data.get("adapter_selection_confidence") or 0.0) >= 0.8


if __name__ == "__main__":
    unittest.main()
