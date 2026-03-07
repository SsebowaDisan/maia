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


def test_build_task_contract_sanitizes_google_doc_recipient_missing_item(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_TASK_CONTRACT_ENABLED", "1")
    monkeypatch.setattr(
        llm_contracts,
        "call_json_response",
        lambda **kwargs: {
            "objective": "Write findings to Google Doc",
            "required_outputs": ["Google Doc notes"],
            "required_facts": ["Comparison findings"],
            "required_actions": ["create_document"],
            "constraints": [],
            "delivery_target": "",
            "missing_requirements": ["Recipient for the Google Doc"],
            "success_checks": ["Notes captured"],
        },
    )
    row = build_task_contract(
        message="Write research findings into a Google Doc and share progress in this thread.",
        agent_goal="Document findings in Google Docs.",
        rewritten_task="Create and populate a Google Doc with research findings.",
        deliverables=[],
        constraints=[],
        intent_tags=["docs_write", "report_generation"],
        conversation_summary="",
    )
    assert row["missing_requirements"] == []


def test_build_task_contract_sanitizes_generic_output_format_for_defaultable_outputs(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_TASK_CONTRACT_ENABLED", "1")
    monkeypatch.setattr(
        llm_contracts,
        "call_json_response",
        lambda **kwargs: {
            "objective": "Research and summarize findings",
            "required_outputs": ["Research notes"],
            "required_facts": ["Key workflow differences"],
            "required_actions": ["create_document", "update_sheet"],
            "constraints": [],
            "delivery_target": "",
            "missing_requirements": ["Output format for findings"],
            "success_checks": ["Findings documented"],
        },
    )
    row = build_task_contract(
        message=(
            "Research Codex, Cursor, and ChatGPT Agent. "
            "Track each step in Google Sheets and write findings in a Google Doc."
        ),
        agent_goal="Show progress in-thread and provide implementation recommendations.",
        rewritten_task="Run benchmark and capture notes in workspace artifacts.",
        deliverables=[],
        constraints=[],
        intent_tags=["web_research", "report_generation", "docs_write", "sheets_update"],
        conversation_summary="",
    )
    assert row["missing_requirements"] == []


def test_build_task_contract_keeps_email_recipient_requirement_for_non_email_target(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_TASK_CONTRACT_ENABLED", "1")
    monkeypatch.setattr(
        llm_contracts,
        "call_json_response",
        lambda **kwargs: {
            "objective": "Email summary to leadership",
            "required_outputs": ["Summary email"],
            "required_facts": ["Verified findings"],
            "required_actions": ["send_email"],
            "constraints": [],
            "delivery_target": "product leadership team",
            "missing_requirements": ["Recipient email address for delivery"],
            "success_checks": ["Delivery completed"],
        },
    )
    row = build_task_contract(
        message="Prepare delivery to leadership.",
        agent_goal="Recipient: product leadership team",
        rewritten_task="Email findings to leadership",
        deliverables=[],
        constraints=[],
        intent_tags=["email_delivery", "report_generation"],
        conversation_summary="",
    )
    assert row["delivery_target"] == "product leadership team"
    assert "Recipient email address for delivery" in row["missing_requirements"]


def test_build_task_contract_ignores_target_url_when_not_required(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_TASK_CONTRACT_ENABLED", "1")
    monkeypatch.setattr(
        llm_contracts,
        "call_json_response",
        lambda **kwargs: {
            "objective": "Agent benchmark report",
            "required_outputs": ["Research report"],
            "required_facts": ["Key architectural differences"],
            "required_actions": ["create_document"],
            "constraints": [],
            "delivery_target": "",
            "missing_requirements": ["Target URL for research"],
            "success_checks": ["Report completed"],
        },
    )
    row = build_task_contract(
        message="Research agent architectures and summarize recommendations.",
        agent_goal="Return findings in this chat.",
        rewritten_task="Run a broad benchmark and summarize outcomes.",
        deliverables=[],
        constraints=[],
        intent_tags=["web_research", "report_generation", "docs_write"],
        conversation_summary="",
    )
    assert "Target URL for research" not in row["missing_requirements"]


def test_build_task_contract_ignores_email_recipient_requirement_for_website_outreach(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_TASK_CONTRACT_ENABLED", "1")
    monkeypatch.setattr(
        llm_contracts,
        "call_json_response",
        lambda **kwargs: {
            "objective": "Analyze site and contact company",
            "required_outputs": ["Website analysis summary"],
            "required_facts": ["Services offered", "Office hours"],
            "required_actions": ["send_email"],
            "constraints": [],
            "delivery_target": "",
            "missing_requirements": ["Recipient email address for delivery"],
            "success_checks": ["Message sent"],
        },
    )
    row = build_task_contract(
        message=(
            "Analyze https://axongroup.com/ and send them a message asking about their services and office hours."
        ),
        agent_goal=None,
        rewritten_task="Analyze the website and send a message to the company.",
        deliverables=[],
        constraints=[],
        intent_tags=["web_research", "contact_form_submission"],
        conversation_summary="",
    )
    assert row["missing_requirements"] == []


def test_build_task_contract_keeps_actionable_llm_missing_requirement_for_contact_form(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_TASK_CONTRACT_ENABLED", "1")
    monkeypatch.setattr(
        llm_contracts,
        "call_json_response",
        lambda **kwargs: {
            "objective": "Analyze site and submit contact form",
            "required_outputs": ["Website analysis summary"],
            "required_facts": ["Services offered"],
            "required_actions": ["submit_contact_form"],
            "constraints": [],
            "delivery_target": "",
            "missing_requirements": ["Provide sender identity details required for outreach form submission"],
            "success_checks": ["Contact request submitted"],
        },
    )
    row = build_task_contract(
        message=(
            "Analyze https://axongroup.com/ and send them a message asking about their services and office hours."
        ),
        agent_goal=None,
        rewritten_task="Analyze website and send an outreach message.",
        deliverables=[],
        constraints=[],
        intent_tags=["web_research", "contact_form_submission"],
        conversation_summary="",
    )
    assert "Provide sender identity details required for outreach form submission" in row["missing_requirements"]


def test_build_task_contract_maps_post_message_to_contact_form_action(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_TASK_CONTRACT_ENABLED", "1")
    monkeypatch.setattr(
        llm_contracts,
        "call_json_response",
        lambda **kwargs: {
            "objective": "Analyze site and send outreach message",
            "required_outputs": ["Website analysis summary"],
            "required_facts": ["Products and services overview"],
            "required_actions": ["post_message"],
            "constraints": [],
            "delivery_target": "",
            "missing_requirements": [],
            "success_checks": ["Outreach completed"],
        },
    )
    row = build_task_contract(
        message="Analyze https://axongroup.com/ and send a message via their contact form.",
        agent_goal=None,
        rewritten_task="Analyze website and contact the company.",
        deliverables=[],
        constraints=[],
        intent_tags=["web_research", "contact_form_submission"],
        conversation_summary="",
    )
    assert "submit_contact_form" in row["required_actions"]
    assert "post_message" not in row["required_actions"]


def test_build_task_contract_reconciles_missing_contact_action_with_llm(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_TASK_CONTRACT_ENABLED", "1")
    monkeypatch.setenv("MAIA_AGENT_LLM_MISSING_ALIGNMENT_ENABLED", "0")
    monkeypatch.setenv("MAIA_AGENT_LLM_MISSING_PRUNE_ENABLED", "0")
    monkeypatch.setenv("MAIA_AGENT_LLM_REQUIRED_FACT_FILTER_ENABLED", "0")

    def _fake_call_json_response(**kwargs):
        prompt = " ".join(
            [
                str(kwargs.get("system_prompt") or ""),
                str(kwargs.get("user_prompt") or ""),
            ]
        )
        if "Build a strict task contract" in prompt:
            return {
                "objective": "Analyze website and send outreach message",
                "required_outputs": [],
                "required_facts": [],
                "required_actions": [],
                "constraints": [],
                "delivery_target": "",
                "missing_requirements": [],
                "success_checks": ["Outreach completed"],
            }
        if "validate required execution actions" in prompt.lower():
            return {"required_actions": ["submit_contact_form"], "reason": "website outreach requested"}
        return {}

    monkeypatch.setattr(llm_contracts, "call_json_response", _fake_call_json_response)

    row = build_task_contract(
        message="Analyze https://axongroup.com/ and send a message through the website inquiry form.",
        agent_goal=None,
        rewritten_task="Analyze website and contact the company.",
        deliverables=[],
        constraints=[],
        intent_tags=["web_research"],
        conversation_summary="",
    )

    assert "submit_contact_form" in row["required_actions"]


def test_build_task_contract_filters_delivery_slot_from_required_facts(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_TASK_CONTRACT_ENABLED", "1")
    monkeypatch.setenv("MAIA_AGENT_LLM_MISSING_ALIGNMENT_ENABLED", "0")
    monkeypatch.setenv("MAIA_AGENT_LLM_MISSING_PRUNE_ENABLED", "0")
    monkeypatch.setenv("MAIA_AGENT_LLM_ACTION_RECONCILE_ENABLED", "0")

    def _fake_call_json_response(**kwargs):
        prompt = str(kwargs.get("user_prompt") or "")
        if "Build a strict task contract" in prompt:
            return {
                "objective": "Find headquarters and email summary",
                "required_outputs": ["Summary email"],
                "required_facts": [
                    "Recipient email address: ops@example.com",
                    "Headquarters city and country",
                ],
                "required_actions": ["send_email"],
                "constraints": [],
                "delivery_target": "ops@example.com",
                "missing_requirements": [],
                "success_checks": ["Delivered"],
            }
        if "filter task-contract required facts" in prompt:
            return {"keep_indexes": [1], "reason": "Only headquarters fact is evidence-bearing."}
        return {}

    monkeypatch.setattr(llm_contracts, "call_json_response", _fake_call_json_response)

    row = build_task_contract(
        message=(
            "Analyze https://example.com, include headquarters city and country, "
            "and send the summary to ops@example.com."
        ),
        agent_goal=None,
        rewritten_task="Find headquarters and send summary email.",
        deliverables=[],
        constraints=[],
        intent_tags=["web_research", "email_delivery", "report_generation"],
        conversation_summary="",
    )

    assert row["required_facts"] == ["Headquarters city and country"]


def test_build_task_contract_drops_send_email_for_contact_form_when_email_tag_is_false_positive(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_TASK_CONTRACT_ENABLED", "0")
    row = build_task_contract(
        message=(
            "Analyze https://axongroup.com/ and send a message via their contact form "
            "asking about products and services."
        ),
        agent_goal=None,
        rewritten_task="",
        deliverables=[],
        constraints=[],
        intent_tags=["web_research", "contact_form_submission", "email_delivery"],
        conversation_summary="",
    )
    assert "submit_contact_form" in row["required_actions"]
    assert "send_email" not in row["required_actions"]
    assert "Recipient email address for delivery" not in row["missing_requirements"]


def test_build_task_contract_keeps_send_email_when_delivery_target_is_present(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_TASK_CONTRACT_ENABLED", "0")
    row = build_task_contract(
        message=(
            "Analyze https://axongroup.com/, send a message via their contact form, "
            "and send delivery confirmation to ops@example.com."
        ),
        agent_goal=None,
        rewritten_task="",
        deliverables=[],
        constraints=[],
        intent_tags=["web_research", "contact_form_submission", "email_delivery"],
        conversation_summary="",
    )
    assert "send_email" in row["required_actions"]
    assert "submit_contact_form" in row["required_actions"]
    assert "Recipient email address for delivery" not in row["missing_requirements"]


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
