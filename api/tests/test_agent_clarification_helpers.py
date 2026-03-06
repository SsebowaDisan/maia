from __future__ import annotations

from api.services.agent.orchestration.clarification_helpers import (
    questions_for_requirements,
    select_relevant_clarification_requirements,
)


def test_select_relevant_clarification_requirements_filters_unrelated_requirements() -> None:
    selected = select_relevant_clarification_requirements(
        deferred_missing_requirements=[
            "Recipient email address for delivery",
            "Provide sender company profile for outreach",
        ],
        contract_missing_items=["Required action not completed: submit_contact_form"],
    )
    assert selected == []


def test_select_relevant_clarification_requirements_keeps_related_requirements() -> None:
    selected = select_relevant_clarification_requirements(
        deferred_missing_requirements=[
            "Recipient email address for delivery",
            "Provide sender company profile for outreach",
        ],
        contract_missing_items=["Missing delivery target for required action: send_email"],
    )
    assert selected == ["Recipient email address for delivery"]


def test_questions_for_requirements_keeps_ordered_question_mapping() -> None:
    questions = questions_for_requirements(
        requirements=["Recipient email address for delivery"],
        all_requirements=[
            "Recipient email address for delivery",
            "Provide sender company profile for outreach",
        ],
        all_questions=[
            "Please provide: Recipient email address for delivery",
            "Please provide: Provide sender company profile for outreach",
        ],
    )
    assert questions == ["Please provide: Recipient email address for delivery"]

