from api.services.agent import llm_contracts
from api.services.agent import contract_verification
from api.services.agent.llm_contracts import (
    NO_HARDCODE_WORDS_CONSTRAINT,
    build_task_contract,
    propose_fact_probe_steps,
    verify_task_contract_fulfillment,
)



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


