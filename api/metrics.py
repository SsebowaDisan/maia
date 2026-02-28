from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from api.services.agent.observability import get_agent_observability

router = APIRouter(tags=["metrics"])


@router.get("/api/metrics")
def metrics() -> PlainTextResponse:
    return PlainTextResponse(
        content=get_agent_observability().prometheus_text(),
        media_type="text/plain; version=0.0.4",
    )

