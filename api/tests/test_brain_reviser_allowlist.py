from __future__ import annotations

from types import SimpleNamespace

from api.services.agent.brain.brain import Brain
from api.services.agent.brain import reviser
from api.services.agent.brain.state import ActionCoverage, BrainState, FactCoverage


def _build_state() -> BrainState:
    return BrainState(
        turn_id="turn-1",
        user_id="tenant-1",
        conversation_id="conv-1",
        user_message="Research machine learning and email a summary.",
        task_intelligence=type("TI", (), {"objective": "Research machine learning and send email"})(),
        task_contract={"required_facts": ["current machine learning overview"]},
        original_plan=[],
        fact_coverage=FactCoverage(required_facts=["current machine learning overview"]),
        action_coverage=ActionCoverage(required_actions=[]),
    )


def test_build_revision_steps_filters_to_allowed_tools(monkeypatch) -> None:
    state = _build_state()
    state.evidence_pool = ["[marketing.web_research] partial findings only"]

    monkeypatch.setattr(
        reviser,
        "call_json_response",
        lambda **kwargs: [
            {
                "tool_id": "data.science.profile",
                "title": "Profile the dataset",
                "params": {},
                "why_this_step": "Check structured trend data",
                "expected_evidence": ["profile output"],
            },
            {
                "tool_id": "web.extract.structured",
                "title": "Extract page evidence",
                "params": {"url": "https://example.com"},
                "why_this_step": "Collect cited evidence",
                "expected_evidence": ["page evidence"],
            },
        ],
    )

    steps = reviser.build_revision_steps(
        state=state,
        registry=object(),
        allowed_tool_ids=["marketing.web_research", "web.extract.structured"],
    )

    assert [step.tool_id for step in steps] == ["web.extract.structured"]


def test_brain_allowed_tool_ids_suppress_live_inspection_for_standard_web_only() -> None:
    state = _build_state()
    state._allowed_tool_ids = [
        "marketing.web_research",
        "web.extract.structured",
        "browser.playwright.inspect",
        "documents.highlight.extract",
    ]
    state.execution_context = SimpleNamespace(
        settings={
            "__research_depth_tier": "standard",
            "__research_web_only": True,
            "__task_target_url": "",
        }
    )
    brain = Brain(state=state, registry=object())
    assert brain._allowed_tool_ids() == {"marketing.web_research", "web.extract.structured"}
