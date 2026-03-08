from api.services.agent import llm_contracts
from api.services.agent import contract_verification
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
    assert "Target website URL" not in row["missing_requirements"]
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
    assert "Need target website URL" not in row["missing_requirements"]
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


def test_build_task_contract_classifier_flags_missing_recipient(monkeypatch) -> None:
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
    assert "Preferred output format or artifact type" not in row["missing_requirements"]


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
    assert "Preferred output format or artifact type" not in row["missing_requirements"]


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


def test_build_task_contract_prunes_inferred_required_facts_outside_user_scope(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_TASK_CONTRACT_ENABLED", "1")
    monkeypatch.setenv("MAIA_AGENT_LLM_REQUIRED_FACT_FILTER_ENABLED", "0")
    monkeypatch.setattr(
        llm_contracts,
        "call_json_response",
        lambda **kwargs: {
            "objective": "Analyze website and deliver report",
            "required_outputs": ["Website analysis report"],
            "required_facts": ["site performance", "user experience", "content quality"],
            "required_actions": ["send_email"],
            "constraints": [],
            "delivery_target": "ops@example.com",
            "missing_requirements": [],
            "success_checks": ["Report sent"],
        },
    )
    row = build_task_contract(
        message='analysis https://axongroup.com/ and send a report to "ops@example.com"',
        agent_goal=None,
        rewritten_task=(
            "Conduct a comprehensive analysis of the website and include site performance, "
            "user experience, content quality, and potential areas for improvement in the report."
        ),
        deliverables=[],
        constraints=[],
        intent_tags=["web_research", "report_generation", "email_delivery"],
        conversation_summary="",
    )
    assert row["required_facts"] == []
    assert "Required facts to verify in the final answer" not in row["missing_requirements"]


def test_build_task_contract_drops_generic_report_fact_for_email_delivery(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_TASK_CONTRACT_ENABLED", "1")
    monkeypatch.setenv("MAIA_AGENT_LLM_REQUIRED_FACT_FILTER_ENABLED", "1")

    def _fake_call_json_response(**kwargs):
        prompt = str(kwargs.get("user_prompt") or "")
        if "Build a strict task contract" in prompt:
            return {
                "objective": 'analysis https://axongroup.com/ and send a report to "ops@example.com"',
                "required_outputs": ["Comprehensive analysis report of https://axongroup.com/"],
                "required_facts": ["Key insights from the analysis of https://axongroup.com/"],
                "required_actions": ["send_email"],
                "constraints": [],
                "delivery_target": "ops@example.com",
                "missing_requirements": [],
                "success_checks": ["Report sent"],
            }
        if "filter task-contract required facts" in prompt:
            return {"keep_indexes": [0], "reason": "placeholder fact retained"}
        return {}

    monkeypatch.setattr(llm_contracts, "call_json_response", _fake_call_json_response)

    row = build_task_contract(
        message='analysis https://axongroup.com/ and send a report to "ops@example.com"',
        agent_goal=None,
        rewritten_task='analysis https://axongroup.com/ and send a report to "ops@example.com"',
        deliverables=[],
        constraints=[],
        intent_tags=["web_research", "report_generation", "email_delivery"],
        conversation_summary="",
    )
    assert row["required_facts"] == []


def test_build_task_contract_drops_generic_fact_without_url_for_report_email(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_TASK_CONTRACT_ENABLED", "1")
    monkeypatch.setenv("MAIA_AGENT_LLM_REQUIRED_FACT_FILTER_ENABLED", "1")

    def _fake_call_json_response(**kwargs):
        prompt = str(kwargs.get("user_prompt") or "")
        if "Build a strict task contract" in prompt:
            return {
                "objective": 'analysis https://axongroup.com/ and send a report to "ops@example.com"',
                "required_outputs": ["Comprehensive analysis report of https://axongroup.com/"],
                "required_facts": ["website content analysis"],
                "required_actions": ["send_email"],
                "constraints": [],
                "delivery_target": "ops@example.com",
                "missing_requirements": [],
                "success_checks": ["Report sent"],
            }
        if "filter task-contract required facts" in prompt:
            return {"keep_indexes": [0], "reason": "retained"}
        return {}

    monkeypatch.setattr(llm_contracts, "call_json_response", _fake_call_json_response)

    row = build_task_contract(
        message='analysis https://axongroup.com/ and send a report to "ops@example.com"',
        agent_goal=None,
        rewritten_task='analysis https://axongroup.com/ and send a report to "ops@example.com"',
        deliverables=[],
        constraints=[],
        intent_tags=["web_research", "report_generation", "email_delivery"],
        conversation_summary="",
    )
    assert row["required_facts"] == []


def test_build_task_contract_sanitizes_missing_items_already_provided_in_goal(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_TASK_CONTRACT_ENABLED", "1")
    monkeypatch.setattr(
        llm_contracts,
        "call_json_response",
        lambda **kwargs: {
            "objective": "Research and implementation plan",
            "required_outputs": [],
            "required_facts": ["Core findings for implementation plan"],
            "required_actions": ["create_document", "update_sheet"],
            "constraints": [],
            "delivery_target": "",
            "missing_requirements": [
                "Recipient for the findings: this chat thread only",
                "Target format for the implementation plan: markdown",
            ],
            "success_checks": ["Plan includes prioritized backlog"],
        },
    )
    row = build_task_contract(
        message="Research agent architectures.",
        agent_goal=(
            "Recipient for the findings: this chat thread only. "
            "Target format for the implementation plan: markdown."
        ),
        rewritten_task="Research and propose implementation plan.",
        deliverables=[],
        constraints=[],
        intent_tags=["report_generation", "docs_write", "sheets_update"],
        conversation_summary="",
    )
    assert row["delivery_target"] == "this chat thread only"
    assert row["missing_requirements"] == []


def test_build_task_contract_sanitizes_live_thread_and_workspace_format_missing_items(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_TASK_CONTRACT_ENABLED", "1")
    monkeypatch.setattr(
        llm_contracts,
        "call_json_response",
        lambda **kwargs: {
            "objective": "Research agent workflows and track progress",
            "required_outputs": ["Research notes", "Task tracker updates"],
            "required_facts": ["Comparison of Codex, Cursor, and ChatGPT Agent"],
            "required_actions": ["create_document", "update_sheet"],
            "constraints": [],
            "delivery_target": "",
            "missing_requirements": [
                "Recipient for the live thread updates",
                "Output format specifications for Google Sheets and Google Doc",
            ],
            "success_checks": ["Research is complete"],
        },
    )
    row = build_task_contract(
        message=(
            "Research Codex, Cursor, and ChatGPT Agent; track steps in Google Sheets; "
            "write findings in Google Doc; show all progress in the live thread."
        ),
        agent_goal="Run end-to-end research with visible in-thread updates.",
        rewritten_task="Benchmark agent workflows and produce implementation recommendations.",
        deliverables=[],
        constraints=[],
        intent_tags=["web_research", "report_generation", "docs_write", "sheets_update"],
        conversation_summary="",
    )
    assert row["missing_requirements"] == []
