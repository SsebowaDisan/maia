"""B3-07 — Marketplace REST router.

Responsibility: HTTP layer for marketplace discovery, publishing, and installation.

Endpoints:
  GET    /api/marketplace/agents                   — list/search agents
  GET    /api/marketplace/agents/{agent_id}        — agent detail
  POST   /api/marketplace/agents                   — publish a new agent
  POST   /api/marketplace/agents/{agent_id}/submit — submit for review
  POST   /api/marketplace/agents/{agent_id}/approve — approve (admin)
  POST   /api/marketplace/agents/{agent_id}/reject  — reject (admin)
  POST   /api/marketplace/agents/{agent_id}/install — install into tenant
  DELETE /api/marketplace/agents/{agent_id}/install — uninstall
  GET    /api/marketplace/agents/{agent_id}/reviews — get reviews
  POST   /api/marketplace/agents/{agent_id}/reviews — submit review
  GET    /api/marketplace/updates                   — check for updates
  POST   /api/marketplace/updates/{agent_id}        — apply update
"""
from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from api.auth import get_current_user_id
from api.services.marketplace import registry, publisher, installer, versioning, reviews as reviews_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])


# ── Request bodies ─────────────────────────────────────────────────────────────

class PublishRequest(BaseModel):
    definition: dict[str, Any]
    metadata: dict[str, Any] = {}


class InstallRequest(BaseModel):
    version: str | None = None
    connector_mapping: dict[str, str] = {}


class ReviewRequest(BaseModel):
    rating: int
    review_text: str = ""


class RejectRequest(BaseModel):
    reason: str


class UpdateRequest(BaseModel):
    target_version: str | None = None


# ── Discovery ──────────────────────────────────────────────────────────────────

@router.get("/agents")
def list_agents(
    user_id: Annotated[str, Depends(get_current_user_id)],
    q: str | None = Query(default=None),
    tags: str | None = Query(default=None, description="Comma-separated tags"),
    required_connectors: str | None = Query(default=None),
    pricing: str | None = Query(default=None),
    has_computer_use: bool | None = Query(default=None),
    sort_by: str = Query(default="installs"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, le=100),
) -> list[dict[str, Any]]:
    offset = (page - 1) * limit
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    conn_list = [c.strip() for c in required_connectors.split(",")] if required_connectors else None

    if q:
        results = registry.search_marketplace_agents(q, limit=limit)
    else:
        results = registry.list_marketplace_agents(
            tags=tag_list,
            required_connectors=conn_list,
            pricing=pricing,  # type: ignore[arg-type]
            has_computer_use=has_computer_use,
            limit=limit,
            offset=offset,
        )

    return [_agent_summary(r) for r in results]


@router.get("/agents/{agent_id}")
def get_agent(
    agent_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    version: str | None = Query(default=None),
) -> dict[str, Any]:
    entry = registry.get_marketplace_agent(agent_id, version)
    if not entry:
        raise HTTPException(status_code=404, detail="Marketplace agent not found.")
    review_data = reviews_service.get_aggregate_rating(agent_id)
    return {**_agent_summary(entry), "definition": json.loads(entry.definition_json), "reviews": review_data}


# ── Publishing ─────────────────────────────────────────────────────────────────

@router.post("/agents", status_code=status.HTTP_201_CREATED)
def publish(
    body: PublishRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    entry = registry.publish_agent(user_id, body.definition, body.metadata)
    return {"id": entry.id, "agent_id": entry.agent_id, "status": entry.status}


@router.post("/agents/{agent_id}/submit")
def submit_for_review(
    agent_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    try:
        entry = publisher.submit_for_review(user_id, agent_id)
    except publisher.PublishValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.reason) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": entry.status, "agent_id": entry.agent_id}


@router.post("/agents/{agent_id}/approve")
def approve(
    agent_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    try:
        entry = publisher.approve_agent(agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": entry.status, "agent_id": entry.agent_id}


@router.post("/agents/{agent_id}/reject")
def reject(
    agent_id: str,
    body: RejectRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    try:
        entry = publisher.reject_agent(agent_id, body.reason)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": entry.status, "agent_id": entry.agent_id}


# ── Installation ───────────────────────────────────────────────────────────────

@router.post("/agents/{agent_id}/install")
def install(
    agent_id: str,
    body: InstallRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    result = installer.install_agent(
        user_id,
        user_id,
        agent_id,
        version=body.version,
        connector_mapping=body.connector_mapping,
    )
    if not result.success:
        return {
            "success": False,
            "agent_id": result.agent_id,
            "missing_connectors": result.missing_connectors,
            "error": result.error,
        }
    return {"success": True, "agent_id": result.agent_id}


@router.delete("/agents/{agent_id}/install", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def uninstall(
    agent_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> None:
    removed = installer.uninstall_agent(user_id, agent_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Agent not installed.")


# ── Reviews ────────────────────────────────────────────────────────────────────

@router.get("/agents/{agent_id}/reviews")
def get_reviews(
    agent_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    return [
        {
            "id": r.id,
            "rating": r.rating,
            "review_text": r.review_text,
            "publisher_response": r.publisher_response,
            "created_at": r.created_at,
        }
        for r in reviews_service.get_reviews(agent_id, limit=limit, offset=offset)
    ]


@router.post("/agents/{agent_id}/reviews", status_code=status.HTTP_201_CREATED)
def submit_review(
    agent_id: str,
    body: ReviewRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    try:
        review = reviews_service.submit_review(user_id, agent_id, body.rating, body.review_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": review.id, "rating": review.rating}


# ── Updates ────────────────────────────────────────────────────────────────────

@router.get("/updates")
def check_updates(
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> list[dict[str, Any]]:
    return versioning.check_for_updates(user_id)


@router.post("/updates/{agent_id}")
def apply_update(
    agent_id: str,
    body: UpdateRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    return versioning.update_agent(user_id, user_id, agent_id, body.target_version)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _agent_summary(entry: Any) -> dict[str, Any]:
    return {
        "id": entry.id,
        "agent_id": entry.agent_id,
        "name": entry.name,
        "description": entry.description,
        "version": entry.version,
        "tags": json.loads(entry.tags_json),
        "required_connectors": json.loads(entry.required_connectors_json),
        "pricing_tier": entry.pricing_tier,
        "status": entry.status,
        "install_count": entry.install_count,
        "avg_rating": entry.avg_rating,
        "rating_count": entry.rating_count,
        "has_computer_use": entry.has_computer_use,
        "verified": entry.verified,
        "published_at": entry.published_at,
    }
