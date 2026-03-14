"""TenantStore — CRUD operations for the Tenant model.

Responsibility: all database reads and writes for the maia_tenant table.
No business logic beyond persistence; callers own validation.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Sequence

from sqlmodel import Session, select

from api.models.tenant import Tenant
from ktem.db.engine import engine

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")


def _ensure_tables() -> None:
    """Create tables if they do not exist yet."""
    from sqlmodel import SQLModel  # local import to avoid circular init

    SQLModel.metadata.create_all(engine)


def _to_slug(name: str) -> str:
    """Derive a URL-safe slug from a tenant name."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:62] or "tenant"


# ── Read ──────────────────────────────────────────────────────────────────────


def get_tenant(tenant_id: str) -> Tenant | None:
    """Return a tenant by primary-key id, or None if not found."""
    with Session(engine) as session:
        return session.get(Tenant, tenant_id)


def get_tenant_by_slug(slug: str) -> Tenant | None:
    """Return a tenant by slug, or None if not found."""
    with Session(engine) as session:
        return session.exec(select(Tenant).where(Tenant.slug == slug)).first()


def get_tenant_for_user(user_id: str) -> Tenant | None:
    """Return the tenant whose member_user_ids includes user_id, or None."""
    with Session(engine) as session:
        tenants = session.exec(
            select(Tenant).where(Tenant.is_active == True)  # noqa: E712
        ).all()
        for tenant in tenants:
            if user_id in (tenant.member_user_ids or []):
                return tenant
        return None


def list_tenants(*, active_only: bool = True) -> Sequence[Tenant]:
    """Return all tenants, optionally filtering to active ones."""
    with Session(engine) as session:
        query = select(Tenant)
        if active_only:
            query = query.where(Tenant.is_active == True)  # noqa: E712
        return session.exec(query.order_by(Tenant.date_created)).all()


# ── Write ─────────────────────────────────────────────────────────────────────


def create_tenant(
    *,
    name: str,
    owner_user_id: str,
    slug: str | None = None,
    plan: str = "free",
) -> Tenant:
    """Create and persist a new tenant. Returns the saved instance."""
    _ensure_tables()

    resolved_slug = slug or _to_slug(name)
    if not _SLUG_RE.match(resolved_slug):
        raise ValueError(f"Invalid slug '{resolved_slug}'.")

    with Session(engine) as session:
        existing = session.exec(
            select(Tenant).where(Tenant.slug == resolved_slug)
        ).first()
        if existing:
            raise ValueError(f"A tenant with slug '{resolved_slug}' already exists.")

        tenant = Tenant(
            name=name,
            slug=resolved_slug,
            owner_user_id=owner_user_id,
            member_user_ids=[owner_user_id],
            plan=plan,
        )
        session.add(tenant)
        session.commit()
        session.refresh(tenant)
        return tenant


def update_tenant(
    tenant_id: str,
    *,
    name: str | None = None,
    plan: str | None = None,
    feature_flags: dict | None = None,
    max_agents: int | None = None,
    max_connectors: int | None = None,
) -> Tenant:
    """Update mutable fields on a tenant. Raises ValueError if not found."""
    with Session(engine) as session:
        tenant = session.get(Tenant, tenant_id)
        if not tenant:
            raise ValueError(f"Tenant '{tenant_id}' not found.")

        if name is not None:
            tenant.name = name
        if plan is not None:
            tenant.plan = plan
        if feature_flags is not None:
            tenant.feature_flags = feature_flags
        if max_agents is not None:
            tenant.max_agents = max_agents
        if max_connectors is not None:
            tenant.max_connectors = max_connectors

        tenant.date_updated = datetime.utcnow()
        session.add(tenant)
        session.commit()
        session.refresh(tenant)
        return tenant


def add_member(tenant_id: str, user_id: str) -> Tenant:
    """Add a user to the tenant's member list. Idempotent."""
    with Session(engine) as session:
        tenant = session.get(Tenant, tenant_id)
        if not tenant:
            raise ValueError(f"Tenant '{tenant_id}' not found.")

        members = list(tenant.member_user_ids or [])
        if user_id not in members:
            members.append(user_id)
            tenant.member_user_ids = members
            tenant.date_updated = datetime.utcnow()
            session.add(tenant)
            session.commit()
            session.refresh(tenant)
        return tenant


def remove_member(tenant_id: str, user_id: str) -> Tenant:
    """Remove a user from the tenant's member list."""
    with Session(engine) as session:
        tenant = session.get(Tenant, tenant_id)
        if not tenant:
            raise ValueError(f"Tenant '{tenant_id}' not found.")
        if user_id == tenant.owner_user_id:
            raise ValueError("Cannot remove the tenant owner from the member list.")

        members = [m for m in (tenant.member_user_ids or []) if m != user_id]
        tenant.member_user_ids = members
        tenant.date_updated = datetime.utcnow()
        session.add(tenant)
        session.commit()
        session.refresh(tenant)
        return tenant


def deactivate_tenant(tenant_id: str) -> Tenant:
    """Soft-delete a tenant by setting is_active=False."""
    with Session(engine) as session:
        tenant = session.get(Tenant, tenant_id)
        if not tenant:
            raise ValueError(f"Tenant '{tenant_id}' not found.")
        tenant.is_active = False
        tenant.date_updated = datetime.utcnow()
        session.add(tenant)
        session.commit()
        session.refresh(tenant)
        return tenant
