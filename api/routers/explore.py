"""Explore and discovery API."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, SQLModel, col, select

from api.auth import get_current_user_id
from api.models.creator_follow import CreatorFollow
from api.models.creator_profile import CreatorProfile
from api.models.published_workflow import PublishedWorkflow
from api.services.marketplace.feed import list_feed_for_user
from ktem.db.engine import engine

logger = logging.getLogger(__name__)
router = APIRouter(tags=["explore"])


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


def _team_summary(row: PublishedWorkflow, creator: CreatorProfile | None = None) -> dict[str, Any]:
    return {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "description": row.description,
        "category": row.category,
        "tags": row.tags or [],
        "agent_count": len(row.agent_lineup or []),
        "install_count": row.install_count,
        "avg_rating": row.avg_rating,
        "review_count": row.review_count,
        "required_connectors": row.required_connectors or [],
        "creator_username": creator.username if creator else "",
        "creator_display_name": creator.display_name if creator else "",
        "creator_avatar_url": creator.avatar_url if creator else "",
        "date_created": row.date_created.isoformat() if row.date_created else None,
    }


def _creator_summary(row: CreatorProfile) -> dict[str, Any]:
    return {
        "user_id": row.user_id,
        "username": row.username,
        "display_name": row.display_name,
        "avatar_url": row.avatar_url,
        "follower_count": row.follower_count,
        "total_installs": row.total_installs,
        "published_agent_count": row.published_agent_count,
        "published_team_count": row.published_team_count,
    }


@router.get("/api/explore")
def explore_homepage(limit: int = 8) -> dict[str, Any]:
    _ensure_tables()
    cap = min(max(limit, 1), 24)
    with Session(engine) as session:
        published = session.exec(
            select(PublishedWorkflow).where(PublishedWorkflow.status == "published").limit(400)
        ).all()
        creators = {
            row.user_id: row
            for row in session.exec(select(CreatorProfile).limit(300)).all()
        }

    published_sorted_by_installs = sorted(
        published, key=lambda row: int(row.install_count or 0), reverse=True
    )
    published_sorted_by_date = sorted(
        published, key=lambda row: row.date_created or datetime.min, reverse=True
    )

    trending_teams = [
        _team_summary(row, creators.get(row.creator_id))
        for row in published_sorted_by_installs[:cap]
    ]
    new_teams = [
        _team_summary(row, creators.get(row.creator_id))
        for row in published_sorted_by_date[:cap]
    ]

    trending_agents: list[dict[str, Any]] = []
    new_agents: list[dict[str, Any]] = []
    categories: list[dict[str, Any]] = []
    try:
        from api.routers.marketplace import _list_marketplace_agents_sorted

        trending_agents = _list_marketplace_agents_sorted(sort="installs", limit=cap)
        new_agents = _list_marketplace_agents_sorted(sort="newest", limit=cap)
        category_map: dict[str, list[dict[str, Any]]] = {}
        for agent in _list_marketplace_agents_sorted(sort="installs", limit=120):
            category = str(agent.get("category") or "other").strip().lower()
            bucket = category_map.setdefault(category, [])
            if len(bucket) < 4:
                bucket.append(agent)
        categories = [
            {"id": category, "label": category.title(), "agents": rows}
            for category, rows in category_map.items()
        ]
    except Exception:
        logger.debug("Unable to enrich explore page with agent categories", exc_info=True)

    featured_creators = [
        _creator_summary(row)
        for row in sorted(
            creators.values(), key=lambda item: int(item.total_installs or 0), reverse=True
        )[:cap]
    ]

    return {
        "trending_agents": trending_agents,
        "trending_teams": trending_teams,
        "new_agents": new_agents,
        "new_teams": new_teams,
        "categories": categories,
        "featured_creators": featured_creators,
    }


@router.get("/api/marketplace/explore")
def marketplace_explore(limit: int = 8) -> dict[str, Any]:
    return explore_homepage(limit=limit)


@router.get("/api/explore/search")
def search_explore(
    q: str = "",
    type: str = Query(default="all", alias="type"),
    limit: int = 20,
) -> dict[str, Any]:
    _ensure_tables()
    query = str(q or "").strip().lower()
    cap = min(max(limit, 1), 50)
    results: dict[str, Any] = {"query": q, "agents": [], "teams": [], "creators": []}
    if not query:
        return results

    if type in ("all", "teams"):
        from api.services.marketplace.workflow_publisher import list_published_workflows

        results["teams"] = list_published_workflows(q=query, limit=cap, sort="trending")

    if type in ("all", "creators"):
        with Session(engine) as session:
            rows = session.exec(
                select(CreatorProfile)
                .where(
                    col(CreatorProfile.username).ilike(f"%{query}%")
                    | col(CreatorProfile.display_name).ilike(f"%{query}%")
                    | col(CreatorProfile.bio).ilike(f"%{query}%")
                )
                .limit(cap)
            ).all()
        results["creators"] = [_creator_summary(row) for row in rows]

    if type in ("all", "agents"):
        try:
            from api.routers.marketplace import _search_marketplace_agents

            results["agents"] = _search_marketplace_agents(query=query, limit=cap)
        except Exception:
            results["agents"] = []

    return results


@router.post("/api/creators/{username}/follow", status_code=status.HTTP_201_CREATED)
def follow_creator(
    username: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    _ensure_tables()
    with Session(engine) as session:
        creator = session.exec(
            select(CreatorProfile).where(CreatorProfile.username == username.strip().lower())
        ).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found.")
        if creator.user_id == user_id:
            raise HTTPException(status_code=400, detail="Cannot follow yourself.")

        existing = session.exec(
            select(CreatorFollow).where(
                CreatorFollow.follower_user_id == user_id,
                CreatorFollow.creator_user_id == creator.user_id,
            )
        ).first()
        if existing:
            return {"status": "already_following"}

        session.add(CreatorFollow(follower_user_id=user_id, creator_user_id=creator.user_id))
        creator.follower_count = int(creator.follower_count or 0) + 1
        session.add(creator)
        session.commit()
    return {"status": "following", "username": creator.username}


@router.delete("/api/creators/{username}/follow", status_code=status.HTTP_200_OK)
def unfollow_creator(
    username: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    _ensure_tables()
    with Session(engine) as session:
        creator = session.exec(
            select(CreatorProfile).where(CreatorProfile.username == username.strip().lower())
        ).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found.")

        follow = session.exec(
            select(CreatorFollow).where(
                CreatorFollow.follower_user_id == user_id,
                CreatorFollow.creator_user_id == creator.user_id,
            )
        ).first()
        if not follow:
            return {"status": "not_following"}

        session.delete(follow)
        creator.follower_count = max(0, int(creator.follower_count or 0) - 1)
        session.add(creator)
        session.commit()
    return {"status": "unfollowed", "username": creator.username}


@router.get("/api/feed")
def get_feed(
    user_id: str = Depends(get_current_user_id),
    limit: int = 30,
) -> list[dict[str, Any]]:
    _ensure_tables()
    return list_feed_for_user(user_id, limit=min(max(limit, 1), 100))
