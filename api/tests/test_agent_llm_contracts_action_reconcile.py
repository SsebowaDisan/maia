from __future__ import annotations

from api.services.agent import llm_contracts_helpers
from api.services.agent.llm_contracts import build_task_contract


def test_reconcile_required_actions_strips_post_message_without_chat_delivery_scope(monkeypatch) -> None:
    monkeypatch.setattr(llm_contracts_helpers, "env_bool", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        llm_contracts_helpers,
        "call_json_response",
        lambda **kwargs: {"required_actions": ["send_email", "post_message"], "reason": "llm"},
    )

    actions = llm_contracts_helpers.reconcile_required_actions_with_llm(
        message="Make the research about machine learning and write an email about the research to ssebowadisan1@gmail.com",
        agent_goal="Research machine learning and email the findings",
        rewritten_task="Research machine learning and email the findings to ssebowadisan1@gmail.com",
        required_actions=["send_email"],
        intent_tags=["web_research", "report_generation", "email_delivery"],
        delivery_target="ssebowadisan1@gmail.com",
        target_url="",
    )

    assert actions == ["send_email"]


def test_reconcile_required_actions_keeps_post_message_for_explicit_channel_request(monkeypatch) -> None:
    monkeypatch.setattr(llm_contracts_helpers, "env_bool", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        llm_contracts_helpers,
        "call_json_response",
        lambda **kwargs: {"required_actions": ["post_message"], "reason": "llm"},
    )

    actions = llm_contracts_helpers.reconcile_required_actions_with_llm(
        message="Post the final summary to the Slack channel",
        agent_goal="Share the summary in Slack",
        rewritten_task="Post the final summary to the Slack channel once complete",
        required_actions=[],
        intent_tags=["report_generation"],
        delivery_target="",
        target_url="",
    )

    assert actions == ["post_message"]


def test_reconcile_required_actions_strips_send_email_for_draft_only_scope(monkeypatch) -> None:
    monkeypatch.setattr(llm_contracts_helpers, "env_bool", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        llm_contracts_helpers,
        "call_json_response",
        lambda **kwargs: {"required_actions": ["send_email"], "reason": "llm"},
    )

    actions = llm_contracts_helpers.reconcile_required_actions_with_llm(
        message="make the research about machine learning and write an email about the research to ssebowadisan1@gmail.com",
        agent_goal="Synthesize research findings into a concise, client-ready email draft addressed to ssebowadisan1@gmail.com",
        rewritten_task="Write a polished, citation-rich email about machine learning for ssebowadisan1@gmail.com. Do not send the email.",
        required_actions=["send_email"],
        intent_tags=["docs_write", "email_delivery"],
        delivery_target="ssebowadisan1@gmail.com",
        target_url="",
    )

    assert actions == []


def test_build_task_contract_keeps_email_draft_step_as_draft_only(monkeypatch) -> None:
    monkeypatch.setattr("api.services.agent.llm_contracts.env_bool", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        "api.services.agent.llm_contracts.call_json_response",
        lambda **kwargs: {
            "objective": "Synthesize research findings into a concise, client-ready email draft addressed to ssebowadisan1@gmail.com",
            "required_outputs": ["Email draft with inline citations"],
            "required_facts": ["Three source-backed machine learning takeaways with inline citations"],
            "required_actions": ["send_email"],
            "constraints": [],
            "delivery_target": "ssebowadisan1@gmail.com",
            "missing_requirements": [],
            "success_checks": ["Draft is ready"],
        },
    )

    contract = build_task_contract(
        message="make the research about machine learning and write an email about the research to ssebowadisan1@gmail.com",
        agent_goal="Synthesize research findings into a concise, client-ready email draft addressed to ssebowadisan1@gmail.com",
        rewritten_task="Write a polished, citation-rich email about machine learning for ssebowadisan1@gmail.com. Do not send the email.",
        deliverables=["Email draft with inline citations"],
        constraints=[],
        intent_tags=["docs_write", "email_delivery"],
        conversation_summary="",
    )

    assert contract["required_actions"] == []
    assert contract["delivery_target"] == "ssebowadisan1@gmail.com"


def test_build_task_contract_keeps_email_dispatch_step_as_draft_only(monkeypatch) -> None:
    monkeypatch.setattr("api.services.agent.llm_contracts.env_bool", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        "api.services.agent.llm_contracts.call_json_response",
        lambda **kwargs: {
            "objective": "Compose the final premium email draft",
            "required_outputs": ["Email draft with inline citations"],
            "required_facts": ["Three source-backed machine learning takeaways with inline citations"],
            "required_actions": ["send_email"],
            "constraints": [],
            "delivery_target": "ssebowadisan1@gmail.com",
            "missing_requirements": [],
            "success_checks": ["Draft is ready"],
        },
    )

    contract = build_task_contract(
        message="make the research about machine learning and write an email about the research to ssebowadisan1@gmail.com",
        agent_goal="Compose a polished, citation-rich email draft addressed to ssebowadisan1@gmail.com",
        rewritten_task="Compose a polished, citation-rich email draft for ssebowadisan1@gmail.com. This stage drafts only; do not dispatch the email.",
        deliverables=["Email draft with inline citations"],
        constraints=[],
        intent_tags=["docs_write", "email_delivery"],
        conversation_summary="",
    )

    assert contract["required_actions"] == []
    assert contract["delivery_target"] == "ssebowadisan1@gmail.com"
