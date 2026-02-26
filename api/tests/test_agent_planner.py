from api.schemas import ChatRequest
from api.services.agent.planner import build_plan


def test_direct_website_analysis_prioritizes_inspection_report_and_email_send() -> None:
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
        "gmail.draft",
        "gmail.send",
    ]
    assert steps[0].params.get("url") == "https://axongroup.com/"
    assert steps[2].params.get("to") == "ssebowadisan1@gmail.com"
    assert steps[3].params.get("to") == "ssebowadisan1@gmail.com"


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
