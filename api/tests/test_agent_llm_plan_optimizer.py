from api.schemas import ChatRequest
from api.services.agent import llm_plan_optimizer
from api.services.agent.llm_plan_optimizer import optimize_plan_rows, rewrite_search_query


def test_optimize_plan_rows_returns_input_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_PLAN_CRITIC_ENABLED", "0")
    rows = [{"tool_id": "report.generate", "title": "Report", "params": {}}]
    request = ChatRequest(message="Generate a report", agent_mode="company_agent")
    output = optimize_plan_rows(
        request=request,
        rows=rows,
        allowed_tool_ids={"report.generate"},
    )
    assert output == rows


def test_optimize_plan_rows_filters_tools(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_PLAN_CRITIC_ENABLED", "1")

    def _fake_json_response(**kwargs):
        return {
            "steps": [
                {"tool_id": "report.generate", "title": "Generate report", "params": {"summary": "A"}},
                {"tool_id": "unknown.tool", "title": "Nope", "params": {}},
            ]
        }

    monkeypatch.setattr(llm_plan_optimizer, "call_json_response", _fake_json_response)
    request = ChatRequest(message="Generate report", agent_mode="company_agent")
    output = optimize_plan_rows(
        request=request,
        rows=[{"tool_id": "report.generate", "title": "Report", "params": {}}],
        allowed_tool_ids={"report.generate"},
    )
    assert len(output) == 1
    assert output[0]["tool_id"] == "report.generate"


def test_rewrite_search_query_uses_fallback_on_empty(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_QUERY_REWRITE_ENABLED", "1")
    monkeypatch.setattr(llm_plan_optimizer, "call_text_response", lambda **kwargs: "")
    request = ChatRequest(message="find competitors", agent_mode="company_agent")
    query = rewrite_search_query(
        query="company overview",
        request=request,
        fallback_url="https://axongroup.com",
    )
    assert query == "company overview"
