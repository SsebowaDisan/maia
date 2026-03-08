from __future__ import annotations

from typing import Any

from api.schemas import ChatRequest
from api.services.agent.models import AgentRunResult
from api.services.agent.observability import get_agent_observability


def persist_completed_run(
    *,
    run_id: str,
    user_id: str,
    conversation_id: str,
    request: ChatRequest,
    access_context: Any,
    result: AgentRunResult,
    coverage: dict[str, Any],
    verification_report: dict[str, Any],
    task_contract_objective: str,
    user_preferences: dict[str, Any],
    step_count: int,
    action_count: int,
    source_count: int,
    web_kpi_gate: dict[str, Any],
    web_kpi_summary: dict[str, Any],
    web_evidence_summary: dict[str, Any],
    activity_store: Any,
    session_store: Any,
    audit: Any,
    memory: Any,
) -> None:
    activity_store.end_run(run_id, result.to_dict())
    try:
        session_store.save_session_run(
            {
                "run_id": run_id,
                "user_id": user_id,
                "tenant_id": access_context.tenant_id,
                "conversation_id": conversation_id,
                "message": request.message,
                "agent_goal": request.agent_goal,
                "answer": result.answer,
                "next_recommended_steps": result.next_recommended_steps,
                "needs_human_review": result.needs_human_review,
                "human_review_notes": result.human_review_notes,
                "evidence_count": len(result.evidence_items),
                "event_coverage": coverage,
                "verification_grade": verification_report.get("grade"),
                "verification_score": verification_report.get("score"),
                "task_contract_objective": task_contract_objective,
            }
        )
    except Exception:
        pass

    audit.write(
        user_id=user_id,
        tenant_id=access_context.tenant_id,
        run_id=run_id,
        event="agent_run_completed",
        payload={
            "conversation_id": conversation_id,
            "steps": step_count,
            "actions": action_count,
            "sources": source_count,
            "event_coverage_percent": coverage.get("coverage_percent", 0),
            "web_ready_for_scale": bool(web_kpi_gate.get("ready_for_scale")),
            "web_steps_total": int(web_kpi_summary.get("web_steps_total") or 0),
            "web_evidence_total": int(web_evidence_summary.get("web_evidence_total") or 0),
        },
    )

    memory.save_run(
        {
            "run_id": run_id,
            "user_id": user_id,
            "tenant_id": access_context.tenant_id,
            "conversation_id": conversation_id,
            "message": request.message,
            "agent_goal": request.agent_goal,
            "answer": result.answer,
            "actions_taken": [item.to_dict() for item in result.actions_taken],
            "sources_used": [item.to_dict() for item in result.sources_used],
            "evidence_items": [dict(item) for item in result.evidence_items],
            "next_recommended_steps": result.next_recommended_steps,
            "needs_human_review": result.needs_human_review,
            "human_review_notes": result.human_review_notes,
            "web_summary": result.web_summary,
            "user_preferences": user_preferences,
            "event_coverage": coverage,
        }
    )
    get_agent_observability().observe_run_completion(
        run_id=run_id,
        step_count=step_count,
        action_count=action_count,
        source_count=source_count,
        needs_human_review=result.needs_human_review,
        reward_score=None,
    )
