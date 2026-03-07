from __future__ import annotations

from typing import Any

from api.schemas import ChatRequest
from api.services.agent.planner import PlannedStep

from .models import ExecutionState


def _pending_step_rows(*, steps: list[PlannedStep], limit: int = 32) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for step in list(steps or [])[: max(1, int(limit))]:
        rows.append(
            {
                "tool_id": str(step.tool_id or "").strip(),
                "title": " ".join(str(step.title or "").split()).strip()[:180],
            }
        )
    return rows


def persist_run_checkpoint(
    *,
    session_store: Any,
    run_id: str,
    user_id: str,
    tenant_id: str,
    conversation_id: str,
    request: ChatRequest,
    checkpoint: dict[str, Any],
    settings: dict[str, Any],
    state: ExecutionState | None = None,
    pending_steps: list[PlannedStep] | None = None,
    resume_status: str = "in_progress",
) -> None:
    try:
        payload: dict[str, Any] = {
            "run_id": run_id,
            "user_id": user_id,
            "tenant_id": tenant_id,
            "conversation_id": conversation_id,
            "message": request.message,
            "agent_goal": request.agent_goal,
            "resume_status": " ".join(str(resume_status or "").split()).strip().lower() or "in_progress",
            "execution_checkpoint": dict(checkpoint or {}),
            "execution_checkpoints": list(settings.get("__execution_checkpoints") or [])[-24:],
            "active_role": " ".join(str(settings.get("__active_execution_role") or "").split()).strip().lower(),
            "side_effect_status": dict(settings.get("__side_effect_status") or {})
            if isinstance(settings.get("__side_effect_status"), dict)
            else {},
        }
        if state is not None:
            payload["executed_steps"] = list(state.executed_steps[-24:])
            payload["next_recommended_steps"] = list(state.next_steps[:8])
        if isinstance(pending_steps, list):
            payload["pending_steps"] = _pending_step_rows(steps=pending_steps)
        session_store.save_session_run(payload)
    except Exception:
        return
