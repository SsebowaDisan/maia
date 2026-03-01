from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.models import AgentActivityEvent
from api.services.agent.observability import get_agent_observability
from api.services.agent.planner import PlannedStep, build_plan

from ..models import PlanPreparation, TaskPreparation
from ..text_helpers import extract_first_email
from .contracts import (
    build_planning_request,
    collect_probe_allowed_tool_ids,
    insert_contract_probe_steps,
)
from .capability_planning import analyze_capability_plan
from .evidence import enforce_evidence_path, summarize_fact_coverage
from .events import (
    plan_capability_event,
    plan_candidate_event,
    plan_decompose_completed_event,
    plan_decompose_started_event,
    plan_fact_coverage_event,
    plan_ready_event,
    plan_refined_event,
    plan_step_event,
)
from .intent_enrichment import apply_intent_enrichment
from .research import (
    build_research_plan,
    ensure_company_agent_highlight_step,
    normalize_step_parameters,
)
from .workspace_logging import (
    build_workspace_logging_plan,
    prepend_workspace_roadmap_steps,
)


def build_execution_steps(
    *,
    request: ChatRequest,
    settings: dict[str, Any],
    task_prep: TaskPreparation,
    registry: Any,
    emit_event: Callable[[AgentActivityEvent], dict[str, Any]],
    activity_event_factory: Callable[..., AgentActivityEvent],
) -> Generator[dict[str, Any], None, PlanPreparation]:
    planning_request, planning_message = build_planning_request(
        request=request,
        task_prep=task_prep,
    )
    capability_analysis = analyze_capability_plan(
        request=request,
        task_prep=task_prep,
        registry=registry,
    )
    yield emit_event(
        plan_capability_event(
            activity_event_factory=activity_event_factory,
            required_domains=capability_analysis.required_domains,
            preferred_tool_ids=capability_analysis.preferred_tool_ids,
            matched_signals=capability_analysis.matched_signals,
            rationale=capability_analysis.rationale,
        )
    )

    yield emit_event(
        plan_decompose_started_event(
            activity_event_factory=activity_event_factory,
            task_prep=task_prep,
            planning_detail=planning_message,
            request_message=request.message,
        )
    )
    steps = build_plan(
        planning_request,
        preferred_tool_ids=set(capability_analysis.preferred_tool_ids),
    )
    yield emit_event(
        plan_decompose_completed_event(
            activity_event_factory=activity_event_factory,
            steps=steps,
        )
    )

    steps = apply_intent_enrichment(
        request=request,
        task_prep=task_prep,
        steps=steps,
    )

    research_plan = build_research_plan(request=request, settings=settings)
    steps = normalize_step_parameters(
        steps=steps,
        planned_search_terms=research_plan.planned_search_terms,
        planned_keywords=research_plan.planned_keywords,
        highlight_color=research_plan.highlight_color,
    )
    steps = ensure_company_agent_highlight_step(
        request=request,
        steps=steps,
        highlight_color=research_plan.highlight_color,
        planned_keywords=research_plan.planned_keywords,
    )

    probe_allowed_tool_ids = collect_probe_allowed_tool_ids(registry)
    steps = insert_contract_probe_steps(
        request=request,
        task_prep=task_prep,
        steps=steps,
        allowed_tool_ids=probe_allowed_tool_ids,
    )
    steps = enforce_evidence_path(
        request=request,
        task_prep=task_prep,
        steps=steps,
        highlight_color=research_plan.highlight_color,
    )
    fact_coverage = summarize_fact_coverage(
        contract_facts=task_prep.contract_facts,
        steps=steps,
    )
    yield emit_event(
        plan_fact_coverage_event(
            activity_event_factory=activity_event_factory,
            fact_coverage=fact_coverage,
        )
    )

    workspace_logging_plan = build_workspace_logging_plan(
        request=request,
        settings=settings,
        task_prep=task_prep,
        deep_research_mode=research_plan.deep_research_mode,
    )
    if (
        workspace_logging_plan.deep_workspace_logging_enabled
        and request.agent_mode == "company_agent"
    ):
        steps = prepend_workspace_roadmap_steps(
            request=request,
            task_prep=task_prep,
            steps=steps,
            planned_search_terms=research_plan.planned_search_terms,
            planned_keywords=research_plan.planned_keywords,
        )

    for idx, planned_step in enumerate(steps, start=1):
        yield emit_event(
            plan_step_event(
                activity_event_factory=activity_event_factory,
                step_number=idx,
                planned_step=planned_step,
            )
        )

    delivery_email = extract_first_email(request.message, request.agent_goal or "")
    yield emit_event(
        plan_candidate_event(
            activity_event_factory=activity_event_factory,
            steps=steps,
            task_prep=task_prep,
            request_message=request.message,
            delivery_email=delivery_email,
            workspace_logging_requested=workspace_logging_plan.workspace_logging_requested,
            planned_search_terms=research_plan.planned_search_terms,
            planned_keywords=research_plan.planned_keywords,
        )
    )
    yield emit_event(
        plan_refined_event(
            activity_event_factory=activity_event_factory,
            steps=steps,
            planned_search_terms=research_plan.planned_search_terms,
            planned_keywords=research_plan.planned_keywords,
            fact_coverage=fact_coverage,
        )
    )
    yield emit_event(plan_ready_event(activity_event_factory=activity_event_factory, steps=steps))
    get_agent_observability().observe_plan_steps(
        tool_ids=[item.tool_id for item in steps],
    )

    return PlanPreparation(
        steps=steps,
        deep_research_mode=research_plan.deep_research_mode,
        highlight_color=research_plan.highlight_color,
        planned_search_terms=research_plan.planned_search_terms,
        planned_keywords=research_plan.planned_keywords,
        workspace_logging_requested=workspace_logging_plan.workspace_logging_requested,
        deep_workspace_logging_enabled=workspace_logging_plan.deep_workspace_logging_enabled,
        delivery_email=delivery_email,
    )
