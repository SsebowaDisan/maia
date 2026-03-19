"""Feed event helpers for creator and marketplace activity."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlmodel import Session, SQLModel, col, select

from api.models.creator_follow import CreatorFollow
from api.models.creator_profile import CreatorProfile
from api.models.feed_event import FeedEvent
from ktem.db.engine import engine


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


def record_feed_event(
    *,
    creator_user_id: str,
    actor_user_id: str,
    event_type: str,
    entity_type: str,
    entity_id: str,
    slug: str = "",
    title: str = "",
    summary: str = "",
    payload: dict[str, Any] | None = None,
) -> FeedEvent:
    _ensure_tables()
    event = FeedEvent(
        creator_user_id=creator_user_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        slug=slug,
        title=title[:160],
        summary=summary[:500],
        payload=payload or {},
        date_created=datetime.utcnow(),
    )
    with Session(engine) as session:
        session.add(event)
        session.commit()
        session.refresh(event)
    return event


def list_creator_activity(creator_user_id: str, *, limit: int = 30) -> list[dict[str, Any]]:
    _ensure_tables()
    with Session(engine) as session:
        rows = session.exec(
            select(FeedEvent)
            .where(FeedEvent.creator_user_id == creator_user_id)
            .order_by(col(FeedEvent.date_created).desc())
            .limit(min(max(limit, 1), 100))
        ).all()
        creators = {
            c.user_id: c
            for c in session.exec(
                select(CreatorProfile).where(CreatorProfile.user_id.in_([row.creator_user_id for row in rows]))
            ).all()
        }
    return [_to_dict(row, creators.get(row.creator_user_id)) for row in rows]


def list_feed_for_user(user_id: str, *, limit: int = 30) -> list[dict[str, Any]]:
    _ensure_tables()
    with Session(engine) as session:
        followed_creator_ids = [
            row.creator_user_id
            for row in session.exec(
                select(CreatorFollow).where(CreatorFollow.follower_user_id == user_id)
            ).all()
        ]
        if not followed_creator_ids:
            return []
        rows = session.exec(
            select(FeedEvent)
            .where(FeedEvent.creator_user_id.in_(followed_creator_ids))
            .order_by(col(FeedEvent.date_created).desc())
            .limit(min(max(limit, 1), 100))
        ).all()
        creators = {
            c.user_id: c
            for c in session.exec(
                select(CreatorProfile).where(CreatorProfile.user_id.in_(followed_creator_ids))
            ).all()
        }
    return [_to_dict(row, creators.get(row.creator_user_id)) for row in rows]


def _to_dict(row: FeedEvent, creator: CreatorProfile | None) -> dict[str, Any]:
    return {
        "id": row.id,
        "event_type": row.event_type,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "slug": row.slug,
        "title": row.title,
        "summary": row.summary,
        "payload": row.payload or {},
        "timestamp": row.date_created.isoformat() if row.date_created else "",
        "creator_username": creator.username if creator else "",
        "creator_display_name": creator.display_name if creator else "",
        "creator_avatar_url": creator.avatar_url if creator else "",
        "creator_user_id": row.creator_user_id,
        "actor_user_id": row.actor_user_id,
    }
