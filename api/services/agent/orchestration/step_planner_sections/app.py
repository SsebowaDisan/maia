from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.models import AgentActivityEvent
from api.services.agent.observability import get_agent_observability
from api.services.agent.planner import PlannedStep, build_plan, resolve_web_routing

from ..models import PlanPreparation, TaskPreparation
from ..role_router import build_role_owned_steps, role_owned_steps_to_payload
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
    plan_web_routing_event,
    plan_step_event,
)
from .intent_enrichment import apply_intent_enrichment
from .research import (
    build_research_plan,
    enforce_deep_file_scope_policy,
    enforce_web_only_research_path,
    ensure_company_agent_highlight_step,
    normalize_step_parameters,
)
from .workspace_logging import (
    build_workspace_logging_plan,
    prepend_workspace_roadmap_steps,
)


def _extract_available_tool_ids(registry: Any) -> set[str]:
    try:
        rows = registry.list_tools()
    except Exception:
        return set()
    available: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        tool_id = str(row.get("tool_id") or "").strip()
        if tool_id:
            available.add(tool_id)
    return available


def _filter_steps_by_available_tools(
    *,
    steps: list[PlannedStep],
    available_tool_ids: set[str],
) -> list[PlannedStep]:
    if not available_tool_ids:
        return list(steps)
    return [step for step in steps if step.tool_id in available_tool_ids]


def build_execution_steps(
    *,
    request: ChatRequest,
    settings: dict[str, Any],
    task_prep: TaskPreparation,
    registry: Any,
    emit_event: Callable[[AgentActivityEvent], dict[str, Any]],
    activity_event_factory: Callable[..., AgentActivityEvent],
) -> Generator[dict[str, Any], None, PlanPreparation]:
    available_tool_ids = _extract_available_tool_ids(registry)
    settings["__contact_form_capability_enabled"] = (
        "browser.contact_form.send" in available_tool_ids
    )
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
    settings["__capability_required_domains"] = list(capability_analysis.required_domains[:12])
    settings["__capability_preferred_tool_ids"] = list(
        capability_analysis.preferred_tool_ids[:24]
    )
    settings["__capability_matched_signals"] = list(capability_analysis.matched_signals[:24])

    yield emit_event(
        plan_decompose_started_event(
            activity_event_factory=activity_event_factory,
            task_prep=task_prep,
            planning_detail=planning_message,
            request_message=request.message,
        )
    )
    web_routing = resolve_web_routing(planning_request)
    yield emit_event(
        plan_web_routing_event(
            activity_event_factory=activity_event_factory,
            web_routing=web_routing,
        )
    )
    steps = build_plan(
        planning_request,
        preferred_tool_ids=set(capability_analysis.preferred_tool_ids),
        web_routing=web_routing,
    )
    steps = _filter_steps_by_available_tools(
        steps=steps,
        available_tool_ids=available_tool_ids,
    )
    yield emit_event(
        plan_decompose_completed_event(
            activity_event_factory=activity_event_factory,
            steps=steps,
        )
    )

    steps = apply_intent_enrichment(
        request=request,
        settings=settings,
        task_prep=task_prep,
        steps=steps,
    )

    research_plan = build_research_plan(request=request, settings=settings)
    settings["__research_depth_tier"] = research_plan.depth_tier
    settings["__research_max_query_variants"] = research_plan.max_query_variants
    settings["__research_results_per_query"] = research_plan.results_per_query
    settings["__research_fused_top_k"] = research_plan.fused_top_k
    settings["__research_max_live_inspections"] = research_plan.max_live_inspections
    settings["__research_min_unique_sources"] = research_plan.min_unique_sources
    settings["__research_web_search_budget"] = research_plan.web_search_budget
    settings["__file_research_max_sources"] = research_plan.max_file_sources
    settings["__file_research_max_chunks"] = research_plan.max_file_chunks
    settings["__file_research_max_scan_pages"] = research_plan.max_file_scan_pages
    settings["__simple_explanation_required"] = research_plan.simple_explanation_required
    steps = normalize_step_parameters(
        steps=steps,
        planned_search_terms=research_plan.planned_search_terms,
        planned_keywords=research_plan.planned_keywords,
        highlight_color=research_plan.highlight_color,
        research_plan=research_plan,
    )
    steps = enforce_web_only_research_path(
        request=request,
        settings=settings,
        steps=steps,
        research_plan=research_plan,
    )
    steps = ensure_company_agent_highlight_step(
        request=request,
        settings=settings,
        steps=steps,
        highlight_color=research_plan.highlight_color,
        planned_keywords=research_plan.planned_keywords,
    )
    steps = enforce_deep_file_scope_policy(
        request=request,
        settings=settings,
        steps=steps,
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

    role_owned_step_models = build_role_owned_steps(steps=steps)
    role_owned_steps = role_owned_steps_to_payload(steps=role_owned_step_models)

    for idx, planned_step in enumerate(steps, start=1):
        role_step = role_owned_step_models[idx - 1] if idx - 1 < len(role_owned_step_models) else None
        yield emit_event(
            plan_step_event(
                activity_event_factory=activity_event_factory,
                step_number=idx,
                planned_step=planned_step,
                owner_role=(
                    str(role_step.owner_role or "").strip()
                    if role_step is not None
                    else ""
                ),
                handoff_from_role=(
                    str(role_step.handoff_from_role or "").strip()
                    if role_step is not None
                    else ""
                ),
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
            research_depth_profile={
                "tier": research_plan.depth_tier,
                "max_query_variants": research_plan.max_query_variants,
                "results_per_query": research_plan.results_per_query,
                "fused_top_k": research_plan.fused_top_k,
                "max_live_inspections": research_plan.max_live_inspections,
                "min_unique_sources": research_plan.min_unique_sources,
                "web_search_budget": research_plan.web_search_budget,
                "max_file_sources": research_plan.max_file_sources,
                "max_file_chunks": research_plan.max_file_chunks,
                "max_file_scan_pages": research_plan.max_file_scan_pages,
                "simple_explanation_required": research_plan.simple_explanation_required,
            },
            role_owned_steps=role_owned_steps,
        )
    )
    yield emit_event(
        plan_refined_event(
            activity_event_factory=activity_event_factory,
            steps=steps,
            planned_search_terms=research_plan.planned_search_terms,
            planned_keywords=research_plan.planned_keywords,
            research_depth_profile={
                "tier": research_plan.depth_tier,
                "max_query_variants": research_plan.max_query_variants,
                "results_per_query": research_plan.results_per_query,
                "fused_top_k": research_plan.fused_top_k,
                "max_live_inspections": research_plan.max_live_inspections,
                "min_unique_sources": research_plan.min_unique_sources,
                "web_search_budget": research_plan.web_search_budget,
                "max_file_sources": research_plan.max_file_sources,
                "max_file_chunks": research_plan.max_file_chunks,
                "max_file_scan_pages": research_plan.max_file_scan_pages,
                "simple_explanation_required": research_plan.simple_explanation_required,
            },
            fact_coverage=fact_coverage,
            role_owned_steps=role_owned_steps,
        )
    )
    yield emit_event(
        plan_ready_event(
            activity_event_factory=activity_event_factory,
            steps=steps,
            role_owned_steps=role_owned_steps,
        )
    )
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
        role_owned_steps=role_owned_steps,
    )
