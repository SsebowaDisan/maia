from __future__ import annotations

from api.services.agent.tools.base import ToolExecutionContext
from api.services.agent.tools.data_tools import ReportGenerationTool


def _context() -> ToolExecutionContext:
    return ToolExecutionContext(
        user_id="u1",
        tenant_id="t1",
        conversation_id="c1",
        run_id="r1",
        mode="company_agent",
        settings={},
    )


def test_report_generation_answers_direct_question_with_llm(monkeypatch) -> None:
    context = _context()
    monkeypatch.setenv("MAIA_AGENT_LLM_REPORT_QA_ENABLED", "1")
    monkeypatch.setattr(
        "api.services.agent.tools.data_tools.call_text_response",
        lambda **kwargs: (
            "Machine learning is a field of AI where models learn patterns from data "
            "to make predictions or decisions."
        ),
    )
    result = ReportGenerationTool().execute(
        context=context,
        prompt="answer this question",
        params={"title": "Quick Answer", "summary": "what is machine learning?"},
    )
    assert "Machine learning is a field of AI" in result.content
