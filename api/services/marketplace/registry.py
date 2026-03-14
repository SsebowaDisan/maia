"""B3-01 — Marketplace agent registry.

Responsibility: central registry of published agents available for discovery
and installation by tenants.  Separate from tenant-scoped agent_definitions.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Literal, Optional, Sequence

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine

PublishStatus = Literal["pending_review", "approved", "published", "rejected", "deprecated"]
PricingTier = Literal["free", "paid", "enterprise"]


class MarketplaceAgent(SQLModel, table=True):
    __tablename__ = "maia_marketplace_agent"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    publisher_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    name: str
    description: str = ""
    version: str
    tags_json: str = "[]"          # JSON list[str]
    required_connectors_json: str = "[]"  # JSON list[str]
    definition_json: str = "{}"
    pricing_tier: PricingTier = "free"
    status: PublishStatus = "pending_review"
    install_count: int = 0
    avg_rating: float = 0.0
    rating_count: int = 0
    has_computer_use: bool = False
    verified: bool = False
    published_at: Optional[float] = None
    created_at: float = Field(default_factory=time.time)


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


# ── Public API ─────────────────────────────────────────────────────────────────

def publish_agent(
    publisher_id: str,
    definition: dict[str, Any],
    metadata: dict[str, Any],
) -> MarketplaceAgent:
    """Create a new marketplace listing in 'pending_review' status."""
    _ensure_tables()
    agent_id = str(definition.get("id") or metadata.get("agent_id") or uuid.uuid4())
    version = str(definition.get("version") or metadata.get("version") or "1.0.0")
    tags: list[str] = list(metadata.get("tags") or [])
    req_connectors: list[str] = list(metadata.get("required_connectors") or [])
    has_cu = "computer_use" in req_connectors or "computer_use" in tags

    entry = MarketplaceAgent(
        publisher_id=publisher_id,
        agent_id=agent_id,
        name=str(definition.get("name") or metadata.get("name") or agent_id),
        description=str(definition.get("description") or metadata.get("description") or ""),
        version=version,
        tags_json=json.dumps(tags),
        required_connectors_json=json.dumps(req_connectors),
        definition_json=json.dumps(definition),
        pricing_tier=str(metadata.get("pricing_tier") or "free"),  # type: ignore[arg-type]
        has_computer_use=has_cu,
    )
    with Session(engine) as session:
        session.add(entry)
        session.commit()
        session.refresh(entry)
    return entry


def get_marketplace_agent(
    agent_id: str,
    version: str | None = None,
) -> MarketplaceAgent | None:
    with Session(engine) as session:
        q = select(MarketplaceAgent).where(MarketplaceAgent.agent_id == agent_id)
        if version:
            q = q.where(MarketplaceAgent.version == version)
        else:
            q = q.where(MarketplaceAgent.status == "published")
        return session.exec(q.order_by(MarketplaceAgent.created_at.desc())).first()  # type: ignore[attr-defined]


def list_marketplace_agents(
    *,
    tags: list[str] | None = None,
    required_connectors: list[str] | None = None,
    pricing: PricingTier | None = None,
    has_computer_use: bool | None = None,
    publisher_id: str | None = None,
    status: PublishStatus = "published",
    limit: int = 50,
    offset: int = 0,
) -> Sequence[MarketplaceAgent]:
    with Session(engine) as session:
        q = select(MarketplaceAgent).where(MarketplaceAgent.status == status)
        if publisher_id:
            q = q.where(MarketplaceAgent.publisher_id == publisher_id)
        if pricing:
            q = q.where(MarketplaceAgent.pricing_tier == pricing)
        if has_computer_use is not None:
            q = q.where(MarketplaceAgent.has_computer_use == has_computer_use)
        results = session.exec(q.order_by(MarketplaceAgent.install_count.desc()).offset(offset).limit(limit)).all()  # type: ignore[attr-defined]

    # Client-side filter for JSON-encoded tags / connectors (DB-agnostic)
    if tags:
        results = [r for r in results if any(t in json.loads(r.tags_json) for t in tags)]
    if required_connectors:
        results = [r for r in results if any(c in json.loads(r.required_connectors_json) for c in required_connectors)]
    return results


def search_marketplace_agents(query: str, *, limit: int = 20) -> Sequence[MarketplaceAgent]:
    """Simple keyword search over name + description.  Full-text via Postgres handled upstream."""
    q_lower = query.lower()
    with Session(engine) as session:
        candidates = session.exec(
            select(MarketplaceAgent)
            .where(MarketplaceAgent.status == "published")
            .limit(500)
        ).all()
    return [
        r for r in candidates
        if q_lower in r.name.lower() or q_lower in r.description.lower()
           or q_lower in r.tags_json.lower()
    ][:limit]


def increment_install_count(agent_id: str) -> None:
    with Session(engine) as session:
        entry = session.exec(
            select(MarketplaceAgent)
            .where(MarketplaceAgent.agent_id == agent_id)
            .where(MarketplaceAgent.status == "published")
        ).first()
        if entry:
            entry.install_count += 1
            session.add(entry)
            session.commit()


def update_rating(agent_id: str, new_avg: float, new_count: int) -> None:
    with Session(engine) as session:
        entry = session.exec(
            select(MarketplaceAgent).where(MarketplaceAgent.agent_id == agent_id)
        ).first()
        if entry:
            entry.avg_rating = round(new_avg, 2)
            entry.rating_count = new_count
            session.add(entry)
            session.commit()
