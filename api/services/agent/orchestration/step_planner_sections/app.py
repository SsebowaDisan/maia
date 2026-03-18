from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.models import AgentActivityEvent
from api.services.agent.observability import get_agent_observability
from api.services.agent.planner import PlannedStep, build_plan, resolve_web_routing
from api.services.agent.reasoning import TreeOfThoughtPlanner

# Causal DAG (Innovation #4) — optional, try/except wrapped
try:
    from api.services.agent.reasoning import CausalDAG
    _CAUSAL_DAG_AVAILABLE = True
except Exception:
    _CAUSAL_DAG_AVAILABLE = False

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

    # Enforce agent definition tool allowlist when present.
    # The allowlist comes from AgentDefinitionSchema.tools and is injected by
    # run_agent_task() via settings["__allowed_tool_ids"].  This ensures a
    # marketplace agent (e.g. ga4-analytics-reporter) can only plan steps using
    # the tools it declared — not the full global registry.
    _allowed = settings.get("__allowed_tool_ids")
    if isinstance(_allowed, list) and _allowed:
        _allowed_set = {str(t).strip() for t in _allowed if str(t).strip()}
        available_tool_ids = available_tool_ids & _allowed_set

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

    # --- Tree-of-Thought planning (Innovation #6) -------------------------
    # Try multi-candidate planning first; fall back to single-plan if it fails.
    steps: list[PlannedStep] = []
    _tot_used = False
    try:
        _tot_planner = TreeOfThoughtPlanner()
        _tot_candidates = _tot_planner.generate_plan_candidates(
            task_goal=str(request.message or ""),
            available_tools=sorted(available_tool_ids)[:60],
            context=str(request.agent_goal or ""),
            num_candidates=3,
        )
        if _tot_candidates:
            _task_contract = getattr(task_prep, "task_contract", None) or {}
            _scored = _tot_planner.score_candidates(_tot_candidates, _task_contract)
            _best = _tot_planner.select_best(_scored)
            if _best and _best.steps:
                steps = [
                    PlannedStep(
                        tool_id=str(s.get("tool_id") or ""),
                        title=str(s.get("title") or "")[:120],
                        params=dict(s.get("params") or {}),
                        why_this_step=str(s.get("why_this_step") or "")[:240],
                        expected_evidence=tuple(
                            str(e)[:220]
                            for e in (s.get("expected_evidence") or [])
                            if str(e).strip()
                        ),
                    )
                    for s in _best.steps
                    if str(s.get("tool_id") or "").strip()
                ]
                _tot_used = bool(steps)
                # Store alternatives for fallback in settings.
                settings["__tot_alternatives"] = [
                    {
                        "plan_id": alt.plan_id,
                        "rationale": alt.rationale[:200],
                        "score": alt.score,
                        "step_count": len(alt.steps),
                    }
                    for alt in _tot_planner.alternatives[:4]
                ]
                settings["__tot_selected_plan_id"] = _best.plan_id
    except Exception:
        import logging as _tot_log
        _tot_log.getLogger(__name__).debug(
            "Tree-of-Thought planning failed — falling back to single-plan",
            exc_info=True,
        )

    # Fall back to the original single-plan LLM call if ToT did not produce steps.
    if not _tot_used:
        steps = build_plan(
            planning_request,
            preferred_tool_ids=set(capability_analysis.preferred_tool_ids),
            web_routing=web_routing,
        )
    # --- end Tree-of-Thought -----------------------------------------------

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
    settings["__research_max_search_rounds"] = getattr(research_plan, "max_search_rounds", 1)
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
        registry=registry,
    )
    fact_coverage = summarize_fact_coverage(
        contract_facts=task_prep.contract_facts,
        steps=steps,
        analytics_context=bool(getattr(task_prep.task_intelligence, "is_analytics_request", False)),
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

    delivery_email = extract_first_email(
        request.message,
        request.agent_goal if request.agent_mode == "company_agent" else "",
    )
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
    # --- Causal DAG (Innovation #4) -------------------------------------------
    # Build a dependency graph from the plan, detect conflicts, compute optimal
    # execution order, and store the graph in settings for brain/step executor.
    try:
        if _CAUSAL_DAG_AVAILABLE and len(steps) >= 2:
            _causal = CausalDAG()
            _step_dicts = [
                {
                    "step_id": f"step_{i + 1}",
                    "tool_id": s.tool_id,
                    "title": s.title[:80],
                    "expected_output_type": "",
                    "side_effects": [],
                }
                for i, s in enumerate(steps)
            ]
            _causal_graph = _causal.build_from_steps(_step_dicts)
            _conflicts = _causal.detect_conflicts(_causal_graph)
            _exec_order = _causal.optimal_execution_order(_causal_graph)
            settings["__causal_dag"] = {
                "node_count": len(_causal_graph.nodes),
                "edge_count": len(_causal_graph.edges),
                "conflicts": [
                    {"from": c[0], "to": c[1]} for c in _conflicts[:5]
                ],
                "optimal_order": _exec_order[:40],
            }
            # Store the graph object for use by the brain during execution.
            settings["__causal_graph_obj"] = _causal_graph
            if _conflicts:
                yield emit_event(
                    activity_event_factory(
                        event_type="causal_dag_conflicts",
                        title=f"Causal DAG: {len(_conflicts)} conflict(s) detected",
                        detail="; ".join(
                            f"{c[0]} ↔ {c[1]}" for c in _conflicts[:3]
                        ),
                        metadata=settings["__causal_dag"],
                    )
                )
    except Exception:
        import logging as _cdag_log
        _cdag_log.getLogger(__name__).debug(
            "CausalDAG planning failed — non-blocking", exc_info=True,
        )
    # --- end Causal DAG -------------------------------------------------------

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
