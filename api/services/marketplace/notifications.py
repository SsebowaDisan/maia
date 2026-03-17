"""B3 — Approval event notifications.

Responsibility: persist in-platform notifications for marketplace status
transitions (submitted, approved, rejected, published) and expose a simple
read/dismiss API consumed by the notification bell in the frontend.

Storage: lightweight SQLModel table `maia_marketplace_notification`.
Delivery: in-platform only (email hooks can be wired via `on_notify` override).
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Optional, Sequence

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine

logger = logging.getLogger(__name__)


class MarketplaceNotification(SQLModel, table=True):
    __tablename__ = "maia_marketplace_notification"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    # Recipient — the publisher / user who should see this notification
    user_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    agent_name: str = ""
    # Event type: submitted | approved | rejected | published
    event_type: str
    # Human-readable message shown in the notification bell
    message: str
    # Optional rejection reason (populated on rejected events)
    detail: str = ""
    is_read: bool = False
    created_at: float = Field(default_factory=time.time)


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


# ── Public API ──────────────────────────────────────────────────────────────────

def notify(
    user_id: str,
    agent_id: str,
    agent_name: str,
    event_type: str,
    detail: str = "",
) -> MarketplaceNotification:
    """Create a notification for a marketplace event.

    Called by publisher hooks on every status transition.
    """
    _ensure_tables()
    messages = {
        "submitted": f"Your agent '{agent_name}' has been submitted for review.",
        "approved": f"Your agent '{agent_name}' was approved and is ready to publish.",
        "rejected": f"Your agent '{agent_name}' was rejected.",
        "published": f"Your agent '{agent_name}' is now live on the marketplace.",
        "revised": f"Your revision for '{agent_name}' is back in the review queue.",
    }
    message = messages.get(event_type, f"Update on your agent '{agent_name}': {event_type}.")
    record = MarketplaceNotification(
        user_id=user_id,
        agent_id=agent_id,
        agent_name=agent_name,
        event_type=event_type,
        message=message,
        detail=detail,
    )
    with Session(engine) as session:
        session.add(record)
        session.commit()
        session.refresh(record)
    logger.debug("Notification created: user=%s event=%s agent=%s", user_id, event_type, agent_id)
    return record


def list_notifications(
    user_id: str,
    *,
    unread_only: bool = False,
    limit: int = 50,
) -> Sequence[MarketplaceNotification]:
    """Return notifications for a user, newest first."""
    with Session(engine) as session:
        q = (
            select(MarketplaceNotification)
            .where(MarketplaceNotification.user_id == user_id)
        )
        if unread_only:
            q = q.where(MarketplaceNotification.is_read == False)  # noqa: E712
        q = q.order_by(MarketplaceNotification.created_at.desc()).limit(limit)  # type: ignore[attr-defined]
        return session.exec(q).all()


def mark_read(notification_id: str, user_id: str) -> bool:
    """Mark a single notification as read. Returns False if not found/owned."""
    with Session(engine) as session:
        rec = session.get(MarketplaceNotification, notification_id)
        if not rec or rec.user_id != user_id:
            return False
        rec.is_read = True
        session.add(rec)
        session.commit()
    return True


def mark_all_read(user_id: str) -> int:
    """Mark all of a user's notifications as read. Returns count updated."""
    with Session(engine) as session:
        records = session.exec(
            select(MarketplaceNotification)
            .where(MarketplaceNotification.user_id == user_id)
            .where(MarketplaceNotification.is_read == False)  # noqa: E712
        ).all()
        for rec in records:
            rec.is_read = True
            session.add(rec)
        session.commit()
    return len(records)


def unread_count(user_id: str) -> int:
    """Return the number of unread notifications for a user."""
    with Session(engine) as session:
        return len(session.exec(
            select(MarketplaceNotification)
            .where(MarketplaceNotification.user_id == user_id)
            .where(MarketplaceNotification.is_read == False)  # noqa: E712
        ).all())
