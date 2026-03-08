from api.services.agent import llm_contracts
from api.services.agent import contract_verification
from api.services.agent.llm_contracts import (
    NO_HARDCODE_WORDS_CONSTRAINT,
    build_task_contract,
    propose_fact_probe_steps,
    verify_task_contract_fulfillment,
)

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


def test_verify_task_contract_pre_send_gate_skips_fact_blockers_for_pending_send_action(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_DELIVERY_CHECK_ENABLED", "1")
    monkeypatch.setenv("MAIA_AGENT_LLM_FACT_SLOT_FILTER_ENABLED", "0")
    monkeypatch.setenv("MAIA_AGENT_LLM_FACT_COVERAGE_CHECK_ENABLED", "0")
    row = verify_task_contract_fulfillment(
        contract={
            "objective": "Analyze website and send report",
            "required_facts": ["website content analysis"],
            "required_actions": ["send_email"],
            "delivery_target": "ops@example.com",
        },
        request_message='analysis https://example.com and send a report to "ops@example.com"',
        executed_steps=[
            {
                "tool_id": "browser.playwright.inspect",
                "status": "success",
                "title": "Inspect website",
                "summary": "Collected page evidence from the target domain.",
            }
        ],
        actions=[{"tool_id": "gmail.draft", "status": "success", "summary": "draft created"}],
        report_body="Website findings report prepared.",
        sources=[{"url": "https://example.com", "label": "Example"}],
        allowed_tool_ids=["gmail.draft", "gmail.send", "mailer.report_send"],
        pending_action_tool_id="mailer.report_send",
    )
    assert row["ready_for_final_response"] is True
    assert row["ready_for_external_actions"] is True
    assert row["missing_items"] == []


def test_verify_task_contract_ignores_delivery_slot_rows_from_required_facts(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_DELIVERY_CHECK_ENABLED", "0")
    monkeypatch.setenv("MAIA_AGENT_LLM_FACT_SLOT_FILTER_ENABLED", "0")
    row = verify_task_contract_fulfillment(
        contract={
            "objective": "Email summary",
            "required_facts": ["Recipient email address: ops@example.com"],
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
        contract={"objective": "Location + delivery", "required_facts": ["Company address"]},
        request_message="Analyze and send",
        executed_steps=[{"tool_id": "browser.playwright.inspect", "status": "success"}],
        actions=[],
        report_body="Findings",
        sources=[{"url": "https://example.com"}],
        allowed_tool_ids=["docs.create", "workspace.docs.research_notes"],
    )
    assert row["ready_for_final_response"] is False
    assert row["ready_for_external_actions"] is False
    assert row["missing_items"] == ["Unverified required fact: Company address"]
    assert row["recommended_remediation"] == [
        {"tool_id": "docs.create", "title": "Draft location note", "params": {"title": "Location Brief"}}
    ]


def test_verify_task_contract_ignores_non_actionable_llm_block_when_deterministic_ready(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_DELIVERY_CHECK_ENABLED", "1")
    monkeypatch.setattr(
        llm_contracts,
        "call_json_response",
        lambda **kwargs: {
            "ready_for_final_response": False,
            "ready_for_external_actions": False,
            "missing_items": [],
            "reason": "Need a broader synthesis before final response.",
            "recommended_remediation": [],
        },
    )
    row = verify_task_contract_fulfillment(
        contract={"objective": "Summarize findings", "required_facts": [], "required_actions": []},
        request_message="Summarize findings in this chat.",
        executed_steps=[{"tool_id": "docs.create", "status": "success", "summary": "Drafted summary."}],
        actions=[{"tool_id": "docs.create", "status": "success", "summary": "Drafted summary."}],
        report_body="Summary with supporting citations is ready.",
        sources=[{"url": "https://example.com", "label": "Example source"}],
        allowed_tool_ids=["docs.create"],
    )
    assert row["ready_for_final_response"] is True
    assert row["ready_for_external_actions"] is True
    assert row["missing_items"] == []


def test_verify_task_contract_semantic_fact_miss_requires_lexical_gap(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_DELIVERY_CHECK_ENABLED", "0")
    monkeypatch.setenv("MAIA_AGENT_LLM_FACT_SLOT_FILTER_ENABLED", "0")
    monkeypatch.setenv("MAIA_AGENT_LLM_FACT_COVERAGE_CHECK_ENABLED", "1")
    monkeypatch.setattr(
        contract_verification,
        "call_json_response",
        lambda **kwargs: {"missing_fact_indexes": [0], "reason": "false positive semantic miss"},
    )
    row = verify_task_contract_fulfillment(
        contract={
            "objective": "Research machine learning",
            "required_facts": ["Overview of machine learning"],
            "required_actions": [],
            "delivery_target": "",
        },
        request_message="make research about machine learning",
        executed_steps=[{"tool_id": "marketing.web_research", "status": "success", "summary": "Overview captured"}],
        actions=[],
        report_body=(
            "This report provides an overview of machine learning, including key concepts and "
            "practical adoption patterns."
        ),
        sources=[{"url": "https://example.com", "label": "Example source"}],
        allowed_tool_ids=["marketing.web_research", "browser.playwright.inspect"],
    )
    assert row["ready_for_final_response"] is True
    assert row["ready_for_external_actions"] is True
    assert row["missing_items"] == []


def test_verify_task_contract_keeps_actionable_llm_block_when_fact_gap_is_reported(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_DELIVERY_CHECK_ENABLED", "1")
    monkeypatch.setattr(
        llm_contracts,
        "call_json_response",
        lambda **kwargs: {
            "ready_for_final_response": False,
            "ready_for_external_actions": False,
            "missing_items": ["Unverified required fact: Headquarters city and country"],
            "reason": "Required fact not fully supported.",
            "recommended_remediation": [
                {
                    "tool_id": "marketing.web_research",
                    "title": "Recheck headquarters location",
                    "params": {"query": "company headquarters city country"},
                }
            ],
        },
    )
    row = verify_task_contract_fulfillment(
        contract={
            "objective": "Confirm headquarters",
            "required_facts": ["Headquarters city and country"],
            "required_actions": [],
        },
        request_message="Find the headquarters location.",
        executed_steps=[
            {
                "tool_id": "marketing.web_research",
                "status": "success",
                "summary": "Headquarters city and country details were captured.",
            }
        ],
        actions=[{"tool_id": "marketing.web_research", "status": "success", "summary": "Location captured"}],
        report_body="Headquarters city and country: Brussels, Belgium.",
        sources=[{"url": "https://example.com", "label": "Example source"}],
        allowed_tool_ids=["marketing.web_research", "browser.playwright.inspect"],
    )
    assert row["ready_for_final_response"] is False
    assert row["ready_for_external_actions"] is False
    assert row["missing_items"] == ["Unverified required fact: Headquarters city and country"]
    assert row["recommended_remediation"] == [
        {
            "tool_id": "marketing.web_research",
            "title": "Recheck headquarters location",
            "params": {"query": "company headquarters city country"},
        }
    ]


def test_verify_task_contract_sanitizes_out_of_contract_llm_missing_items(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_DELIVERY_CHECK_ENABLED", "1")
    monkeypatch.setenv("MAIA_AGENT_LLM_MISSING_ALIGNMENT_ENABLED", "0")
    monkeypatch.setattr(
        llm_contracts,
        "call_json_response",
        lambda **kwargs: {
            "ready_for_final_response": False,
            "ready_for_external_actions": False,
            "missing_items": ["recipient: ssebowadisan1@gmail.com"],
            "reason": "Mandatory requirement for recipient email address is missing.",
            "recommended_remediation": [],
        },
    )
    row = verify_task_contract_fulfillment(
        contract={
            "objective": "Research machine learning",
            "required_facts": ["Bayesian posterior uncertainty decomposition"],
            "required_actions": [],
            "delivery_target": "",
        },
        request_message="make research about machine learning",
        executed_steps=[],
        actions=[],
        report_body="",
        sources=[],
        allowed_tool_ids=["marketing.web_research", "browser.playwright.inspect"],
    )
    assert row["ready_for_final_response"] is False
    assert row["ready_for_external_actions"] is False
    assert row["missing_items"] == ["Unverified required fact: Bayesian posterior uncertainty decomposition"]


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


