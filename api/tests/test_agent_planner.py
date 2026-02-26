import pytest

from api.schemas import ChatRequest
from api.services.agent import planner as planner_module
from api.services.agent.planner import build_plan


@pytest.fixture(autouse=True)
def _disable_llm_paths(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_PLANNER_ENABLED", "0")
    monkeypatch.setenv("MAIA_AGENT_LLM_PLAN_CRITIC_ENABLED", "0")
    monkeypatch.setenv("MAIA_AGENT_LLM_QUERY_REWRITE_ENABLED", "0")


def test_direct_website_analysis_prioritizes_inspection_and_report_then_server_delivery() -> None:
    request = ChatRequest(
        message=(
            "here is website https://axongroup.com/ analysis and find what they do "
            "and send the report to ssebowadisan1@gmail.com"
        ),
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "marketing.web_research" not in tool_ids
    assert tool_ids == [
        "browser.playwright.inspect",
        "report.generate",
    ]
    assert steps[0].params.get("url") == "https://axongroup.com/"


def test_url_prompt_with_explicit_source_discovery_keeps_web_research() -> None:
    request = ChatRequest(
        message=(
            "Use https://axongroup.com and search online sources about competitors, then summarize."
        ),
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "marketing.web_research" in tool_ids
    assert "browser.playwright.inspect" in tool_ids
    assert "report.generate" in tool_ids


def test_build_plan_uses_llm_steps_when_available(monkeypatch) -> None:
    def _fake_plan_with_llm(*, request, allowed_tool_ids):
        return [
            {
                "tool_id": "docs.create",
                "title": "Create working doc",
                "params": {"title": "Company Draft"},
            },
            {
                "tool_id": "report.generate",
                "title": "Generate report",
                "params": {"summary": request.message},
            },
        ]

    monkeypatch.setattr(planner_module, "plan_with_llm", _fake_plan_with_llm)
    request = ChatRequest(
        message="Prepare a structured company update for leadership.",
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert tool_ids == [
        "report.generate",
        "docs.create",
    ]


def test_highlight_request_adds_file_highlights_and_docs_capture() -> None:
    request = ChatRequest(
        message=(
            "Analyze https://axongroup.com, highlight copied words from files and website in green, "
            "then open docs and write the copied words."
        ),
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "browser.playwright.inspect" in tool_ids
    assert "documents.highlight.extract" in tool_ids
    assert "docs.create" in tool_ids

    browser_step = next(step for step in steps if step.tool_id == "browser.playwright.inspect")
    docs_step = next(step for step in steps if step.tool_id == "docs.create")
    highlight_step = next(step for step in steps if step.tool_id == "documents.highlight.extract")

    assert browser_step.params.get("highlight_color") == "green"
    assert highlight_step.params.get("highlight_color") == "green"
    assert docs_step.params.get("include_copied_highlights") is True


def test_location_request_with_url_keeps_location_web_research() -> None:
    request = ChatRequest(
        message=(
            "analysis https://axongroup.com/ and send an email to "
            "ssebowadisan1@gmail.com about where they are found"
        ),
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "browser.playwright.inspect" in tool_ids
    assert "marketing.web_research" in tool_ids
    assert "report.generate" in tool_ids

    web_step = next(step for step in steps if step.tool_id == "marketing.web_research")
    report_step = next(step for step in steps if step.tool_id == "report.generate")
    query = str(web_step.params.get("query") or "").lower()
    report_summary = str(report_step.params.get("summary") or "").lower()

    assert "site:axongroup.com" in query
    assert any(token in query for token in ("location", "headquarters", "address", "located"))
    assert any(token in report_summary for token in ("located", "headquarters", "address"))


def test_build_plan_uses_llm_intent_semantic_fallback_when_llm_plan_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(planner_module, "plan_with_llm", lambda **kwargs: [])
    monkeypatch.setattr(
        planner_module,
        "enrich_task_intelligence",
        lambda **kwargs: {
            "objective": "Determine where Axon Group is located and share findings.",
            "target_url": "https://axongroup.com/",
            "delivery_email": "ssebowadisan1@gmail.com",
            "requires_delivery": True,
            "requires_web_inspection": True,
            "requested_report": True,
            "preferred_format": "document",
        },
    )
    request = ChatRequest(
        message="yo check this company out and mail where they are based to ssebowadisan1@gmail.com",
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "browser.playwright.inspect" in tool_ids
    assert "report.generate" in tool_ids
    assert "docs.create" in tool_ids
    assert "gmail.send" not in tool_ids
