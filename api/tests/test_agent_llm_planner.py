from api.schemas import ChatRequest
from api.services.agent import llm_planner
from api.services.agent.llm_planner import plan_with_llm


def test_plan_with_llm_returns_empty_when_api_key_missing(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    request = ChatRequest(message="Analyze this company", agent_mode="company_agent")
    rows = plan_with_llm(
        request=request,
        allowed_tool_ids={"report.generate", "browser.playwright.inspect"},
    )
    assert rows == []


def test_plan_with_llm_filters_unknown_tools_and_sanitizes(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def _fake_request_openai_plan(**kwargs):
        return {
            "steps": [
                {"tool_id": "unknown.tool", "title": "Ignore", "params": {}},
                {"tool_id": "report.generate", "title": "", "params": {"summary": "A" * 5000}},
                {
                    "tool_id": "browser.playwright.inspect",
                    "title": "Inspect website",
                    "params": {"url": "https://axongroup.com", "depth": {"value": 2}},
                },
            ]
        }

    monkeypatch.setattr(llm_planner, "_request_openai_plan", _fake_request_openai_plan)
    request = ChatRequest(
        message="Analyze https://axongroup.com and prepare a report.",
        agent_mode="company_agent",
    )
    rows = plan_with_llm(
        request=request,
        allowed_tool_ids={"report.generate", "browser.playwright.inspect"},
    )

    assert [row["tool_id"] for row in rows] == [
        "report.generate",
        "browser.playwright.inspect",
    ]
    assert rows[0]["title"]
    assert len(str(rows[0]["params"].get("summary") or "")) <= 1200


def test_plan_with_llm_passes_preferred_tool_ids_to_prompt_builder(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    captured: dict[str, object] = {}

    def _fake_request_openai_plan(**kwargs):
        captured.update(kwargs)
        return {"steps": []}

    monkeypatch.setattr(llm_planner, "_request_openai_plan", _fake_request_openai_plan)
    request = ChatRequest(message="Prepare research and docs update", agent_mode="company_agent")
    _ = plan_with_llm(
        request=request,
        allowed_tool_ids={"marketing.web_research", "workspace.docs.research_notes"},
        preferred_tool_ids={"workspace.docs.research_notes", "unknown.tool"},
    )

    assert captured.get("preferred_tool_ids") == ["workspace.docs.research_notes"]
