from types import SimpleNamespace

from api.schemas import ChatRequest
from api.services.agent.orchestration.app_runtime_helpers import (
    build_execution_context_settings,
)


def _plan_prep() -> SimpleNamespace:
    return SimpleNamespace(
        planned_search_terms=["ga4 report"],
        planned_keywords=["ga4", "sessions"],
        highlight_color="yellow",
        role_owned_steps=[],
    )


def _task_prep() -> SimpleNamespace:
    return SimpleNamespace(
        user_preferences={},
        research_depth_profile={},
        rewritten_task="Generate GA4 report",
        planned_deliverables=[],
        planned_constraints=[],
        task_contract={},
        contract_success_checks=[],
        contract_missing_requirements=[],
        clarification_questions=[],
        contract_missing_slots=[],
        clarification_blocked=False,
        session_context_snippets=[],
        memory_context_snippets=[],
        working_context={},
        task_intelligence=SimpleNamespace(
            preferred_tone="",
            preferred_format="",
            intent_tags=("report_generation",),
            target_url="",
        ),
    )


def test_build_execution_context_settings_resets_run_local_artifacts() -> None:
    request = ChatRequest(message="Generate GA4 report", agent_mode="company_agent")
    settings = {
        "__latest_report_title": "Old report",
        "__latest_report_content": "old body",
        "__latest_web_sources": [{"url": "https://example.com"}],
        "__latest_analytics_full_report": {"property_id": "old"},
        "__web_kpi": {"web_steps_total": 4},
        "__web_evidence": {"items": [{"id": "old"}]},
    }

    runtime = build_execution_context_settings(
        request=request,
        settings=settings,
        run_id="run-1",
        user_id="user-1",
        plan_prep=_plan_prep(),
        task_prep=_task_prep(),
        role_dispatch_plan=[],
    )

    assert runtime["__latest_report_title"] == ""
    assert runtime["__latest_report_content"] == ""
    assert runtime["__latest_web_sources"] == []
    assert runtime["__latest_analytics_full_report"] == {}
    assert runtime["__web_kpi"] == {}
    assert runtime["__web_evidence"] == {"items": []}
