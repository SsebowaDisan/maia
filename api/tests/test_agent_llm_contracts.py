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
    assert row["required_facts"] == []
    assert row["constraints"][0] == NO_HARDCODE_WORDS_CONSTRAINT
    assert row["missing_requirements"] == []
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
