"""B1-CU-05 - Computer Use SSE router.

Responsibility: HTTP layer for Computer Use browser sessions.
All business logic is delegated to services/computer_use.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.auth import get_current_user_id
from api.context import get_context
from api.services.computer_use.policy_gate import evaluate_task_policy, get_policy_snapshot
from api.services.computer_use.runtime_config import (
    resolve_effective_model,
    validate_runtime_requirements,
)
from api.services.computer_use.slo_metrics import (
    StreamStatus,
    get_computer_use_slo_store,
)
from api.services.computer_use.session_record import list_records
from api.services.computer_use.session_registry import (
    SessionLimitExceeded,
    StreamLimitExceeded,
    get_session_registry,
)
from api.services.settings_service import load_user_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/computer-use", tags=["computer-use"])


class StartSessionRequest(BaseModel):
    url: str = "about:blank"


class StartSessionResponse(BaseModel):
    session_id: str
    url: str


class NavigateRequest(BaseModel):
    url: str


class ActiveModelResponse(BaseModel):
    model: str
    source: str


class ComputerUsePolicyResponse(BaseModel):
    mode: str
    max_task_chars: int
    blocked_terms_count: int
    blocked_terms_preview: list[str]


class ComputerUseSLOSummaryResponse(BaseModel):
    window_seconds: int
    run_count: int
    success_rate: float
    error_rate: float
    p50_latency_ms: int
    p95_latency_ms: int
    p99_latency_ms: int
    avg_latency_ms: int
    avg_event_count: float
    avg_action_count: float
    status_counts: dict[str, int]


@router.post("/sessions", response_model=StartSessionResponse, status_code=status.HTTP_201_CREATED)
def start_session(
    body: StartSessionRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    request_id: str | None = Query(default=None),
) -> StartSessionResponse:
    """Create a new browser session and navigate to the initial URL."""
    registry = get_session_registry()
    try:
        session = registry.create(
            user_id=user_id,
            start_url=body.url,
            request_id=request_id,
        )
    except SessionLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Failed to create browser session: %s", exc)
        raise HTTPException(status_code=500, detail=f"Could not start browser session: {exc}") from exc

    if body.url and body.url != "about:blank":
        try:
            session.navigate(body.url)
        except Exception as exc:
            registry.close(session.session_id)
            raise HTTPException(status_code=400, detail=f"Navigation failed: {exc}") from exc

    return StartSessionResponse(session_id=session.session_id, url=session.current_url())


@router.get("/sessions")
def list_sessions(
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> list[dict[str, Any]]:
    """Return all session records for the authenticated user (newest first)."""
    try:
        records = list_records(user_id)
    except Exception as exc:
        logger.error("Failed to list sessions: %s", exc)
        raise HTTPException(status_code=500, detail="Could not list sessions.") from exc

    registry = get_session_registry()
    live_ids = set(registry.active_session_ids())
    for record in records:
        record["live"] = record["session_id"] in live_ids
    return records


@router.get("/sessions/{session_id}")
def get_session(
    session_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    """Return session metadata."""
    session = get_session_registry().get_for_user(session_id, user_id=user_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    return {
        "session_id": session_id,
        "url": session.current_url(),
        "viewport": session.viewport(),
    }


@router.post("/sessions/{session_id}/navigate")
def navigate_session(
    session_id: str,
    body: NavigateRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    """Navigate an existing session without tearing down the browser."""
    session = get_session_registry().get_for_user(session_id, user_id=user_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=422, detail="url must not be empty.")
    try:
        title = session.navigate(url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Navigation failed: {exc}") from exc
    return {"session_id": session_id, "url": session.current_url(), "title": title}


@router.get("/active-model", response_model=ActiveModelResponse)
def get_active_model(
    user_id: Annotated[str, Depends(get_current_user_id)],
    model: str | None = None,
) -> ActiveModelResponse:
    """Return the resolved computer-use model and source."""
    user_settings = load_user_settings(context=get_context(), user_id=user_id)
    resolved_model, source = resolve_effective_model(
        explicit_model=model,
        user_settings=user_settings,
    )
    return ActiveModelResponse(model=resolved_model, source=source)


@router.get("/policy", response_model=ComputerUsePolicyResponse)
def get_computer_use_policy(
    _user_id: Annotated[str, Depends(get_current_user_id)],
) -> ComputerUsePolicyResponse:
    """Expose the resolved Computer Use policy gate settings."""
    return ComputerUsePolicyResponse(**get_policy_snapshot())


@router.get("/slo/summary", response_model=ComputerUseSLOSummaryResponse)
def get_computer_use_slo_summary(
    user_id: Annotated[str, Depends(get_current_user_id)],
    window_seconds: int = Query(default=86400, ge=60, le=7 * 24 * 3600),
) -> ComputerUseSLOSummaryResponse:
    """Return user-scoped Computer Use SLO summary metrics."""
    summary = get_computer_use_slo_store().summary(
        user_id=user_id,
        window_seconds=window_seconds,
    )
    return ComputerUseSLOSummaryResponse(**summary)


@router.get("/sessions/{session_id}/stream")
def stream_agent_loop(
    session_id: str,
    task: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    model: str | None = None,
    max_iterations: int = 25,
    run_id: str | None = None,
) -> StreamingResponse:
    """Stream Computer Use agent loop events as Server-Sent Events."""
    registry = get_session_registry()
    session = registry.get_for_user(session_id, user_id=user_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    normalized_task = str(task or "").strip()
    if not normalized_task:
        raise HTTPException(status_code=422, detail="task must not be empty.")

    policy_decision = evaluate_task_policy(normalized_task)
    if policy_decision.reason:
        logger.warning(
            "Computer Use policy match user=%s session=%s mode=%s reason=%s",
            user_id,
            session_id,
            policy_decision.mode,
            policy_decision.reason,
        )
    if not policy_decision.allowed:
        now = time.time()
        get_computer_use_slo_store().record_stream_result(
            user_id=user_id,
            session_id=session_id,
            status="policy_blocked",
            started_at=now,
            ended_at=now,
            event_count=0,
            action_count=0,
        )
        raise HTTPException(status_code=403, detail=policy_decision.reason)

    clean_model: str | None = model.strip() if model else None
    if not clean_model:
        clean_model = None

    user_settings = load_user_settings(context=get_context(), user_id=user_id)
    runtime_ok, runtime_error = validate_runtime_requirements(
        model=clean_model,
        user_settings=user_settings,
    )
    if not runtime_ok:
        raise HTTPException(status_code=400, detail=runtime_error)

    resolved_model, model_source = resolve_effective_model(
        explicit_model=clean_model,
        user_settings=user_settings,
    )
    stream_started_at = time.time()
    slo_store = get_computer_use_slo_store()

    try:
        registry.try_acquire_stream_lease(session_id=session_id, user_id=user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found.") from exc
    except StreamLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    normalized_run_id = str(run_id or "").strip() or None
    publish_index = 0
    try:
        from api.services.computer_use.agent_loop import run_agent_loop
    except Exception:
        registry.release_stream_lease(session_id=session_id, user_id=user_id)
        slo_store.record_stream_result(
            user_id=user_id,
            session_id=session_id,
            status="failed",
            started_at=stream_started_at,
            ended_at=time.time(),
            event_count=0,
            action_count=0,
        )
        raise

    def _publish_event(event: dict[str, Any]) -> None:
        nonlocal publish_index
        if not normalized_run_id:
            return

        event_type = str(event.get("event_type") or "").strip().lower()
        if not event_type:
            return

        # Keep the theatre channel lightweight; BrowserScene already receives screenshots.
        if event_type == "screenshot":
            return

        publish_index += 1
        detail = _event_detail(event=event)
        payload = {
            "event_type": f"computer_use_{event_type}",
            "title": "Computer Use",
            "detail": detail,
            "stage": "execute",
            "status": "running" if event_type in {"action", "text"} else ("failed" if event_type == "error" else "completed"),
            "event_index": publish_index,
            "data": {
                "event_type": f"computer_use_{event_type}",
                "detail": detail,
                "computer_use_session_id": session_id,
                "computer_use_task": task,
                "computer_use_model": resolved_model,
                "computer_use_model_source": model_source,
                "computer_use_max_iterations": max_iterations,
                "url": str(event.get("url") or ""),
                "iteration": int(event.get("iteration") or 0),
                # Theatre correlation
                "scene_family": "browser",
                "brand_slug": "browser",
                "connector_id": "computer_use_browser",
                "connector_label": "Computer Browser",
                "operation_label": f"Computer Use: {event_type}",
            },
        }

        try:
            from api.services.agent.live_events import get_live_event_broker

            get_live_event_broker().publish(
                user_id=user_id,
                run_id=normalized_run_id,
                event=payload,
            )
        except Exception:
            logger.debug("Computer Use live-event publish failed", exc_info=True)

        try:
            from api.services.agent.activity import get_activity_store
            from api.services.agent.models import AgentActivityEvent, new_id

            record = AgentActivityEvent(
                event_id=new_id("evt"),
                run_id=normalized_run_id,
                event_type=f"computer_use_{event_type}",
                title="Computer Use",
                detail=detail,
                seq=publish_index,
                stage="execute",
                status=payload["status"],
                data=payload["data"],
            )
            get_activity_store().append(record)
        except Exception:
            logger.debug("Computer Use activity-store append failed", exc_info=True)

    def _generate():
        event_count = 0
        action_count = 0
        final_status: StreamStatus = "cancelled"

        def _track_event(event: dict[str, Any]) -> None:
            nonlocal event_count, action_count, final_status
            event_count += 1
            event_type = str(event.get("event_type") or "").strip().lower()
            if event_type == "action":
                action_count += 1
            if event_type == "done":
                final_status = "completed"
            elif event_type == "max_iterations":
                final_status = "max_iterations"
            elif event_type == "error":
                final_status = "failed"

        started_event = {
            "event_type": "started",
            "detail": "Computer Use session started.",
            "iteration": 0,
            "url": session.current_url(),
        }
        _track_event(started_event)
        _publish_event(started_event)
        try:
            for event in run_agent_loop(
                session,
                normalized_task,
                model=clean_model,
                max_iterations=max_iterations,
                user_settings=user_settings,
            ):
                _track_event(event)
                _publish_event(event)
                if event.get("event_type") != "screenshot":
                    payload = json.dumps(event)
                else:
                    payload = json.dumps(
                        {
                            "event_type": "screenshot",
                            "iteration": event.get("iteration"),
                            "url": event.get("url"),
                            "screenshot_b64": event.get("screenshot_b64", ""),
                        }
                    )
                yield f"data: {payload}\n\n"
        except Exception as exc:
            error_event = {
                "event_type": "error",
                "detail": str(exc)[:400],
                "iteration": 0,
                "url": session.current_url(),
            }
            _track_event(error_event)
            _publish_event(error_event)
            yield f"data: {json.dumps({'event_type': 'error', 'detail': str(exc)[:400]})}\n\n"
        finally:
            registry.release_stream_lease(session_id=session_id, user_id=user_id)
            slo_store.record_stream_result(
                user_id=user_id,
                session_id=session_id,
                status=final_status,
                started_at=stream_started_at,
                ended_at=time.time(),
                event_count=event_count,
                action_count=action_count,
            )
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def close_session(
    session_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> None:
    """Close and destroy a Computer Use session."""
    registry = get_session_registry()
    session = registry.get_for_user(session_id, user_id=user_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    removed = registry.close(session_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Session not found.")

    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _event_detail(*, event: dict[str, Any]) -> str:
    event_type = str(event.get("event_type") or "").strip().lower()
    if event_type == "text":
        text = str(event.get("text") or "").strip()
        return text[:220] if text else "Computer Use generated a text update."
    if event_type == "action":
        action = str(event.get("action") or "action").strip()
        return f"Running action: {action}"
    if event_type == "done":
        return "Computer Use task completed."
    if event_type == "max_iterations":
        return "Computer Use reached the step limit."
    if event_type == "error":
        detail = str(event.get("detail") or "").strip()
        return detail[:220] if detail else "Computer Use failed."
    if event_type == "started":
        return str(event.get("detail") or "Computer Use session started.").strip()
    return str(event.get("detail") or "Computer Use update.").strip()[:220]
