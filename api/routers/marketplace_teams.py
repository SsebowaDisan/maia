"""Marketplace workflows/teams API.

Supports both route families for compatibility:
  - /api/marketplace/workflows/*
  - /api/marketplace/teams/*
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.auth import get_current_user_id
from api.services.marketplace.abuse_prevention import DailyQuotaExceededError
from api.services.marketplace.feed import record_feed_event
from api.services.marketplace.workflow_publisher import (
    get_published_workflow,
    install_workflow,
    list_published_workflows,
    list_related_workflows,
    publish_workflow,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketplace", tags=["marketplace-workflows"])


class PublishWorkflowRequest(BaseModel):
    source_workflow_id: str
    name: str = Field(max_length=120)
    description: str = Field(default="", max_length=500)
    readme_md: str = Field(default="")
    definition: dict[str, Any]
    category: str = Field(default="other", max_length=40)
    tags: list[str] = Field(default_factory=list)
    screenshots: list[str] = Field(default_factory=list)


class ReviewRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    review_text: str = Field(default="", max_length=1000)


def _publish(
    *,
    body: PublishWorkflowRequest,
    user_id: str,
) -> dict[str, Any]:
    try:
        return publish_workflow(
            creator_id=user_id,
            source_workflow_id=body.source_workflow_id,
            name=body.name,
            description=body.description,
            readme_md=body.readme_md,
            definition=body.definition,
            category=body.category,
            tags=body.tags,
            screenshots=body.screenshots,
        )
    except DailyQuotaExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


def _list(*, category: str | None, q: str | None, sort: str, limit: int) -> list[dict[str, Any]]:
    return list_published_workflows(
        category=category,
        q=q,
        sort=sort,
        limit=min(limit, 100),
    )


def _get_or_404(slug: str) -> dict[str, Any]:
    result = get_published_workflow(slug)
    if not result:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    return result


def _install(*, slug: str, user_id: str) -> dict[str, Any]:
    try:
        return install_workflow(slug=slug, tenant_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _list_reviews(slug: str, limit: int = 20) -> list[dict[str, Any]]:
    workflow = _get_or_404(slug)
    try:
        from api.services.marketplace.reviews import list_reviews as _list

        return _list(agent_id=workflow["id"], limit=min(limit, 50))
    except Exception:
        return []


def _submit_review(*, slug: str, body: ReviewRequest, user_id: str) -> dict[str, Any]:
    workflow = _get_or_404(slug)
    try:
        from api.services.marketplace.reviews import submit_review as _submit

        review = _submit(
            agent_id=workflow["id"],
            user_id=user_id,
            rating=body.rating,
            review_text=body.review_text,
        )
        try:
            record_feed_event(
                creator_user_id=str(workflow.get("creator_id") or ""),
                actor_user_id=user_id,
                event_type="team_review_posted",
                entity_type="team",
                entity_id=str(workflow.get("id") or ""),
                slug=str(workflow.get("slug") or ""),
                title=str(workflow.get("name") or "Team review"),
                summary=f"New {body.rating}-star review posted.",
                payload={"rating": body.rating, "review_id": str(getattr(review, "id", ""))},
            )
        except Exception:
            logger.debug("Failed to emit team review feed event", exc_info=True)
        return {
            "id": str(getattr(review, "id", "")),
            "rating": int(getattr(review, "rating", body.rating)),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _flag_review(*, slug: str, review_id: str) -> None:
    workflow = _get_or_404(slug)
    try:
        from api.services.marketplace.reviews import flag_review as _flag
        from api.services.marketplace.reviews import get_reviews as _list

        review_rows = _list(agent_id=workflow["id"], limit=500, offset=0)
        if not any(str(row.id) == review_id for row in review_rows):
            raise HTTPException(status_code=404, detail="Review not found for this team.")
        if not _flag(review_id):
            raise HTTPException(status_code=404, detail="Review not found.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# Workflows routes
@router.post("/workflows", status_code=status.HTTP_201_CREATED)
def publish_workflow_route(
    body: PublishWorkflowRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    return _publish(body=body, user_id=user_id)


@router.get("/workflows")
def list_workflows_route(
    category: str | None = None,
    q: str | None = None,
    sort: str = "popular",
    limit: int = 50,
) -> list[dict[str, Any]]:
    return _list(category=category, q=q, sort=sort, limit=limit)


@router.get("/workflows/{slug}")
def get_workflow_route(slug: str) -> dict[str, Any]:
    return _get_or_404(slug)


@router.get("/workflows/{slug}/related")
def get_related_workflows(slug: str, limit: int = 6) -> list[dict[str, Any]]:
    return list_related_workflows(slug, limit=min(max(limit, 1), 20))


@router.post("/workflows/{slug}/install")
def install_workflow_route(
    slug: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    return _install(slug=slug, user_id=user_id)


@router.get("/workflows/{slug}/reviews")
def list_workflow_reviews_route(slug: str, limit: int = 20) -> list[dict[str, Any]]:
    return _list_reviews(slug, limit=limit)


@router.post("/workflows/{slug}/reviews", status_code=status.HTTP_201_CREATED)
def submit_workflow_review_route(
    slug: str,
    body: ReviewRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    return _submit_review(slug=slug, body=body, user_id=user_id)


@router.post(
    "/workflows/{slug}/reviews/{review_id}/flag",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def flag_workflow_review_route(
    slug: str,
    review_id: str,
    _user_id: str = Depends(get_current_user_id),
) -> None:
    _flag_review(slug=slug, review_id=review_id)


# Teams alias routes for backward compatibility
@router.post("/teams", status_code=status.HTTP_201_CREATED)
def publish_team_route(
    body: PublishWorkflowRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    return _publish(body=body, user_id=user_id)


@router.get("/teams")
def list_teams_route(
    category: str | None = None,
    q: str | None = None,
    sort: str = "popular",
    limit: int = 50,
) -> list[dict[str, Any]]:
    return _list(category=category, q=q, sort=sort, limit=limit)


@router.get("/teams/{slug}")
def get_team_route(slug: str) -> dict[str, Any]:
    return _get_or_404(slug)


@router.get("/teams/{slug}/related")
def get_related_teams(slug: str, limit: int = 6) -> list[dict[str, Any]]:
    return list_related_workflows(slug, limit=min(max(limit, 1), 20))


@router.post("/teams/{slug}/install")
def install_team_route(
    slug: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    return _install(slug=slug, user_id=user_id)


@router.get("/teams/{slug}/reviews")
def list_team_reviews_route(slug: str, limit: int = 20) -> list[dict[str, Any]]:
    return _list_reviews(slug, limit=limit)


@router.post("/teams/{slug}/reviews", status_code=status.HTTP_201_CREATED)
def submit_team_review_route(
    slug: str,
    body: ReviewRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    return _submit_review(slug=slug, body=body, user_id=user_id)


@router.post(
    "/teams/{slug}/reviews/{review_id}/flag",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def flag_team_review_route(
    slug: str,
    review_id: str,
    _user_id: str = Depends(get_current_user_id),
) -> None:
    _flag_review(slug=slug, review_id=review_id)
