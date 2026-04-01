"""User CRUD — all database reads and writes for maia_user.

No business logic beyond persistence; callers own validation.
"""
from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlmodel import Session, select

from api.models.user import User
from ktem.db.engine import engine


def _ensure_tables() -> None:
    from sqlmodel import SQLModel
    SQLModel.metadata.create_all(engine)


# ── Read ───────────────────────────────────────────────────────────────────────

def count_users() -> int:
    """Return total number of user records (used for bootstrap guard)."""
    _ensure_tables()
    with Session(engine) as session:
        return len(session.exec(select(User)).all())


def create_user_with_id(
    *,
    user_id: str,
    email: str,
    hashed_password: str,
    full_name: str = "",
    role: str = "super_admin",
    tenant_id: str | None = None,
) -> User:
    """Create a user with a specific ID (used for bootstrap only)."""
    _ensure_tables()
    user = User(
        id=user_id,
        email=email.lower().strip(),
        hashed_password=hashed_password,
        full_name=full_name,
        role=role,
        tenant_id=tenant_id,
    )
    with Session(engine) as session:
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def get_user(user_id: str) -> User | None:
    with Session(engine) as session:
        return session.get(User, user_id)


def get_user_by_email(email: str) -> User | None:
    with Session(engine) as session:
        return session.exec(
            select(User).where(User.email == email.lower().strip())
        ).first()


def list_users_for_tenant(tenant_id: str) -> Sequence[User]:
    with Session(engine) as session:
        return session.exec(
            select(User)
            .where(User.tenant_id == tenant_id)
            .where(User.is_active == True)  # noqa: E712
            .order_by(User.date_created)
        ).all()


def list_all_active_users() -> Sequence[User]:
    with Session(engine) as session:
        return session.exec(
            select(User)
            .where(User.is_active == True)  # noqa: E712
            .order_by(User.date_created)
        ).all()


# ── Write ──────────────────────────────────────────────────────────────────────

def create_user(
    *,
    email: str,
    hashed_password: str,
    full_name: str = "",
    role: str = "org_user",
    tenant_id: str | None = None,
) -> User:
    _ensure_tables()
    user = User(
        email=email.lower().strip(),
        hashed_password=hashed_password,
        full_name=full_name,
        role=role,
        tenant_id=tenant_id,
    )
    with Session(engine) as session:
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def update_user(
    user_id: str,
    *,
    full_name: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    tenant_id: str | None = None,
) -> User:
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            raise ValueError(f"User '{user_id}' not found.")
        if full_name is not None:
            user.full_name = full_name
        if role is not None:
            user.role = role
        if is_active is not None:
            user.is_active = is_active
        if tenant_id is not None:
            user.tenant_id = tenant_id
        user.date_updated = datetime.utcnow()
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def deactivate_user(user_id: str) -> User:
    return update_user(user_id, is_active=False)
