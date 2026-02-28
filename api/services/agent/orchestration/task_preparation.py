from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.intelligence import derive_task_intelligence
from api.services.agent.llm_contracts import build_task_contract
from api.services.agent.llm_execution_support import rewrite_task_for_execution
from api.services.agent.llm_personalization import infer_user_preferences
from api.services.agent.models import AgentActivityEvent
from api.services.agent.preferences import get_user_preference_store
from api.services.agent.preflight import run_preflight_checks

from .models import TaskPreparation
from .text_helpers import compact, truthy


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

    task_understanding_ready = activity_event_factory(
        event_type="task_understanding_ready",
        title="Task understanding completed",
        detail=task_intelligence.objective,
        metadata={
            **task_intelligence.to_dict(),
            "preferences": user_preferences,
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
    clarification_blocked = clarification_gate_enabled and bool(contract_missing_requirements)
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
        clarification_resolved_event = activity_event_factory(
            event_type="llm.clarification_resolved",
            title="Clarification requirements satisfied",
            detail="Execution can proceed with current contract inputs.",
            metadata={"missing_requirements": []},
        )
        yield emit_event(clarification_resolved_event)

    return TaskPreparation(
        task_intelligence=task_intelligence,
        user_preferences=user_preferences,
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
        clarification_blocked=clarification_blocked,
        clarification_questions=clarification_questions,
    )
