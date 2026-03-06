from __future__ import annotations

from collections.abc import Callable, Generator
from dataclasses import replace
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.intelligence import derive_task_intelligence
from api.services.agent.llm_contracts import build_task_contract
from api.services.agent.llm_execution_support import rewrite_task_for_execution
from api.services.agent.memory import get_memory_service
from api.services.agent.llm_personalization import infer_user_preferences
from api.services.agent.models import AgentActivityEvent
from api.services.agent.preferences import get_user_preference_store
from api.services.agent.preflight import run_preflight_checks
from api.services.agent.research_depth_profile import (
    ResearchDepthProfile,
    derive_research_depth_profile,
)

from .models import TaskPreparation
from .text_helpers import compact, truthy


def _bounded_int(value: Any, *, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = int(default)
    return max(low, min(high, parsed))


def _force_deep_search_profile(
    *,
    request: ChatRequest,
    settings: dict[str, Any],
    depth_profile: ResearchDepthProfile,
) -> ResearchDepthProfile:
    deep_search_requested = str(request.agent_mode or "").strip().lower() == "deep_search" or truthy(
        settings.get("__deep_search_enabled"),
        default=False,
    )
    if not deep_search_requested:
        return depth_profile

    complexity = " ".join(str(settings.get("__deep_search_complexity") or "").split()).strip().lower()
    complex_mode = complexity == "complex"

    max_query_variants = _bounded_int(
        settings.get("__research_max_query_variants"),
        default=max(18 if complex_mode else 12, depth_profile.max_query_variants),
        low=8,
        high=20,
    )
    results_per_query = _bounded_int(
        settings.get("__research_results_per_query"),
        default=max(12 if complex_mode else 10, depth_profile.results_per_query),
        low=8,
        high=25,
    )
    source_budget_min = _bounded_int(
        settings.get("__research_source_budget_min"),
        default=max(80 if complex_mode else 50, depth_profile.source_budget_min),
        low=20,
        high=200,
    )
    source_budget_max = _bounded_int(
        settings.get("__research_source_budget_max"),
        default=max(180 if complex_mode else 100, depth_profile.source_budget_max),
        low=source_budget_min,
        high=220,
    )
    min_unique_sources = _bounded_int(
        settings.get("__research_min_unique_sources"),
        default=max(source_budget_min, 50, depth_profile.min_unique_sources),
        low=source_budget_min,
        high=200,
    )
    file_source_budget_min = _bounded_int(
        settings.get("__file_research_source_budget_min"),
        default=max(140 if complex_mode else 100, depth_profile.file_source_budget_min),
        low=24,
        high=220,
    )
    file_source_budget_max = _bounded_int(
        settings.get("__file_research_source_budget_max"),
        default=max(220 if complex_mode else 180, depth_profile.file_source_budget_max),
        low=file_source_budget_min,
        high=240,
    )
    max_file_sources = _bounded_int(
        settings.get("__file_research_max_sources"),
        default=max(file_source_budget_min, depth_profile.max_file_sources),
        low=file_source_budget_min,
        high=240,
    )
    max_file_chunks = _bounded_int(
        settings.get("__file_research_max_chunks"),
        default=max(1800 if complex_mode else 1400, depth_profile.max_file_chunks),
        low=200,
        high=3000,
    )
    max_file_scan_pages = _bounded_int(
        settings.get("__file_research_max_scan_pages"),
        default=max(220 if complex_mode else 180, depth_profile.max_file_scan_pages),
        low=20,
        high=300,
    )

    return replace(
        depth_profile,
        tier="deep_research",
        rationale=(
            "Deep Search mode requested; using complex high-coverage profile."
            if complex_mode
            else "Deep Search mode requested; using broad standard deep-research profile."
        ),
        max_query_variants=max_query_variants,
        results_per_query=results_per_query,
        fused_top_k=max(source_budget_max, depth_profile.fused_top_k),
        max_live_inspections=max(18, depth_profile.max_live_inspections),
        min_unique_sources=min_unique_sources,
        source_budget_min=source_budget_min,
        source_budget_max=source_budget_max,
        min_keywords=max(16, depth_profile.min_keywords),
        file_source_budget_min=file_source_budget_min,
        file_source_budget_max=file_source_budget_max,
        max_file_sources=max_file_sources,
        max_file_chunks=max_file_chunks,
        max_file_scan_pages=max_file_scan_pages,
        include_execution_why=True,
    )


def prepare_task_context(
    *,
    run_id: str,
    conversation_id: str,
    user_id: str,
    request: ChatRequest,
    settings: dict[str, Any],
    emit_event: Callable[[AgentActivityEvent], dict[str, Any]],
    activity_event_factory: Callable[..., AgentActivityEvent],
) -> Generator[dict[str, Any], None, TaskPreparation]:
    task_understanding_started = activity_event_factory(
        event_type="task_understanding_started",
        title="Understanding requested outcome",
        detail=compact(request.message, 220),
        metadata={"conversation_id": conversation_id},
    )
    yield emit_event(task_understanding_started)
    task_intelligence = derive_task_intelligence(
        message=request.message,
        agent_goal=request.agent_goal,
    )

    preference_store = get_user_preference_store()
    saved_preferences = preference_store.get(user_id=user_id)
    inferred_preferences = infer_user_preferences(
        message=request.message,
        existing_preferences=saved_preferences,
    )
    user_preferences = (
        preference_store.merge(user_id=user_id, patch=inferred_preferences)
        if inferred_preferences
        else saved_preferences
    )
    depth_profile = derive_research_depth_profile(
        message=request.message,
        agent_goal=request.agent_goal,
        user_preferences=user_preferences,
        agent_mode=request.agent_mode,
    )
    depth_profile = _force_deep_search_profile(
        request=request,
        settings=settings,
        depth_profile=depth_profile,
    )
    settings["__deep_search_enabled"] = bool(
        truthy(settings.get("__deep_search_enabled"), default=False)
        or str(request.agent_mode or "").strip().lower() == "deep_search"
    )
    settings["__research_depth_profile"] = depth_profile.as_dict()
    settings["__research_depth_tier"] = depth_profile.tier
    settings["__research_max_query_variants"] = depth_profile.max_query_variants
    settings["__research_results_per_query"] = depth_profile.results_per_query
    settings["__research_fused_top_k"] = depth_profile.fused_top_k
    settings["__research_max_live_inspections"] = depth_profile.max_live_inspections
    settings["__research_min_unique_sources"] = depth_profile.min_unique_sources
    settings["__research_source_budget_min"] = depth_profile.source_budget_min
    settings["__research_source_budget_max"] = depth_profile.source_budget_max
    settings["__research_web_search_budget"] = _bounded_int(
        settings.get("__research_web_search_budget"),
        default=depth_profile.max_query_variants * depth_profile.results_per_query,
        low=20,
        high=350,
    )
    settings["__research_min_keywords"] = depth_profile.min_keywords
    settings["__file_research_source_budget_min"] = depth_profile.file_source_budget_min
    settings["__file_research_source_budget_max"] = depth_profile.file_source_budget_max
    settings["__file_research_max_sources"] = depth_profile.max_file_sources
    settings["__file_research_max_chunks"] = depth_profile.max_file_chunks
    settings["__file_research_max_scan_pages"] = depth_profile.max_file_scan_pages
    settings["__file_research_prefer_pdf"] = True
    settings["__simple_explanation_required"] = depth_profile.simple_explanation_required
    settings["__include_execution_why"] = depth_profile.include_execution_why
    depth_event = activity_event_factory(
        event_type="llm.research_depth_profile",
        title="Adaptive research depth profile selected",
        detail=f"Tier `{depth_profile.tier}` with target {depth_profile.source_budget_min}-{depth_profile.source_budget_max} sources.",
        metadata=depth_profile.as_dict(),
    )
    yield emit_event(depth_event)

    task_understanding_ready = activity_event_factory(
        event_type="task_understanding_ready",
        title="Task understanding completed",
        detail=task_intelligence.objective,
        metadata={
            **task_intelligence.to_dict(),
            "preferences": user_preferences,
            "research_depth_profile": depth_profile.as_dict(),
            "conversation_context_summary": str(
                settings.get("__conversation_summary") or ""
            ).strip()[:480],
            "conversation_snippets": (
                [
                    str(item).strip()
                    for item in (settings.get("__conversation_snippets") or [])
                    if str(item).strip()
                ][:8]
                if isinstance(settings.get("__conversation_snippets"), list)
                else []
            ),
        },
    )
    yield emit_event(task_understanding_ready)

    conversation_summary_text = str(settings.get("__conversation_summary") or "").strip()
    if conversation_summary_text:
        llm_context_event = activity_event_factory(
            event_type="llm.context_summary",
            title="LLM contextual grounding",
            detail=compact(conversation_summary_text, 180),
            metadata={"conversation_summary": conversation_summary_text},
        )
        yield emit_event(llm_context_event)

    memory_context_snippets: list[str] = []
    if truthy(settings.get("agent.memory_context_enabled"), default=True):
        memory_query = " ".join(
            [
                str(request.message or "").strip(),
                str(request.agent_goal or "").strip(),
                conversation_summary_text,
            ]
        ).strip()
        if memory_query:
            try:
                memory_context_snippets = get_memory_service().retrieve_context_snippets(
                    query=memory_query,
                    limit=4,
                )
            except Exception:
                memory_context_snippets = []
    if memory_context_snippets:
        memory_event = activity_event_factory(
            event_type="llm.context_memory",
            title="Loaded relevant memory context",
            detail=f"Retrieved {len(memory_context_snippets)} similar memory snippet(s)",
            metadata={"memory_context_snippets": memory_context_snippets[:4]},
        )
        yield emit_event(memory_event)

    if task_intelligence.intent_tags:
        llm_intent_event = activity_event_factory(
            event_type="llm.intent_tags",
            title="LLM intent classification",
            detail=", ".join(list(task_intelligence.intent_tags)[:8]),
            metadata={"intent_tags": list(task_intelligence.intent_tags)},
        )
        yield emit_event(llm_intent_event)

    preflight_checks = run_preflight_checks(
        requires_delivery=task_intelligence.requires_delivery,
        requires_web_inspection=task_intelligence.requires_web_inspection,
    )
    preflight_started_event = activity_event_factory(
        event_type="preflight_started",
        title="Running preflight checks",
        detail="Validating credentials and execution prerequisites",
        metadata={"check_count": len(preflight_checks)},
    )
    yield emit_event(preflight_started_event)
    for check in preflight_checks:
        preflight_check_event = activity_event_factory(
            event_type="preflight_check",
            title=str(check.get("name") or "preflight_check"),
            detail=str(check.get("detail") or ""),
            metadata={"status": str(check.get("status") or "info")},
        )
        yield emit_event(preflight_check_event)
    preflight_completed_event = activity_event_factory(
        event_type="preflight_completed",
        title="Preflight checks completed",
        detail="Proceeding with planning and tool execution",
        metadata={"checks": preflight_checks},
    )
    yield emit_event(preflight_completed_event)

    planning_started_event = activity_event_factory(
        event_type="planning_started",
        title="Planning agent workflow",
        detail=compact(request.message, 220),
        metadata={"conversation_id": conversation_id},
    )
    yield emit_event(planning_started_event)

    conversation_summary = " ".join(
        str(settings.get("__conversation_summary") or "").split()
    ).strip()

    rewrite_started_event = activity_event_factory(
        event_type="llm.task_rewrite_started",
        title="Rewriting task into detailed brief",
        detail=compact(request.message, 200),
        metadata={"agent_goal": str(request.agent_goal or "").strip()[:240]},
    )
    yield emit_event(rewrite_started_event)
    rewrite_payload = rewrite_task_for_execution(
        message=request.message,
        agent_goal=request.agent_goal,
        conversation_summary=conversation_summary,
    )
    rewritten_task = " ".join(
        str(rewrite_payload.get("detailed_task") or request.message or "").split()
    ).strip()
    planned_deliverables = [
        str(item).strip()
        for item in (rewrite_payload.get("deliverables") if isinstance(rewrite_payload, dict) else [])
        if str(item).strip()
    ][:6]
    planned_constraints = [
        str(item).strip()
        for item in (rewrite_payload.get("constraints") if isinstance(rewrite_payload, dict) else [])
        if str(item).strip()
    ][:6]
    rewrite_completed_event = activity_event_factory(
        event_type="llm.task_rewrite_completed",
        title="Task rewrite ready",
        detail=compact(rewritten_task or request.message, 220),
        metadata={
            "detailed_task": rewritten_task or request.message,
            "deliverables": planned_deliverables,
            "constraints": planned_constraints,
        },
    )
    yield emit_event(rewrite_completed_event)

    contract_started_event = activity_event_factory(
        event_type="llm.task_contract_started",
        title="Building task contract",
        detail="Extracting required outputs, facts, and action gates",
        metadata={"intent_tags": list(task_intelligence.intent_tags)},
    )
    yield emit_event(contract_started_event)
    task_contract = build_task_contract(
        message=request.message,
        agent_goal=request.agent_goal,
        rewritten_task=rewritten_task,
        deliverables=planned_deliverables,
        constraints=planned_constraints,
        intent_tags=list(task_intelligence.intent_tags),
        conversation_summary=conversation_summary,
    )

    contract_objective = " ".join(str(task_contract.get("objective") or "").split()).strip()
    contract_outputs = [
        str(item).strip()
        for item in (
            task_contract.get("required_outputs")
            if isinstance(task_contract.get("required_outputs"), list)
            else []
        )
        if str(item).strip()
    ][:6]
    contract_facts = [
        str(item).strip()
        for item in (
            task_contract.get("required_facts")
            if isinstance(task_contract.get("required_facts"), list)
            else []
        )
        if str(item).strip()
    ][:6]
    contract_actions = [
        str(item).strip()
        for item in (
            task_contract.get("required_actions")
            if isinstance(task_contract.get("required_actions"), list)
            else []
        )
        if str(item).strip()
    ][:6]
    contract_missing_requirements = [
        str(item).strip()
        for item in (
            task_contract.get("missing_requirements")
            if isinstance(task_contract.get("missing_requirements"), list)
            else []
        )
        if str(item).strip()
    ][:6]
    contract_success_checks = [
        str(item).strip()
        for item in (
            task_contract.get("success_checks")
            if isinstance(task_contract.get("success_checks"), list)
            else []
        )
        if str(item).strip()
    ][:8]
    contract_target = " ".join(str(task_contract.get("delivery_target") or "").split()).strip()
    contract_completed_event = activity_event_factory(
        event_type="llm.task_contract_completed",
        title="Task contract ready",
        detail=compact(contract_objective or rewritten_task or request.message, 200),
        metadata={
            "objective": contract_objective,
            "required_outputs": contract_outputs,
            "required_facts": contract_facts,
            "required_actions": contract_actions,
            "delivery_target": contract_target,
            "missing_requirements": contract_missing_requirements,
            "success_checks": contract_success_checks,
        },
    )
    yield emit_event(contract_completed_event)

    clarification_gate_enabled = truthy(
        settings.get("agent.clarification_gate_enabled"),
        default=True,
    )
    deep_research_requested = bool(
        str(request.agent_mode or "").strip().lower() == "deep_search"
        or truthy(settings.get("__deep_search_enabled"), default=False)
        or str(settings.get("__research_depth_tier") or "").strip().lower()
        in {"deep_research", "deep_analytics"}
    )
    clarification_blocked = clarification_gate_enabled and bool(contract_missing_requirements)
    if clarification_blocked and deep_research_requested:
        clarification_blocked = False
    clarification_questions = [
        f"Please provide: {item}" for item in contract_missing_requirements[:6]
    ]
    if clarification_blocked:
        clarification_event = activity_event_factory(
            event_type="llm.clarification_requested",
            title="Clarification required before execution",
            detail=compact("; ".join(contract_missing_requirements[:3]), 200),
            metadata={
                "missing_requirements": contract_missing_requirements[:6],
                "questions": clarification_questions[:6],
            },
        )
        yield emit_event(clarification_event)
    else:
        clarification_detail = "Execution can proceed with current contract inputs."
        clarification_metadata: dict[str, Any] = {"missing_requirements": []}
        if contract_missing_requirements and deep_research_requested:
            clarification_detail = (
                "Deep research mode: proceeding with best-effort assumptions for missing optional requirements."
            )
            clarification_metadata = {
                "missing_requirements": contract_missing_requirements[:6],
                "clarification_bypassed_for_deep_research": True,
            }
        clarification_resolved_event = activity_event_factory(
            event_type="llm.clarification_resolved",
            title="Clarification requirements satisfied",
            detail=clarification_detail,
            metadata=clarification_metadata,
        )
        yield emit_event(clarification_resolved_event)

    return TaskPreparation(
        task_intelligence=task_intelligence,
        user_preferences=user_preferences,
        research_depth_profile=depth_profile.as_dict(),
        conversation_summary=conversation_summary,
        rewritten_task=rewritten_task,
        planned_deliverables=planned_deliverables,
        planned_constraints=planned_constraints,
        task_contract=task_contract,
        contract_objective=contract_objective,
        contract_outputs=contract_outputs,
        contract_facts=contract_facts,
        contract_actions=contract_actions,
        contract_target=contract_target,
        contract_missing_requirements=contract_missing_requirements,
        contract_success_checks=contract_success_checks,
        memory_context_snippets=memory_context_snippets,
        clarification_blocked=clarification_blocked,
        clarification_questions=clarification_questions,
    )
