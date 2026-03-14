"""B3-06 — Ratings and reviews.

Responsibility: per-tenant per-agent reviews, one per tenant, with aggregate
rating computation and optional publisher response.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Optional, Sequence

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine
from api.services.marketplace.registry import update_rating


class AgentReview(SQLModel, table=True):
    __tablename__ = "maia_agent_review"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    agent_id: str = Field(index=True)
    tenant_id: str = Field(index=True)
    rating: int  # 1–5
    review_text: str = ""
    publisher_response: Optional[str] = None
    flagged: bool = False
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


def submit_review(
    tenant_id: str,
    agent_id: str,
    rating: int,
    review_text: str = "",
) -> AgentReview:
    """Submit or update a review.  One review per tenant per agent."""
    _ensure_tables()
    if not 1 <= rating <= 5:
        raise ValueError("Rating must be between 1 and 5.")

    with Session(engine) as session:
        existing = session.exec(
            select(AgentReview)
            .where(AgentReview.tenant_id == tenant_id)
            .where(AgentReview.agent_id == agent_id)
        ).first()

        if existing:
            existing.rating = rating
            existing.review_text = review_text
            existing.updated_at = time.time()
            session.add(existing)
            session.commit()
            session.refresh(existing)
            review = existing
        else:
            review = AgentReview(
                agent_id=agent_id,
                tenant_id=tenant_id,
                rating=rating,
                review_text=review_text,
            )
            session.add(review)
            session.commit()
            session.refresh(review)

    # Recompute aggregate
    agg = get_aggregate_rating(agent_id)
    update_rating(agent_id, agg["avg"], agg["count"])
    return review


def get_reviews(
    agent_id: str,
    *,
    limit: int = 20,
    offset: int = 0,
) -> Sequence[AgentReview]:
    with Session(engine) as session:
        return session.exec(
            select(AgentReview)
            .where(AgentReview.agent_id == agent_id)
            .where(AgentReview.flagged == False)  # noqa: E712
            .order_by(AgentReview.created_at.desc())  # type: ignore[attr-defined]
            .offset(offset)
            .limit(limit)
        ).all()


def get_aggregate_rating(agent_id: str) -> dict[str, Any]:
    with Session(engine) as session:
        reviews = session.exec(
            select(AgentReview)
            .where(AgentReview.agent_id == agent_id)
            .where(AgentReview.flagged == False)  # noqa: E712
        ).all()

    if not reviews:
        return {"avg": 0.0, "count": 0, "distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}}

    dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    total = 0
    for r in reviews:
        dist[r.rating] = dist.get(r.rating, 0) + 1
        total += r.rating

    return {
        "avg": round(total / len(reviews), 2),
        "count": len(reviews),
        "distribution": dist,
    }


def add_publisher_response(
    agent_id: str,
    review_id: str,
    response_text: str,
) -> bool:
    with Session(engine) as session:
        review = session.exec(
            select(AgentReview)
            .where(AgentReview.id == review_id)
            .where(AgentReview.agent_id == agent_id)
        ).first()
        if not review:
            return False
        review.publisher_response = response_text
        review.updated_at = time.time()
        session.add(review)
        session.commit()
    return True


def flag_review(review_id: str) -> bool:
    with Session(engine) as session:
        review = session.get(AgentReview, review_id)
        if not review:
            return False
        review.flagged = True
        session.add(review)
        session.commit()
    return True
