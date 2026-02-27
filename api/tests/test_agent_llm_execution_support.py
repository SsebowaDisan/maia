from api.services.agent import llm_execution_support
from api.services.agent.llm_execution_support import (
    build_location_delivery_brief,
    curate_next_steps_for_task,
    polish_contact_form_content,
    polish_email_content,
    rewrite_task_for_execution,
    summarize_conversation_window,
    summarize_step_outcome,
    suggest_failure_recovery,
)


def test_suggest_failure_recovery_disabled(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_RECOVERY_ENABLED", "0")
    hint = suggest_failure_recovery(
        request_message="Send report",
        tool_id="mailer.report_send",
        step_title="Send report",
        error_text="timeout",
        recent_steps=[],
    )
    assert hint == ""


def test_suggest_failure_recovery_parses_json(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_RECOVERY_ENABLED", "1")
    monkeypatch.setattr(
        llm_execution_support,
        "call_json_response",
        lambda **kwargs: {"recovery_hint": "Retry after validating recipient and mailer credentials."},
    )
    hint = suggest_failure_recovery(
        request_message="Send report",
        tool_id="mailer.report_send",
        step_title="Send report",
        error_text="invalid recipient",
        recent_steps=[],
    )
    assert "Retry" in hint


def test_polish_email_content_fallback(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_EMAIL_POLISH_ENABLED", "1")
    monkeypatch.setattr(llm_execution_support, "call_json_response", lambda **kwargs: None)
    result = polish_email_content(
        subject="Weekly report",
        body_text="Body",
        recipient="ops@example.com",
    )
    assert result["subject"] == "Weekly report"
    assert result["body_text"] == "Body"


def test_polish_contact_form_content_fallback(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_CONTACT_POLISH_ENABLED", "1")
    monkeypatch.setattr(llm_execution_support, "call_json_response", lambda **kwargs: None)
    result = polish_contact_form_content(
        subject="Partnership inquiry",
        message_text="Hello team, we would like to discuss collaboration.",
        website_url="https://example.com",
    )
    assert result["subject"] == "Partnership inquiry"
    assert "collaboration" in result["message_text"]


def test_summarize_conversation_window_fallback_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_CONTEXT_SUMMARY_ENABLED", "0")
    summary = summarize_conversation_window(
        latest_user_message="Analyze this company and send a report.",
        turns=[
            {"user": "Analyze axongroup.com", "assistant": "I inspected the site."},
            {"user": "Include location and contacts", "assistant": "I will include both."},
        ],
    )
    assert "Analyze axongroup.com" in summary


def test_summarize_step_outcome_parses_json(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_STEP_SUMMARY_ENABLED", "1")
    monkeypatch.setattr(
        llm_execution_support,
        "call_json_response",
        lambda **kwargs: {
            "summary": "Validated location signals from primary source.",
            "suggestion": "Write findings to Google Docs and log tracker status.",
        },
    )
    row = summarize_step_outcome(
        request_message="Analyze and report",
        tool_id="browser.playwright.inspect",
        step_title="Inspect website",
        result_summary="Inspection completed.",
        result_data={"url": "https://axongroup.com"},
    )
    assert "location signals" in row["summary"]
    assert "Google Docs" in row["suggestion"]


def test_rewrite_task_for_execution_fallback_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_TASK_REWRITE_ENABLED", "0")
    row = rewrite_task_for_execution(
        message="Analyze website and send summary email.",
        agent_goal="Need company location and contacts.",
        conversation_summary="User asked for quick turnaround.",
    )
    assert "Analyze website and send summary email." in row["detailed_task"]
    assert row["deliverables"] == []
    assert row["constraints"] == []


def test_rewrite_task_for_execution_parses_json(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_TASK_REWRITE_ENABLED", "1")
    monkeypatch.setattr(
        llm_execution_support,
        "call_json_response",
        lambda **kwargs: {
            "detailed_task": "Inspect target website, verify location evidence, write report, and deliver via email.",
            "deliverables": ["Location summary", "Source-backed report", "Delivery confirmation"],
            "constraints": ["Use only verified website sources"],
        },
    )
    row = rewrite_task_for_execution(
        message="Analyze and send report.",
        agent_goal=None,
        conversation_summary="",
    )
    assert "verify location evidence" in row["detailed_task"]
    assert "Location summary" in row["deliverables"]
    assert "Use only verified website sources" in row["constraints"]


def test_build_location_delivery_brief_disabled(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_LOCATION_BRIEF_ENABLED", "0")
    row = build_location_delivery_brief(
        request_message="Where are they located?",
        objective="Find company location.",
        report_body="Report body",
    )
    assert row["summary"] == ""
    assert row["address"] == ""
    assert row["evidence_urls"] == []


def test_build_location_delivery_brief_parses_json(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_LOCATION_BRIEF_ENABLED", "1")
    monkeypatch.setattr(
        llm_execution_support,
        "call_json_response",
        lambda **kwargs: {
            "summary": "The company indicates operations in Europe; no single HQ address was explicitly listed.",
            "address": "",
            "evidence_urls": ["https://axongroup.com/about-axon", "invalid-url"],
            "confidence": "medium",
        },
    )
    row = build_location_delivery_brief(
        request_message="Where are they found?",
        objective="Find and email location details.",
        report_body="body",
        sources=[{"url": "https://axongroup.com/about-axon"}],
    )
    assert "operations in Europe" in row["summary"]
    assert row["address"] == ""
    assert row["confidence"] == "medium"
    assert row["evidence_urls"] == ["https://axongroup.com/about-axon"]


def test_build_location_delivery_brief_preserves_llm_response_when_insufficient(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_LOCATION_BRIEF_ENABLED", "1")
    monkeypatch.setattr(
        llm_execution_support,
        "call_json_response",
        lambda **kwargs: {
            "summary": "Evidence is insufficient to determine exact location.",
            "address": "",
            "evidence_urls": [],
            "confidence": "unknown",
        },
    )
    row = build_location_delivery_brief(
        request_message="Where are they found?",
        objective="Find location and address.",
        report_body=(
            "Contact page indicates Adresse: Rue de la Royenne 51, Mouscron, Belgium."
        ),
        sources=[
            {
                "label": "Contact",
                "url": "https://axongroup.com/kontakt",
                "metadata": {"excerpt": "Adresse Rue de la Royenne 51, Mouscron, Belgium"},
            }
        ],
    )
    assert row["address"] == ""
    assert row["summary"] == "Evidence is insufficient to determine exact location."
    assert row["confidence"] == "unknown"
    assert "https://axongroup.com/kontakt" in row["evidence_urls"]


def test_curate_next_steps_filters_task_restatement(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_NEXT_STEPS_ENABLED", "0")
    steps = curate_next_steps_for_task(
        request_message="Analyze https://axongroup.com and send an email with their address.",
        task_contract={
            "objective": "Analyze website and deliver address by email",
            "required_outputs": ["Address of Axon Group", "Email sent to recipient"],
            "required_actions": ["send_email"],
            "required_facts": ["Address of Axon Group"],
            "delivery_target": "ssebowadisan1@gmail.com",
        },
        candidate_steps=[
            "Draft and send an email to ssebowadisan1@gmail.com with the address.",
            "Verify Google token connectivity and rerun the blocked Sheets step.",
            "Validate contradictory evidence before final synthesis.",
        ],
        executed_steps=[
            {"status": "success", "title": "Inspect provided website in live browser"},
            {"status": "failed", "title": "Send report email (server-side)"},
        ],
        actions=[],
        max_items=6,
    )
    assert not any("send an email" in step.lower() for step in steps)
    assert any("google token" in step.lower() for step in steps)


def test_curate_next_steps_applies_post_filter_to_llm_output(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_NEXT_STEPS_ENABLED", "1")
    monkeypatch.setattr(
        llm_execution_support,
        "call_json_response",
        lambda **kwargs: {
            "next_steps": [
                "Send the email with the extracted address.",
                "Resolve missing fact evidence from an authoritative source.",
            ]
        },
    )
    steps = curate_next_steps_for_task(
        request_message="Find address and send email.",
        task_contract={
            "objective": "Find address and send email",
            "required_outputs": ["Address", "Sent email"],
            "required_actions": ["send_email"],
            "required_facts": ["Address"],
            "delivery_target": "recipient@example.com",
        },
        candidate_steps=["Resolve missing fact evidence from an authoritative source."],
        executed_steps=[],
        actions=[],
        max_items=4,
    )
    assert "Resolve missing fact evidence from an authoritative source." in steps
    assert not any("send the email" in step.lower() for step in steps)
