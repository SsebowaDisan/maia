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


def test_url_prompt_with_explicit_source_discovery_keeps_web_research(monkeypatch) -> None:
    # Web-research branching is now LLM-planner driven rather than keyword heuristics.
    def _fake_plan_with_llm(*, request, allowed_tool_ids):
        return [
            {
                "tool_id": "browser.playwright.inspect",
                "title": "Inspect site",
                "params": {"url": "https://axongroup.com"},
            },
            {
                "tool_id": "marketing.web_research",
                "title": "Discover supporting sources",
                "params": {"query": "site:axongroup.com operations"},
            },
            {
                "tool_id": "report.generate",
                "title": "Generate report",
                "params": {"summary": request.message},
            },
        ]

    monkeypatch.setattr(planner_module, "plan_with_llm", _fake_plan_with_llm)
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


def test_highlight_request_adds_file_highlights_and_docs_capture(monkeypatch) -> None:
    def _fake_plan_with_llm(*, request, allowed_tool_ids):
        return [
            {
                "tool_id": "browser.playwright.inspect",
                "title": "Inspect provided website",
                "params": {"url": "https://axongroup.com"},
            },
            {
                "tool_id": "documents.highlight.extract",
                "title": "Extract highlighted terms",
                "params": {},
            },
            {
                "tool_id": "docs.create",
                "title": "Write copied highlights",
                "params": {"title": "Copied Highlights"},
            },
        ]

    monkeypatch.setattr(planner_module, "plan_with_llm", _fake_plan_with_llm)
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

    assert browser_step.params.get("highlight_color") == "yellow"
    assert highlight_step.params.get("highlight_color") == "yellow"
    assert docs_step.params.get("include_copied_highlights") is True


def test_location_request_with_url_keeps_location_web_research(monkeypatch) -> None:
    def _fake_plan_with_llm(*, request, allowed_tool_ids):
        return [
            {
                "tool_id": "browser.playwright.inspect",
                "title": "Inspect provided website",
                "params": {"url": "https://axongroup.com/"},
            },
            {
                "tool_id": "marketing.web_research",
                "title": "Gather external evidence",
                "params": {"query": "Axon Group headquarters address"},
            },
            {
                "tool_id": "report.generate",
                "title": "Generate report",
                "params": {"summary": request.message},
            },
        ]

    monkeypatch.setattr(planner_module, "plan_with_llm", _fake_plan_with_llm)
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

    assert query == "axon group headquarters address"
    assert report_summary != ""


def test_contact_form_request_adds_contact_form_send_step(monkeypatch) -> None:
    monkeypatch.setattr(planner_module, "plan_with_llm", lambda **kwargs: [])
    monkeypatch.setattr(planner_module, "enrich_task_intelligence", lambda **kwargs: {
        "objective": "Submit a contact form message.",
        "target_url": "https://axongroup.com/contact",
        "requires_delivery": False,
        "requires_web_inspection": True,
        "requires_contact_form_submission": True,
        "requested_report": False,
        "intent_tags": ["contact_form_submission"],
    })
    request = ChatRequest(
        message=(
            "Go to https://axongroup.com/contact and fill the contact form with a business inquiry message."
        ),
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "browser.contact_form.send" in tool_ids
    contact_step = next(step for step in steps if step.tool_id == "browser.contact_form.send")
    assert contact_step.params.get("url") == "https://axongroup.com/contact"
    assert "inquiry" in str(contact_step.params.get("subject") or "").lower()


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
            "intent_tags": ["docs_write"],
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


def test_semantic_fallback_can_request_contact_form_submission(monkeypatch) -> None:
    monkeypatch.setattr(planner_module, "plan_with_llm", lambda **kwargs: [])
    monkeypatch.setattr(
        planner_module,
        "enrich_task_intelligence",
        lambda **kwargs: {
            "objective": "Reach out via the website contact form.",
            "target_url": "https://axongroup.com/contact",
            "requires_delivery": False,
            "requires_web_inspection": True,
            "requires_contact_form_submission": True,
            "requested_report": False,
            "preferred_format": "",
        },
    )
    request = ChatRequest(
        message="Contact them through their website form.",
        agent_mode="company_agent",
    )
    steps = build_plan(request)
    tool_ids = [step.tool_id for step in steps]

    assert "browser.contact_form.send" in tool_ids
    contact_step = next(step for step in steps if step.tool_id == "browser.contact_form.send")
    assert contact_step.params.get("url") == "https://axongroup.com/contact"
