from __future__ import annotations

from api.services.agent.brain.workflow_assembly import (
    _build_definition,
    _extract_email,
    _degraded_plan_without_llm,
    _normalize_step_tool_ids,
    _sanitize_plan,
)


def test_research_request_routes_to_real_web_tools() -> None:
    step = {
        "step_id": "step_1",
        "agent_role": "researcher",
        "description": "Gather external evidence and source-backed findings.",
        "tools_needed": [],
    }
    tool_ids = _normalize_step_tool_ids(
        step=step,
        request_description="Research machine learning and write a report with sources.",
    )
    assert "marketing.web_research" in tool_ids
    assert "web.extract.structured" in tool_ids
    assert "browser.playwright.inspect" not in tool_ids
    assert "report.generate" not in tool_ids


def test_research_request_with_explicit_url_allows_browser_inspection() -> None:
    step = {
        "step_id": "step_1",
        "agent_role": "researcher",
        "description": "Inspect https://example.com and gather evidence from the page.",
        "tools_needed": [],
    }
    tool_ids = _normalize_step_tool_ids(
        step=step,
        request_description="Inspect https://example.com and summarize the findings.",
    )
    assert "marketing.web_research" in tool_ids
    assert "web.extract.structured" in tool_ids
    assert "browser.playwright.inspect" in tool_ids


def test_browser_hint_without_visual_request_does_not_force_browser_inspection() -> None:
    step = {
        "step_id": "step_1",
        "agent_role": "research specialist",
        "description": "Conduct balanced research on machine learning using authoritative sources to gather key insights.",
        "tools_needed": ["browser"],
    }
    tool_ids = _normalize_step_tool_ids(
        step=step,
        request_description="Make the research about machine learning and write an email about the research.",
    )
    assert "marketing.web_research" in tool_ids
    assert "web.extract.structured" in tool_ids
    assert "browser.playwright.inspect" not in tool_ids


def test_delivery_step_keeps_mail_tools_without_forcing_web_tools() -> None:
    step = {
        "step_id": "step_2",
        "agent_role": "deliverer",
        "description": "Send the final report to the recipient by email.",
        "tools_needed": [],
    }
    tool_ids = _normalize_step_tool_ids(
        step=step,
        request_description="Research competitors and email the report.",
    )
    assert "gmail.draft" in tool_ids
    assert "gmail.send" in tool_ids
    assert "mailer.report_send" in tool_ids
    assert "marketing.web_research" not in tool_ids
    assert "report.generate" not in tool_ids


def test_email_draft_step_keeps_report_generation_and_draft_without_send_tools() -> None:
    step = {
        "step_id": "step_2",
        "agent_role": "email specialist",
        "description": "Synthesize the research into a concise email draft for the recipient.",
        "tools_needed": ["summary", "email", "research"],
    }
    tool_ids = _normalize_step_tool_ids(
        step=step,
        request_description="Make the research about machine learning and write an email about the research to ssebowadisan1@gmail.com",
    )
    assert "gmail.draft" not in tool_ids
    assert "gmail.send" not in tool_ids
    assert "mailer.report_send" not in tool_ids
    assert "report.generate" in tool_ids
    assert "marketing.web_research" not in tool_ids


def test_email_specialist_never_keeps_send_tools_even_when_hint_requests_send() -> None:
    step = {
        "step_id": "step_2",
        "agent_role": "email specialist",
        "description": "Compose a polished email for the recipient and keep it ready for delivery.",
        "tools_needed": ["send", "email", "summary"],
    }
    tool_ids = _normalize_step_tool_ids(
        step=step,
        request_description="Make the research about machine learning and write an email about the research to ssebowadisan1@gmail.com",
    )
    assert "gmail.send" not in tool_ids
    assert "mailer.report_send" not in tool_ids
    assert "report.generate" in tool_ids


def test_research_step_with_full_request_text_stays_evidence_first() -> None:
    step = {
        "step_id": "step_1",
        "agent_role": "researcher",
        "description": "make the research about machine learning and write an email about the research to ssebowadisan1@gmail.com",
        "tools_needed": ["research"],
    }
    tool_ids = _normalize_step_tool_ids(
        step=step,
        request_description="make the research about machine learning and write an email about the research to ssebowadisan1@gmail.com",
    )
    assert "marketing.web_research" in tool_ids
    assert "web.extract.structured" in tool_ids
    assert "gmail.draft" not in tool_ids
    assert "gmail.send" not in tool_ids


def test_writer_synthesis_step_keeps_report_generation_over_stray_research_hint() -> None:
    step = {
        "step_id": "step_2",
        "agent_role": "writer",
        "description": "Synthesize the findings into a clear response for the user.",
        "tools_needed": ["research"],
    }
    tool_ids = _normalize_step_tool_ids(
        step=step,
        request_description="make the research about machine learning and write an email about the research to ssebowadisan1@gmail.com",
    )
    assert "report.generate" in tool_ids
    assert "gmail.draft" not in tool_ids


def test_no_web_request_blocks_research_tools_even_when_step_mentions_research() -> None:
    step = {
        "step_id": "step_1",
        "agent_role": "researcher",
        "description": "Research the topic and gather evidence.",
        "tools_needed": ["research"],
    }
    tool_ids = _normalize_step_tool_ids(
        step=step,
        request_description="Research this topic but do not browse the web.",
    )
    assert "marketing.web_research" not in tool_ids
    assert "web.extract.structured" not in tool_ids
    assert "browser.playwright.inspect" not in tool_ids


def test_degraded_plan_builds_multi_step_flow_for_research_email_requests() -> None:
    plan = _degraded_plan_without_llm(
        "Research machine learning trends, write a report, and send it to ssebowadisan1@gmail.com",
    )
    steps = plan.get("steps") or []
    assert len(steps) >= 2
    assert any(str(step.get("agent_role")) == "deliverer" for step in steps)
    assert any(str(connector.get("connector_id")) == "gmail" for connector in (plan.get("connectors_needed") or []))


def test_sanitize_plan_rewrites_non_worker_roles_and_tool_like_roles() -> None:
    plan = _sanitize_plan(
        {
            "steps": [
                {
                    "step_id": "first",
                    "agent_role": "brain",
                    "description": "Research supporting evidence and validate claims.",
                    "tools_needed": ["research"],
                },
                {
                    "step_id": "step_2",
                    "agent_role": "Browser Playwright Inspect",
                    "description": "Send the final email to the recipient.",
                    "tools_needed": ["gmail.send"],
                },
            ],
            "edges": [{"from_step": "first", "to_step": "step_2"}],
        },
        description="Research and then email a report.",
    )
    steps = plan.get("steps") or []
    assert len(steps) == 2
    assert steps[0]["step_id"] == "step_1"
    assert steps[1]["step_id"] == "step_2"
    assert steps[0]["agent_role"] != "brain"
    assert steps[1]["agent_role"].lower() != "browser playwright inspect"


def test_extract_email_strips_trailing_punctuation() -> None:
    assert _extract_email("Send the report to ssebowadisan1@gmail.com.") == "ssebowadisan1@gmail.com"


def test_sanitize_plan_rescopes_research_email_workflow_steps() -> None:
    request = "make the research about machine learning and write an email about the research to ssebowadisan1@gmail.com"
    plan = _sanitize_plan(
        {
            "steps": [
                {
                    "step_id": "step_1",
                    "agent_role": "researcher",
                    "description": request,
                    "tools_needed": ["research"],
                },
                {
                    "step_id": "step_2",
                    "agent_role": "writer",
                    "description": "Synthesize the findings into a clear response for the user.",
                    "tools_needed": ["report"],
                },
                {
                    "step_id": "step_3",
                    "agent_role": "deliverer",
                    "description": "Send the final response by email to ssebowadisan1@gmail.com.",
                    "tools_needed": ["email"],
                },
            ],
            "edges": [
                {"from_step": "step_1", "to_step": "step_2"},
                {"from_step": "step_2", "to_step": "step_3"},
            ],
        },
        description=request,
    )
    steps = plan["steps"]
    assert "Do not draft or send the email" in steps[0]["description"]
    assert "Compose a polished, citation-rich email draft about machine learning" in steps[1]["description"]
    assert "Subject line" in steps[1]["description"]
    assert "This stage drafts only; do not dispatch the email" in steps[1]["description"]
    assert "ssebowadisan1@gmail.com" in steps[1]["description"]
    assert steps[2]["description"] == "Send the cited email draft produced by the previous step to ssebowadisan1@gmail.com without changing its substance."


def test_build_definition_assigns_realistic_timeouts_for_rescoped_research_email_flow() -> None:
    request = "make the research about machine learning and write an email about the research to ssebowadisan1@gmail.com"
    sanitized = _sanitize_plan(
        {
            "steps": [
                {
                    "step_id": "step_1",
                    "agent_role": "researcher",
                    "description": request,
                    "tools_needed": ["research"],
                },
                {
                    "step_id": "step_2",
                    "agent_role": "writer",
                    "description": "Synthesize the findings into a clear response for the user.",
                    "tools_needed": ["report"],
                },
                {
                    "step_id": "step_3",
                    "agent_role": "deliverer",
                    "description": "Send the final response by email to ssebowadisan1@gmail.com.",
                    "tools_needed": ["email"],
                },
            ],
            "edges": [
                {"from_step": "step_1", "to_step": "step_2"},
                {"from_step": "step_2", "to_step": "step_3"},
            ],
        },
        description=request,
    )
    definition = _build_definition(
        request,
        sanitized["steps"],
        sanitized["edges"],
    )
    timeouts = {
        str(step["step_id"]): int(step["timeout_s"])
        for step in definition["steps"]
    }
    assert timeouts["step_1"] >= 1200
    assert timeouts["step_2"] >= 420
    assert timeouts["step_3"] >= 420


def test_sanitize_plan_rebalances_misordered_research_email_flow() -> None:
    request = "make the research about machine learning and write an email about the research to ssebowadisan1@gmail.com"
    plan = _sanitize_plan(
        {
            "steps": [
                {
                    "step_id": "step_1",
                    "agent_role": "email specialist",
                    "description": "Write the email for the recipient with citations.",
                    "tools_needed": ["email", "report"],
                },
                {
                    "step_id": "step_2",
                    "agent_role": "research specialist",
                    "description": "Look up authoritative sources on machine learning.",
                    "tools_needed": ["research"],
                },
                {
                    "step_id": "step_3",
                    "agent_role": "delivery specialist",
                    "description": "Send the approved draft by email.",
                    "tools_needed": ["send"],
                },
            ],
            "edges": [
                {"from_step": "step_1", "to_step": "step_2"},
                {"from_step": "step_2", "to_step": "step_3"},
            ],
        },
        description=request,
    )

    steps = plan["steps"]
    assert steps[0]["description"].startswith("Research machine learning")
    assert "Do not draft or send the email" in steps[0]["description"]
    assert "premium body" in steps[1]["description"]
    assert "This stage drafts only; do not dispatch the email." in steps[1]["description"]
    assert steps[2]["description"] == "Send the cited email draft produced by the previous step to ssebowadisan1@gmail.com without changing its substance."


def test_research_brief_step_keeps_synthesis_without_delivery_tools() -> None:
    step = {
        "step_id": "step_1",
        "agent_role": "research specialist",
        "description": (
            "Research machine learning using multiple authoritative sources and return an "
            "executive research brief with inline citations and an Evidence Citations section."
        ),
        "tools_needed": ["research"],
    }
    tool_ids = _normalize_step_tool_ids(
        step=step,
        request_description="make the research about machine learning and write an email about the research to ssebowadisan1@gmail.com",
    )
    assert "marketing.web_research" in tool_ids
    assert "web.extract.structured" in tool_ids
    assert "report.generate" in tool_ids
    assert "gmail.draft" not in tool_ids
    assert "gmail.send" not in tool_ids


def test_build_definition_uses_clean_focus_for_research_query_mapping() -> None:
    request = "make the research about machine learning and write an email about the research to ssebowadisan1@gmail.com"
    sanitized = _sanitize_plan(
        {
            "steps": [
                {
                    "step_id": "step_1",
                    "agent_role": "research specialist",
                    "description": request,
                    "tools_needed": ["research"],
                },
                {
                    "step_id": "step_2",
                    "agent_role": "email specialist",
                    "description": "Draft the cited email.",
                    "tools_needed": ["report"],
                },
            ],
            "edges": [{"from_step": "step_1", "to_step": "step_2"}],
        },
        description=request,
    )
    definition = _build_definition(
        request,
        sanitized["steps"],
        sanitized["edges"],
    )
    research_step = definition["steps"][0]
    assert research_step["input_mapping"]["query"] == "literal:machine learning"
    assert research_step["input_mapping"]["topic"] == "literal:machine learning"
