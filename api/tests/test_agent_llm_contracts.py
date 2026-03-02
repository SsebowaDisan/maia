from api.services.agent import llm_contracts
from api.services.agent.llm_contracts import (
    NO_HARDCODE_WORDS_CONSTRAINT,
    build_task_contract,
    propose_fact_probe_steps,
    verify_task_contract_fulfillment,
)


def test_build_task_contract_disabled_uses_minimal_fallback(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_TASK_CONTRACT_ENABLED", "0")
    row = build_task_contract(
        message="Analyze website and send email about where they are located to team@example.com",
        agent_goal=None,
        rewritten_task="",
        deliverables=["Location summary"],
        constraints=[],
        intent_tags=["location_lookup"],
        conversation_summary="",
    )
    assert row["delivery_target"] == "team@example.com"
    assert "send_email" in row["required_actions"]
    assert any("location" in str(item).lower() for item in row["required_facts"])
    assert row["constraints"][0] == NO_HARDCODE_WORDS_CONSTRAINT
    assert "Target website URL" in row["missing_requirements"]
    assert "Required facts to verify in the final answer" not in row["missing_requirements"]
    assert len(row["success_checks"]) >= 2


def test_build_task_contract_parses_json(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_TASK_CONTRACT_ENABLED", "1")
    monkeypatch.setattr(
        llm_contracts,
        "call_json_response",
        lambda **kwargs: {
            "objective": "Identify company location and deliver by email.",
            "required_outputs": ["Location report", "Delivery confirmation"],
            "required_facts": ["Include location and address when available."],
            "required_actions": ["send_email", "create_document", "invalid_action"],
            "constraints": ["Use cited sources only."],
            "delivery_target": "ops@example.com",
            "missing_requirements": ["Need target website URL"],
            "success_checks": ["Delivery confirmed", "Required facts present"],
        },
    )
    row = build_task_contract(
        message="Analyze and send report to ops@example.com",
        rewritten_task="Analyze and deliver report",
        deliverables=[],
        constraints=[],
        intent_tags=["delivery"],
        conversation_summary="",
    )
    assert row["objective"].startswith("Identify company location")
    assert row["required_actions"] == ["send_email", "create_document"]
    assert row["delivery_target"] == "ops@example.com"
    assert NO_HARDCODE_WORDS_CONSTRAINT in row["constraints"]
    assert row["missing_requirements"] == ["Need target website URL"]
    assert row["success_checks"] == ["Delivery confirmed", "Required facts present"]


def test_build_task_contract_filters_unaligned_send_email_action(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_TASK_CONTRACT_ENABLED", "1")
    monkeypatch.setattr(
        llm_contracts,
        "call_json_response",
        lambda **kwargs: {
            "objective": "Research local sellers",
            "required_outputs": ["Company list"],
            "required_facts": ["Company name and source"],
            "required_actions": ["send_email", "create_document"],
            "constraints": [],
            "delivery_target": "",
            "missing_requirements": [],
            "success_checks": ["Evidence captured"],
        },
    )
    row = build_task_contract(
        message="search for companies in kortrijk that sell office chairs",
        agent_goal=None,
        rewritten_task="Find local office chair sellers and summarize results.",
        deliverables=["Company list"],
        constraints=[],
        intent_tags=["web_research", "report_generation"],
        conversation_summary="Earlier run asked for an email follow-up.",
    )
    assert row["required_actions"] == ["create_document"]
    assert "send_email" not in row["required_actions"]
    assert row["delivery_target"] == ""


def test_build_task_contract_classifier_flags_missing_recipient_and_output_format(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_TASK_CONTRACT_ENABLED", "0")
    row = build_task_contract(
        message="Send the final report when ready",
        agent_goal=None,
        rewritten_task="",
        deliverables=[],
        constraints=[],
        intent_tags=["email_delivery", "report_generation"],
        conversation_summary="",
    )
    assert "Recipient email address for delivery" in row["missing_requirements"]
    assert "Required facts to verify in the final answer" not in row["missing_requirements"]
    assert "Preferred output format or artifact type" in row["missing_requirements"]


def test_build_task_contract_merges_classifier_missing_requirements_with_llm_response(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_TASK_CONTRACT_ENABLED", "1")
    monkeypatch.setattr(
        llm_contracts,
        "call_json_response",
        lambda **kwargs: {
            "objective": "Send report",
            "required_outputs": [],
            "required_facts": [],
            "required_actions": ["send_email"],
            "constraints": [],
            "delivery_target": "",
            "missing_requirements": [],
            "success_checks": ["Delivered"],
        },
    )
    row = build_task_contract(
        message="Send report",
        agent_goal=None,
        rewritten_task="Send report",
        deliverables=[],
        constraints=[],
        intent_tags=["email_delivery", "report_generation"],
        conversation_summary="",
    )
    assert "Recipient email address for delivery" in row["missing_requirements"]
    assert "Preferred output format or artifact type" in row["missing_requirements"]


def test_build_task_contract_handles_markdown_url_without_false_missing_target(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_TASK_CONTRACT_ENABLED", "0")
    row = build_task_contract(
        message=(
            "Analyze [https://axongroup.com/](https://axongroup.com/) "
            "and send location summary to ops@example.com"
        ),
        agent_goal=None,
        rewritten_task="",
        deliverables=["Location summary"],
        constraints=[],
        intent_tags=["location_lookup", "email_delivery"],
        conversation_summary="",
    )
    assert row["delivery_target"] == "ops@example.com"
    assert "Target website URL" not in row["missing_requirements"]


def test_build_task_contract_sanitizes_false_missing_recipient_and_fact_requirements(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_TASK_CONTRACT_ENABLED", "1")
    monkeypatch.setattr(
        llm_contracts,
        "call_json_response",
        lambda **kwargs: {
            "objective": "Analyze site and email location findings",
            "required_outputs": ["Location summary email"],
            "required_facts": ["Company location details from the analysis"],
            "required_actions": ["send_email"],
            "constraints": [],
            "delivery_target": "ssebowadisan1@gmail.com",
            "missing_requirements": [
                "Recipient email address",
                "Company location details from the analysis",
            ],
            "success_checks": ["Location findings delivered"],
        },
    )
    row = build_task_contract(
        message=(
            "Analyze [https://axongroup.com/](https://axongroup.com/) and send an email to "
            "ssebowadisan1@gmail.com about the company's location."
        ),
        agent_goal=None,
        rewritten_task="Analyze company location and email findings.",
        deliverables=[],
        constraints=[],
        intent_tags=["email_delivery", "location_lookup", "web_research"],
        conversation_summary="",
    )
    assert row["delivery_target"] == "ssebowadisan1@gmail.com"
    assert row["required_facts"] == ["Company location details from the analysis"]
    assert row["missing_requirements"] == []


def test_verify_task_contract_disabled_returns_ready(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_DELIVERY_CHECK_ENABLED", "0")
    row = verify_task_contract_fulfillment(
        contract={"objective": "test"},
        request_message="test",
        executed_steps=[],
        actions=[],
        report_body="",
        sources=[],
        allowed_tool_ids=["docs.create"],
    )
    assert row["ready_for_final_response"] is True
    assert row["ready_for_external_actions"] is True


def test_verify_task_contract_disabled_blocks_unverified_required_facts(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_DELIVERY_CHECK_ENABLED", "0")
    row = verify_task_contract_fulfillment(
        contract={
            "objective": "Find headquarters and email summary",
            "required_facts": ["Headquarters city and country"],
            "required_actions": ["send_email"],
            "delivery_target": "ops@example.com",
        },
        request_message="Analyze website and send summary",
        executed_steps=[
            {
                "tool_id": "marketing.web_research",
                "status": "success",
                "summary": "Collected company overview details.",
            }
        ],
        actions=[{"tool_id": "marketing.web_research", "status": "success", "summary": "overview collected"}],
        report_body="General company profile information only.",
        sources=[{"url": "https://example.com", "label": "Example", "metadata": {"excerpt": "Company profile"}}],
        allowed_tool_ids=["marketing.web_research", "browser.playwright.inspect", "gmail.draft"],
    )
    assert row["ready_for_final_response"] is False
    assert row["ready_for_external_actions"] is False
    assert any("Unverified required fact" in item for item in row["missing_items"])
    assert any(item.get("tool_id") in {"marketing.web_research", "browser.playwright.inspect"} for item in row["recommended_remediation"])


def test_verify_task_contract_disabled_blocks_missing_required_external_action(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_DELIVERY_CHECK_ENABLED", "0")
    row = verify_task_contract_fulfillment(
        contract={
            "objective": "Email summary",
            "required_facts": [],
            "required_actions": ["send_email"],
            "delivery_target": "ops@example.com",
        },
        request_message="Send summary to ops@example.com",
        executed_steps=[],
        actions=[{"tool_id": "gmail.draft", "status": "success", "summary": "draft created"}],
        report_body="Summary ready.",
        sources=[],
        allowed_tool_ids=["gmail.draft", "gmail.send"],
    )
    assert row["ready_for_final_response"] is False
    assert row["ready_for_external_actions"] is False
    assert "Required action not completed: send_email" in row["missing_items"]
    assert row["recommended_remediation"] == [
        {
            "tool_id": "gmail.draft",
            "title": "Draft email delivery content",
            "params": {"to": "ops@example.com"},
        }
    ]


def test_verify_task_contract_missing_delivery_target_avoids_email_remediation(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_DELIVERY_CHECK_ENABLED", "0")
    row = verify_task_contract_fulfillment(
        contract={
            "objective": "Send summary",
            "required_facts": [],
            "required_actions": ["send_email"],
            "delivery_target": "",
        },
        request_message="Send summary",
        executed_steps=[],
        actions=[],
        report_body="Summary ready.",
        sources=[],
        allowed_tool_ids=["gmail.draft", "gmail.send"],
    )
    assert row["ready_for_final_response"] is False
    assert row["ready_for_external_actions"] is False
    assert "Missing delivery target for required action: send_email" in row["missing_items"]
    assert row["recommended_remediation"] == []


def test_verify_task_contract_pre_send_gate_does_not_self_block_pending_send_action(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_DELIVERY_CHECK_ENABLED", "1")
    row = verify_task_contract_fulfillment(
        contract={
            "objective": "Email summary",
            "required_facts": [],
            "required_actions": ["send_email"],
            "delivery_target": "ops@example.com",
        },
        request_message="Send summary to ops@example.com",
        executed_steps=[],
        actions=[{"tool_id": "gmail.draft", "status": "success", "summary": "draft created"}],
        report_body="Summary ready.",
        sources=[],
        allowed_tool_ids=["gmail.draft", "gmail.send", "mailer.report_send"],
        pending_action_tool_id="mailer.report_send",
    )
    assert row["ready_for_final_response"] is True
    assert row["ready_for_external_actions"] is True
    assert row["missing_items"] == []


def test_verify_task_contract_parses_json_and_filters_remediation(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_DELIVERY_CHECK_ENABLED", "1")
    monkeypatch.setattr(
        llm_contracts,
        "call_json_response",
        lambda **kwargs: {
            "ready_for_final_response": False,
            "ready_for_external_actions": False,
            "missing_items": ["Missing address in final output"],
            "reason": "Address evidence is required before sending.",
            "recommended_remediation": [
                {"tool_id": "docs.create", "title": "Draft location note", "params": {"title": "Location Brief"}},
                {"tool_id": "unknown.tool", "title": "Ignore me", "params": {}},
                "bad-row",
            ],
        },
    )
    row = verify_task_contract_fulfillment(
        contract={"objective": "Location + delivery"},
        request_message="Analyze and send",
        executed_steps=[{"tool_id": "browser.playwright.inspect", "status": "success"}],
        actions=[],
        report_body="Findings",
        sources=[{"url": "https://example.com"}],
        allowed_tool_ids=["docs.create", "workspace.docs.research_notes"],
    )
    assert row["ready_for_final_response"] is False
    assert row["ready_for_external_actions"] is False
    assert row["missing_items"] == ["Missing address in final output"]
    assert row["recommended_remediation"] == [
        {"tool_id": "docs.create", "title": "Draft location note", "params": {"title": "Location Brief"}}
    ]


def test_verify_task_contract_enforces_no_hardcode_constraint_in_execution_payload(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_DELIVERY_CHECK_ENABLED", "1")
    captured_prompt = {"text": ""}

    def _fake_call_json_response(**kwargs):
        captured_prompt["text"] = str(kwargs.get("user_prompt") or "")
        return {
            "ready_for_final_response": True,
            "ready_for_external_actions": True,
            "missing_items": [],
            "reason": "",
            "recommended_remediation": [],
        }

    monkeypatch.setattr(llm_contracts, "call_json_response", _fake_call_json_response)
    verify_task_contract_fulfillment(
        contract={"objective": "test", "constraints": []},
        request_message="Analyze and send",
        executed_steps=[],
        actions=[],
        report_body="",
        sources=[],
        allowed_tool_ids=["docs.create"],
    )
    assert NO_HARDCODE_WORDS_CONSTRAINT in captured_prompt["text"]


def test_propose_fact_probe_steps_disabled(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_FACT_PROBE_ENABLED", "0")
    rows = propose_fact_probe_steps(
        contract={"required_facts": ["Find phone number"]},
        request_message="Find phone and send summary",
        target_url="https://example.com",
        existing_steps=[],
        allowed_tool_ids=["browser.playwright.inspect"],
    )
    assert rows == []


def test_propose_fact_probe_steps_parses_and_filters(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_FACT_PROBE_ENABLED", "1")
    monkeypatch.setattr(
        llm_contracts,
        "call_json_response",
        lambda **kwargs: {
            "steps": [
                {
                    "tool_id": "browser.playwright.inspect",
                    "title": "Inspect contact page for phone number",
                    "params": {"url": "https://example.com/contact"},
                },
                {"tool_id": "unknown.tool", "title": "ignore", "params": {}},
                "bad",
            ]
        },
    )
    rows = propose_fact_probe_steps(
        contract={"required_facts": ["Find phone number"]},
        request_message="Find phone and send summary",
        target_url="https://example.com",
        existing_steps=[{"tool_id": "marketing.web_research", "title": "Research", "params": {"query": "x"}}],
        allowed_tool_ids=["browser.playwright.inspect", "marketing.web_research"],
    )
    assert rows == [
        {
            "tool_id": "browser.playwright.inspect",
            "title": "Inspect contact page for phone number",
            "params": {"url": "https://example.com/contact"},
        }
    ]
