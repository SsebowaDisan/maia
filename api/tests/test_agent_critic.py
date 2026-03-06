from __future__ import annotations

from api.services.agent import critic
from api.services.agent.critic import review_final_answer


def test_critic_suppresses_false_action_gap_when_external_action_succeeded(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_CRITIC_ENABLED", "1")
    monkeypatch.setattr(
        critic,
        "call_text_response",
        lambda **kwargs: "Lack of Action: the message action was not completed.",
    )
    row = review_final_answer(
        request_message="Send message via contact form",
        answer_text="Completed submission.",
        source_urls=["https://example.com"],
        actions=[
            {
                "tool_id": "browser.contact_form.send",
                "status": "success",
                "action_class": "execute",
                "summary": "Submitted contact form successfully.",
            }
        ],
        contract_check={
            "ready_for_final_response": True,
            "ready_for_external_actions": True,
            "missing_items": [],
        },
    )
    assert row["needs_human_review"] is False
    assert row["critic_note"] == ""


def test_critic_keeps_action_gap_when_required_action_missing(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_CRITIC_ENABLED", "1")
    monkeypatch.setattr(
        critic,
        "call_text_response",
        lambda **kwargs: "Lack of Action: required message action was not completed.",
    )
    row = review_final_answer(
        request_message="Send message via contact form",
        answer_text="No submission was completed.",
        source_urls=["https://example.com"],
        actions=[],
        contract_check={
            "ready_for_final_response": False,
            "ready_for_external_actions": False,
            "missing_items": ["Required action not completed: submit_contact_form"],
        },
    )
    assert row["needs_human_review"] is True
    assert "Lack of Action" in row["critic_note"]


def test_critic_suppresses_attempt_vs_completion_contradiction_when_attempt_failed(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_CRITIC_ENABLED", "1")
    monkeypatch.setattr(
        critic,
        "call_text_response",
        lambda **kwargs: (
            "Lack of Action: action marked not completed but browser.contact_form.send was used, "
            "which implies an attempt was made."
        ),
    )
    row = review_final_answer(
        request_message="Send message via contact form",
        answer_text=(
            "External action was not completed. The agent attempted submission via browser.contact_form.send "
            "but failed because a required phone field was missing."
        ),
        source_urls=["https://example.com"],
        actions=[
            {
                "tool_id": "browser.contact_form.send",
                "status": "failed",
                "action_class": "execute",
                "summary": "Submission failed: telephone number is required.",
            }
        ],
        contract_check={
            "ready_for_final_response": False,
            "ready_for_external_actions": False,
            "missing_items": ["Required action not completed: submit_contact_form"],
        },
    )
    assert row["needs_human_review"] is False
    assert row["critic_note"] == ""
