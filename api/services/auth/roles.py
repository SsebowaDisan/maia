"""Custom role management — CRUD and scope checking.

Built-in roles (super_admin, org_admin, org_user) have implicit scope sets.
Custom roles are stored per-tenant in the ``maia_custom_role`` table.
"""
from __future__ import annotations

import json
import logging
import time
import uuid

from sqlmodel import Session, SQLModel, select

from api.models.custom_role import CustomRole
from ktem.db.engine import engine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# All available scopes
# ---------------------------------------------------------------------------

ALL_SCOPES: list[str] = [
    "workflow:read", "workflow:write", "workflow:run", "workflow:delete",
    "agent:read", "agent:write", "agent:run",
    "connector:read", "connector:write", "connector:manage_credentials",
    "secret:read", "secret:write",
    "user:read", "user:invite", "user:manage_roles",
    "audit:read", "audit:export",
]

# ---------------------------------------------------------------------------
# Built-in role → implicit scopes
# ---------------------------------------------------------------------------

BUILTIN_SCOPES: dict[str, set[str]] = {
    "super_admin": set(ALL_SCOPES),
    "org_admin": {
        s for s in ALL_SCOPES
        if not s.startswith("audit:export")
        # org_admin gets everything except platform-level ops
    } - {"user:manage_roles"},
    "org_user": {s for s in ALL_SCOPES if s.endswith(":read")},
}

# Give org_admin audit:read but not audit:export
BUILTIN_SCOPES["org_admin"].add("audit:read")
BUILTIN_SCOPES["org_admin"].add("user:invite")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_role(
    tenant_id: str,
    name: str,
    scopes: list[str],
    *,
    created_by: str,
    description: str = "",
) -> CustomRole:
    """Create a new custom role for *tenant_id*."""
    _ensure_tables()
    now = time.time()
    role = CustomRole(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        name=name,
        description=description,
        scopes_json=json.dumps(scopes),
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )
    with Session(engine) as session:
        session.add(role)
        session.commit()
        session.refresh(role)
        return role


def get_role(role_id: str) -> CustomRole | None:
    with Session(engine) as session:
        return session.exec(
            select(CustomRole).where(CustomRole.id == role_id)
        ).first()


def list_roles(tenant_id: str) -> list[CustomRole]:
    with Session(engine) as session:
        return list(
            session.exec(
                select(CustomRole).where(CustomRole.tenant_id == tenant_id)
            ).all()
        )


def update_role(
    role_id: str,
    *,
    name: str | None = None,
    scopes: list[str] | None = None,
    description: str | None = None,
) -> CustomRole:
    """Update fields on an existing role. Returns the updated object."""
    with Session(engine) as session:
        role = session.exec(
            select(CustomRole).where(CustomRole.id == role_id)
        ).first()
        if not role:
            raise ValueError(f"Role {role_id} not found")
        if name is not None:
            role.name = name
        if scopes is not None:
            role.scopes_json = json.dumps(scopes)
        if description is not None:
            role.description = description
        role.updated_at = time.time()
        session.add(role)
        session.commit()
        session.refresh(role)
        return role


def delete_role(role_id: str) -> bool:
    with Session(engine) as session:
        role = session.exec(
            select(CustomRole).where(CustomRole.id == role_id)
        ).first()
        if not role:
            return False
        session.delete(role)
        session.commit()
        return True


# ---------------------------------------------------------------------------
# Scope checking
# ---------------------------------------------------------------------------

def check_scope(user_id: str, scope: str) -> bool:
    """Check if *user_id* has the given *scope*.

    Resolution order:
    1. Built-in role scopes (super_admin, org_admin, org_user).
    2. Custom role scopes from the user's ``custom_role_id`` field (if any).
    """
    try:
        from api.services.auth.store import get_user
        user = get_user(user_id)
    except Exception:
        return False

    if not user or not user.is_active:
        return False

    # Built-in role check
    builtin = BUILTIN_SCOPES.get(user.role, set())
    if scope in builtin:
        return True

    # Custom role check — look up roles for the user's tenant
    if user.tenant_id:
        with Session(engine) as session:
            roles = session.exec(
                select(CustomRole).where(CustomRole.tenant_id == user.tenant_id)
            ).all()
            for role in roles:
                try:
                    role_scopes = json.loads(role.scopes_json)
                except Exception:
                    continue
                if scope in role_scopes:
                    return True

    return False
