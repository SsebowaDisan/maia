"""Page monitor router — manage URLs for the Competitor Change Radar.

Endpoints:
  GET    /api/page-monitor/{agent_id}/urls         — list monitored URLs
  POST   /api/page-monitor/{agent_id}/urls         — add a URL
  DELETE /api/page-monitor/{agent_id}/urls         — remove a URL
  POST   /api/page-monitor/{agent_id}/urls/refresh — manually trigger a re-fetch
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, HttpUrl
from sqlmodel import Session

from api.auth import get_current_user_id
from api.context import get_context
from api.models.user import User
from api.services.marketplace.page_monitor import (
    add_monitored_url,
    list_monitored_urls,
    remove_monitored_url,
    upsert_snapshot,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/page-monitor", tags=["page-monitor"])


def _get_session():
    ctx = get_context()
    with Session(ctx.engine) as session:
        yield session


class AddUrlRequest(BaseModel):
    url: str


class RemoveUrlRequest(BaseModel):
    url: str


@router.get("/{agent_id}/urls")
def list_urls(
    agent_id: str,
    user: User = Depends(get_current_user_id),
    session: Session = Depends(_get_session),
):
    records = list_monitored_urls(user.tenant_id, agent_id, session)
    return [
        {
            "url": r.url,
            "content_hash": r.content_hash,
            "last_fetched_at": r.last_fetched_at.isoformat() if r.last_fetched_at else None,
        }
        for r in records
    ]


@router.post("/{agent_id}/urls", status_code=status.HTTP_201_CREATED)
def add_url(
    agent_id: str,
    body: AddUrlRequest,
    user: User = Depends(get_current_user_id),
    session: Session = Depends(_get_session),
):
    record = add_monitored_url(user.tenant_id, agent_id, body.url, session)
    return {"url": record.url, "id": record.id}


@router.delete("/{agent_id}/urls", status_code=status.HTTP_204_NO_CONTENT)
def remove_url(
    agent_id: str,
    body: RemoveUrlRequest,
    user: User = Depends(get_current_user_id),
    session: Session = Depends(_get_session),
):
    removed = remove_monitored_url(user.tenant_id, agent_id, body.url, session)
    if not removed:
        raise HTTPException(status_code=404, detail="URL not found")


@router.post("/{agent_id}/urls/refresh")
def refresh_urls(
    agent_id: str,
    user: User = Depends(get_current_user_id),
    session: Session = Depends(_get_session),
):
    """Manually trigger a re-fetch for all URLs belonging to this agent."""
    records = list_monitored_urls(user.tenant_id, agent_id, session)
    results = []
    for record in records:
        diff = upsert_snapshot(user.tenant_id, agent_id, record.url, session)
        results.append({"url": diff.url, "changed": diff.changed})
    return {"refreshed": len(results), "changes": [r for r in results if r["changed"]]}
