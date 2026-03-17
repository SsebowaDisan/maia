"""Tenant resolution and access-control helpers.

Centralises the logic for determining which tenant a user belongs to
and whether they may access a given tenant's resources.  Replaces the
old ``_tenant(user_id) -> user_id`` pattern with real enforcement.
"""
from __future__ import annotations

from fastapi import HTTPException, status

from api.models.user import User


# ── Resolution ────────────────────────────────────────────────────────────────


def resolve_tenant_id(user: User) -> str:
    """Return the canonical tenant_id for *user*.

    Rules
    -----
    1. If `user.tenant_id` is set, return it directly.
    2. If the user is a super_admin with no tenant_id, fall back to
       `user.id` for backwards compatibility (single-tenant / dev mode).
    3. Otherwise raise — a non-admin user without a tenant is a data error.
    """
    if user.tenant_id:
        return user.tenant_id

    if user.role == "super_admin":
        # Backwards-compat: super_admins aren't tied to a single tenant,
        # but callers that *need* a tenant_id get the user's own id.
        return user.id

    raise ValueError(
        f"User {user.id!r} (role={user.role!r}) has no tenant_id assigned. "
        "Cannot resolve tenant."
    )


# ── Access control ────────────────────────────────────────────────────────────


def assert_tenant_access(user: User, resource_tenant_id: str) -> None:
    """Raise 403 if *user* may not access *resource_tenant_id*.

    * super_admin  — access to ALL tenants (platform-level privilege).
    * org_admin / org_user — only their own tenant.
    """
    if user.role == "super_admin":
        return  # unrestricted

    if user.tenant_id == resource_tenant_id:
        return  # same tenant — allowed

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied: you do not belong to this tenant.",
    )


# ── Query helpers ─────────────────────────────────────────────────────────────


def get_tenant_filter(user: User) -> str | None:
    """Return the tenant_id to filter queries by, or ``None`` for super_admins.

    Intended for list endpoints: pass the result into a WHERE clause.
    ``None`` means "show all tenants" (super_admin only).
    """
    if user.role == "super_admin":
        return None
    return resolve_tenant_id(user)
