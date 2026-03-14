"""B1-CU-05 — Computer Use SSE router.

Responsibility: HTTP layer for Computer Use sessions.
All logic delegated to services/computer_use/.

Endpoints:
  POST   /api/computer-use/sessions          — create session, navigate to URL, return session_id
  GET    /api/computer-use/sessions/{id}/stream — SSE: run agent loop, stream events
  DELETE /api/computer-use/sessions/{id}     — close session
  GET    /api/computer-use/sessions/{id}     — get session metadata
"""
from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.auth import get_current_user_id
from api.context import get_context
from api.services.computer_use.session_record import list_records
from api.services.computer_use.session_registry import get_session_registry
from api.services.settings_service import load_user_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/computer-use", tags=["computer-use"])


# ── Request / Response bodies ──────────────────────────────────────────────────

class StartSessionRequest(BaseModel):
    url: str = "about:blank"


class StartSessionResponse(BaseModel):
    session_id: str
    url: str


class NavigateRequest(BaseModel):
    url: str


class ActiveModelResponse(BaseModel):
    model: str
    source: str  # "explicit" | "settings" | "env:COMPUTER_USE_MODEL" | "env:OPENAI_CHAT_MODEL" | "default"


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/sessions", response_model=StartSessionResponse, status_code=status.HTTP_201_CREATED)
def start_session(
    body: StartSessionRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> StartSessionResponse:
    """Create a new browser session and navigate to the initial URL."""
    registry = get_session_registry()
    try:
        session = registry.create(user_id=user_id, start_url=body.url)
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
    # Annotate which sessions are currently live in the registry
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
    session = get_session_registry().get(session_id)
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
    """Navigate an existing session to a new URL.

    Useful when the task is complete and the user wants to run another
    task without tearing down the browser session.
    """
    session = get_session_registry().get(session_id)
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
    """Return the resolved computer-use model and the source that provided it.

    Follows the same priority chain as the agent loop:
      explicit query param → user settings → COMPUTER_USE_MODEL env → OPENAI_CHAT_MODEL env → default
    """
    import os
    if model:
        m = model.strip()
        if m:
            return ActiveModelResponse(model=m, source="explicit")

    user_settings = load_user_settings(context=get_context(), user_id=user_id)
    stored = str(user_settings.get("agent.computer_use_model", "")).strip()
    if stored:
        return ActiveModelResponse(model=stored, source="settings")

    cu_env = str(os.environ.get("COMPUTER_USE_MODEL", "")).strip()
    if cu_env:
        return ActiveModelResponse(model=cu_env, source="env:COMPUTER_USE_MODEL")

    chat_env = str(os.environ.get("OPENAI_CHAT_MODEL", "")).strip()
    if chat_env:
        return ActiveModelResponse(model=chat_env, source="env:OPENAI_CHAT_MODEL")

    return ActiveModelResponse(model="gpt-4o", source="default")


@router.get("/sessions/{session_id}/stream")
def stream_agent_loop(
    session_id: str,
    task: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    model: str | None = None,
    max_iterations: int = 25,
) -> StreamingResponse:
    """Stream Computer Use agent loop events as Server-Sent Events."""
    session = get_session_registry().get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    # Normalize model: reject empty strings and values that are obviously not model IDs
    clean_model: str | None = model.strip() if model else None
    if not clean_model:
        clean_model = None

    user_settings = load_user_settings(context=get_context(), user_id=user_id)

    from api.services.computer_use.agent_loop import run_agent_loop

    def _generate():
        try:
            for event in run_agent_loop(
                session,
                task,
                model=clean_model,
                max_iterations=max_iterations,
                user_settings=user_settings,
            ):
                # Omit heavy screenshot bytes from the SSE text for non-screenshot events
                if event.get("event_type") != "screenshot":
                    payload = json.dumps(event)
                else:
                    # Send screenshot as a separate data field to avoid huge SSE lines
                    payload = json.dumps({
                        "event_type": "screenshot",
                        "iteration": event.get("iteration"),
                        "url": event.get("url"),
                        "screenshot_b64": event.get("screenshot_b64", ""),
                    })
                yield f"data: {payload}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'event_type': 'error', 'detail': str(exc)[:400]})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def close_session(
    session_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> None:
    """Close and destroy a Computer Use session."""
    removed = get_session_registry().close(session_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Session not found.")
