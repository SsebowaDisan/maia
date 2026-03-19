"""B3-07 â€” Marketplace REST router.

Responsibility: HTTP layer for marketplace discovery, publishing, and installation.

Endpoints:
  GET    /api/marketplace/agents                   â€” list/search agents
  GET    /api/marketplace/agents/{agent_id}        â€” agent detail
  POST   /api/marketplace/agents                   â€” publish a new agent
  POST   /api/marketplace/agents/{agent_id}/submit â€” submit for review
  POST   /api/marketplace/agents/{agent_id}/approve â€” approve (admin)
  POST   /api/marketplace/agents/{agent_id}/reject  â€” reject (admin)
  POST   /api/marketplace/agents/{agent_id}/install â€” install into tenant
  DELETE /api/marketplace/agents/{agent_id}/install â€” uninstall
  GET    /api/marketplace/agents/{agent_id}/reviews â€” get reviews
  POST   /api/marketplace/agents/{agent_id}/reviews â€” submit review
  GET    /api/marketplace/updates                   â€” check for updates
  POST   /api/marketplace/updates/{agent_id}        â€” apply update
"""
from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.auth import get_current_user, get_current_user_id, require_super_admin
from api.models.creator_profile import CreatorProfile
from api.models.user import User
from api.services.auth.tokens import TokenError, decode_access_token
from api.services.marketplace.developers import get_developer_status
from api.services.agents import definition_store
from api.services.marketplace import registry, publisher, installer, versioning, reviews as reviews_service
from api.services.marketplace import notifications as notifications_service
from api.services.marketplace.abuse_prevention import (
    DailyQuotaExceededError,
    consume_daily_quota,
)
from ktem.db.engine import engine
from sqlmodel import Session as _Session, select as _select

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])
_bearer = HTTPBearer(auto_error=False)


# â”€â”€ Request bodies â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class PublishRequest(BaseModel):
    definition: dict[str, Any]
    metadata: dict[str, Any] = {}


class InstallRequest(BaseModel):
    version: str | None = None
    connector_mapping: dict[str, str] = {}
    gate_policies: dict[str, bool] = {}  # {connector_id: require_approval}


class ReviewRequest(BaseModel):
    rating: int
    review_text: str = ""


class RejectRequest(BaseModel):
    reason: str


class ReviseRequest(BaseModel):
    definition: dict[str, Any]
    changelog: str = ""


class UpdateRequest(BaseModel):
    target_version: str | None = None


def _resolve_optional_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    user_id_query: Annotated[str | None, Query(alias="user_id")] = None,
) -> str | None:
    direct = str(x_user_id or user_id_query or "").strip()
    if direct:
        return direct
    if not credentials or not credentials.credentials:
        return None
    token = str(credentials.credentials).strip()
    if not token or token.startswith("mk_"):
        return None
    try:
        payload = decode_access_token(token)
    except TokenError:
        return None
    subject = str(payload.get("sub") or "").strip()
    return subject or None


# â”€â”€ Discovery â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/agents")
def list_agents(
    user_id: Annotated[str | None, Depends(_resolve_optional_user_id)],
    q: str | None = Query(default=None),
    category: str | None = Query(default=None),
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
        results = registry.search_marketplace_agents(q, limit=limit, max_connectors=1)
    else:
        results = registry.list_marketplace_agents(
            tags=tag_list,
            required_connectors=conn_list,
            max_connectors=1,
            pricing=pricing,  # type: ignore[arg-type]
            has_computer_use=has_computer_use,
            limit=limit,
            offset=offset,
        )

    if category:
        normalized_category = str(category).strip().lower()
        results = [
            row
            for row in results
            if str(json.loads(row.definition_json or "{}").get("category") or "").strip().lower()
            == normalized_category
            or any(str(tag).strip().lower() == normalized_category for tag in json.loads(row.tags_json or "[]"))
        ]

    if sort_by == "rating":
        results = sorted(
            results,
            key=lambda row: (float(row.avg_rating or 0.0), int(row.rating_count or 0)),
            reverse=True,
        )
    elif sort_by == "newest":
        results = sorted(results, key=lambda row: float(row.created_at or 0), reverse=True)
    else:
        results = sorted(
            results,
            key=lambda row: (int(row.install_count or 0), float(row.avg_rating or 0.0)),
            reverse=True,
        )
    installed_ids = {r.agent_id for r in definition_store.list_agents(user_id)} if user_id else set()
    creator_lookup = _creator_profile_lookup([str(row.publisher_id or "") for row in results])
    return [
        _agent_summary(r, installed_ids, tenant_id=user_id, creator_lookup=creator_lookup)
        for r in results
    ]


@router.get("/agents/{agent_id}")
def get_agent(
    agent_id: str,
    user_id: Annotated[str | None, Depends(_resolve_optional_user_id)],
    version: str | None = Query(default=None),
) -> dict[str, Any]:
    entry = registry.get_marketplace_agent(agent_id, version)
    if not entry:
        raise HTTPException(status_code=404, detail="Marketplace agent not found.")
    installed_ids = {r.agent_id for r in definition_store.list_agents(user_id)} if user_id else set()
    review_data = reviews_service.get_aggregate_rating(agent_id)
    creator_lookup = _creator_profile_lookup([str(entry.publisher_id or "")])
    definition = json.loads(entry.definition_json)
    readme_md = str(
        definition.get("readme_md")
        or definition.get("readme")
        or definition.get("overview")
        or entry.description
        or ""
    ).strip()
    screenshots = definition.get("screenshots") or []
    if not isinstance(screenshots, list):
        screenshots = []
    return {
        **_agent_summary(
            entry,
            installed_ids,
            tenant_id=user_id,
            creator_lookup=creator_lookup,
        ),
        "definition": definition,
        "readme_md": readme_md,
        "screenshots": [str(item).strip() for item in screenshots if str(item).strip()],
        "run_success_rate": _estimate_run_success_rate(entry.agent_id),
        "reviews": review_data,
    }


# â”€â”€ Publishing â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.post("/agents", status_code=status.HTTP_201_CREATED)
def publish(
    body: PublishRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    dev_status = get_developer_status(user.id)
    if dev_status not in ("verified", "trusted_publisher") and user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Developer access required. Apply at the Developer Portal.",
        )
    try:
        consume_daily_quota(
            user_id=user.id,
            action_key="marketplace_agent_publish",
            daily_limit=10,
        )
    except DailyQuotaExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    entry = registry.publish_agent(user.id, body.definition, body.metadata)
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
    _admin: Annotated[User, Depends(require_super_admin)],
) -> dict[str, Any]:
    """Approve a marketplace agent submission. Maia super-admins only."""
    try:
        entry = publisher.approve_agent(agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": entry.status, "agent_id": entry.agent_id}


@router.post("/agents/{agent_id}/revise")
def revise(
    agent_id: str,
    body: ReviseRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    """Revise a rejected agent definition and re-enter the review queue."""
    try:
        entry = publisher.revise_agent(user_id, agent_id, body.definition, body.changelog)
    except publisher.PublishValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.reason) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "status": entry.status,
        "agent_id": entry.agent_id,
        "revision_count": entry.revision_count,
    }


@router.post("/agents/{agent_id}/reject")
def reject(
    agent_id: str,
    body: RejectRequest,
    _admin: Annotated[User, Depends(require_super_admin)],
) -> dict[str, Any]:
    """Reject a marketplace agent submission. Maia super-admins only."""
    try:
        entry = publisher.reject_agent(agent_id, body.reason)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": entry.status, "agent_id": entry.agent_id}


# â”€â”€ Installation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.post("/agents/{agent_id}/install/preflight")
def install_preflight(
    agent_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    version: str | None = None,
) -> dict[str, Any]:
    """B3 â€” Dry-run check before install.

    Returns whether the agent can be installed in one click (all connectors
    available / auto-mappable) or what is blocking it.  Does NOT write to DB.
    """
    result = installer.preflight_install(user_id, agent_id, version=version)
    return {
        "can_install_immediately": result.can_install_immediately,
        "already_installed": result.already_installed,
        "missing_connectors": result.missing_connectors,
        "auto_mapped": result.auto_mapped,
        "agent_not_found": result.agent_not_found,
    }


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
        gate_policies=body.gate_policies,
    )
    if not result.success:
        return {
            "success": False,
            "agent_id": result.agent_id,
            "missing_connectors": result.missing_connectors,
            "error": result.error,
        }
    # B1 â€” return the full installed agent record so the frontend can update
    # local state immediately without a follow-up GET /api/agents refetch.
    return {
        "success": True,
        "agent_id": result.agent_id,
        "description": result.description,
        "trigger_family": result.trigger_family,
        "already_installed": result.already_installed,
        "auto_mapped_connectors": result.auto_mapped_connectors,
        "installed_agent": result.installed_record,
    }


@router.delete("/agents/{agent_id}/install", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def uninstall(
    agent_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> None:
    removed = installer.uninstall_agent(user_id, agent_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Agent not installed.")


# â”€â”€ Reviews â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/agents/{agent_id}/reviews")
def get_reviews(
    agent_id: str,
    _user_id: Annotated[str | None, Depends(_resolve_optional_user_id)],
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


@router.post(
    "/agents/{agent_id}/reviews/{review_id}/flag",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def flag_review(
    agent_id: str,
    review_id: str,
    _user_id: Annotated[str, Depends(get_current_user_id)],
) -> None:
    review_rows = reviews_service.get_reviews(agent_id, limit=500, offset=0)
    if not any(str(row.id) == review_id for row in review_rows):
        raise HTTPException(status_code=404, detail="Review not found for this agent.")
    if not reviews_service.flag_review(review_id):
        raise HTTPException(status_code=404, detail="Review not found.")


# â”€â”€ Updates â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/agents/{agent_id}/versions")
def get_version_history(
    agent_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> list[dict[str, Any]]:
    """Return full version history for an agent (changelogs, statuses, timestamps)."""
    return registry.get_version_history(agent_id)


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


# â”€â”€ Admin review queue (B5) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class ClaimRequest(BaseModel):
    claim: bool = True  # True = claim, False = unclaim


@router.get("/admin/review-queue")
def admin_review_queue(
    _admin: Annotated[User, Depends(require_super_admin)],
    status_filter: str = Query(default="pending_review", alias="status"),
) -> list[dict[str, Any]]:
    """Return the admin review queue sorted oldest-first. super_admin only."""
    from api.services.marketplace.registry import MarketplaceAgent as _MA
    valid = {"pending_review", "approved", "rejected", "published", "deprecated"}
    sf = status_filter if status_filter in valid else "pending_review"
    with _Session(engine) as session:
        rows = session.exec(
            _select(_MA)
            .where(_MA.status == sf)
            .order_by(_MA.created_at.asc())  # type: ignore[attr-defined]
        ).all()
    result = []
    creator_lookup = _creator_profile_lookup([str(row.publisher_id or "") for row in rows])
    for r in rows:
        result.append({
            **_agent_summary(r, creator_lookup=creator_lookup),
            "definition": json.loads(r.definition_json),
            "rejection_reason": r.rejection_reason,
            "revision_count": r.revision_count,
            "reviewer_id": getattr(r, "reviewer_id", None),
            "review_started_at": getattr(r, "review_started_at", None),
        })
    return result


@router.post("/admin/review-queue/{agent_id}/claim", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def claim_review(
    agent_id: str,
    body: ClaimRequest,
    admin: Annotated[User, Depends(require_super_admin)],
) -> None:
    """Claim or unclaim a review to prevent double-reviewing. super_admin only."""
    import time as _t
    from sqlmodel import Session as _Session
    from api.services.marketplace.registry import MarketplaceAgent as _MA
    with _Session(engine) as session:
        entry = session.exec(
            _select(_MA).where(_MA.agent_id == agent_id)
        ).first()
        if not entry:
            raise HTTPException(status_code=404, detail="Marketplace agent not found.")
        if body.claim:
            if getattr(entry, "reviewer_id", None) and entry.reviewer_id != admin.id:
                raise HTTPException(
                    status_code=409,
                    detail=f"Review already claimed by another admin.",
                )
            entry.reviewer_id = admin.id
            entry.review_started_at = _t.time()
        else:
            entry.reviewer_id = None
            entry.review_started_at = None
        session.add(entry)
        session.commit()


# â”€â”€ Notifications â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/notifications")
def list_notifications(
    user_id: Annotated[str, Depends(get_current_user_id)],
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, le=200),
) -> list[dict[str, Any]]:
    """Return in-platform marketplace notifications for the current user."""
    records = notifications_service.list_notifications(user_id, unread_only=unread_only, limit=limit)
    return [
        {
            "id": r.id,
            "agent_id": r.agent_id,
            "agent_name": r.agent_name,
            "event_type": r.event_type,
            "message": r.message,
            "detail": r.detail,
            "is_read": r.is_read,
            "created_at": r.created_at,
        }
        for r in records
    ]


@router.get("/notifications/unread-count")
def get_unread_count(
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, int]:
    return {"count": notifications_service.unread_count(user_id)}


@router.post("/notifications/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def mark_notification_read(
    notification_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> None:
    if not notifications_service.mark_read(notification_id, user_id):
        raise HTTPException(status_code=404, detail="Notification not found.")


@router.post("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def mark_all_notifications_read(
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> None:
    notifications_service.mark_all_read(user_id)


# â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _agent_summary(
    entry: Any,
    installed_ids: set[str] | None = None,
    tenant_id: str | None = None,
    creator_lookup: dict[str, CreatorProfile] | None = None,
) -> dict[str, Any]:
    required_connectors: list[str] = json.loads(entry.required_connectors_json)
    tags = json.loads(entry.tags_json)
    creator = (creator_lookup or {}).get(str(entry.publisher_id or ""))
    definition = json.loads(entry.definition_json or "{}")
    readme_md = str(
        definition.get("readme_md")
        or definition.get("readme")
        or definition.get("overview")
        or entry.description
        or ""
    ).strip()
    screenshots = definition.get("screenshots") or []
    if not isinstance(screenshots, list):
        screenshots = []
    category = str(definition.get("category") or "").strip().lower()
    if not category:
        category = str(tags[0]).strip().lower() if tags else "other"

    # B6 - per-connector connection state for this tenant
    connector_status: dict[str, str] = {}
    if tenant_id and required_connectors:
        connector_status = installer.get_tenant_connector_status(tenant_id, required_connectors)

    return {
        "id": entry.id,
        "agent_id": entry.agent_id,
        "name": entry.name,
        "description": entry.description,
        "version": entry.version,
        "tags": tags,
        "category": category,
        "required_connectors": required_connectors,
        "connector_status": connector_status,
        "pricing_tier": entry.pricing_tier,
        "status": entry.status,
        "install_count": entry.install_count,
        "avg_rating": entry.avg_rating,
        "rating_count": entry.rating_count,
        "has_computer_use": entry.has_computer_use,
        "verified": entry.verified,
        "published_at": entry.published_at,
        "is_installed": entry.agent_id in installed_ids if installed_ids is not None else False,
        "creator_username": creator.username if creator else "",
        "creator_display_name": creator.display_name if creator else "",
        "creator_avatar_url": creator.avatar_url if creator else "",
        "run_success_rate": _estimate_run_success_rate(entry.agent_id),
        "readme_md": readme_md,
        "screenshots": [str(item).strip() for item in screenshots if str(item).strip()],
    }


def _creator_profile_lookup(user_ids: list[str]) -> dict[str, CreatorProfile]:
    normalized = [uid for uid in {str(value or "").strip() for value in user_ids} if uid]
    if not normalized:
        return {}
    with _Session(engine) as session:
        rows = session.exec(
            _select(CreatorProfile).where(CreatorProfile.user_id.in_(normalized))
        ).all()
    return {row.user_id: row for row in rows}


def _estimate_run_success_rate(agent_id: str) -> float:
    entry = registry.get_marketplace_agent(agent_id)
    if not entry:
        return 0.0
    installs = int(entry.install_count or 0)
    if installs <= 0:
        return 0.0
    return round(min(0.99, 0.82 + min(installs, 500) * 0.00028), 3)


def _list_marketplace_agents_by_publisher(publisher_id: str) -> list[dict[str, Any]]:
    rows = registry.list_marketplace_agents(
        publisher_id=publisher_id,
        status="published",
        limit=120,
        offset=0,
    )
    creator_lookup = _creator_profile_lookup([publisher_id])
    return [_agent_summary(row, creator_lookup=creator_lookup) for row in rows]


def _list_marketplace_agents_sorted(
    *,
    sort: str = "installs",
    limit: int = 20,
) -> list[dict[str, Any]]:
    rows = registry.list_marketplace_agents(limit=min(max(limit, 1), 200), offset=0)
    if sort == "newest":
        rows = sorted(rows, key=lambda row: float(row.created_at or 0), reverse=True)
    elif sort == "rating":
        rows = sorted(
            rows,
            key=lambda row: (float(row.avg_rating or 0.0), int(row.rating_count or 0)),
            reverse=True,
        )
    else:
        rows = sorted(
            rows,
            key=lambda row: (int(row.install_count or 0), float(row.avg_rating or 0.0)),
            reverse=True,
        )
    creator_lookup = _creator_profile_lookup([str(row.publisher_id or "") for row in rows])
    return [_agent_summary(row, creator_lookup=creator_lookup) for row in rows[:limit]]


def _search_marketplace_agents(*, query: str, limit: int = 20) -> list[dict[str, Any]]:
    rows = registry.search_marketplace_agents(query, limit=min(max(limit, 1), 100))
    creator_lookup = _creator_profile_lookup([str(row.publisher_id or "") for row in rows])
    return [_agent_summary(row, creator_lookup=creator_lookup) for row in rows[:limit]]
