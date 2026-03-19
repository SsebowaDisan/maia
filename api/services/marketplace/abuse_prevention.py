"""Marketplace abuse prevention helpers.

Responsibilities:
- Enforce simple per-user daily publish quotas.
- Keep quota accounting in SQL so limits survive restarts.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel, Session, select

from ktem.db.engine import engine


class DailyQuotaExceededError(ValueError):
    """Raised when a user exceeds the configured daily action quota."""


class DailyActionQuota(SQLModel, table=True):
    """Counter row for one user + action key + UTC day."""

    __tablename__ = "maia_daily_action_quota"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    user_id: str = Field(index=True)
    action_key: str = Field(index=True, max_length=64)
    day_key: str = Field(index=True, max_length=10)  # YYYY-MM-DD UTC
    count: int = Field(default=0)
    date_created: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    date_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


def _utc_day_key() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def consume_daily_quota(
    *,
    user_id: str,
    action_key: str,
    daily_limit: int,
) -> int:
    """Consume one quota unit and return the resulting count.

    Raises:
        DailyQuotaExceededError: If the user already consumed daily_limit units.
    """
    _ensure_tables()
    safe_user_id = str(user_id or "").strip()
    safe_action_key = str(action_key or "").strip().lower()
    if not safe_user_id or not safe_action_key:
        raise ValueError("user_id and action_key are required.")
    if daily_limit < 1:
        raise ValueError("daily_limit must be >= 1.")

    day_key = _utc_day_key()
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        row = session.exec(
            select(DailyActionQuota).where(
                DailyActionQuota.user_id == safe_user_id,
                DailyActionQuota.action_key == safe_action_key,
                DailyActionQuota.day_key == day_key,
            )
        ).first()
        if row and int(row.count or 0) >= daily_limit:
            raise DailyQuotaExceededError(
                f"Daily publish limit reached ({daily_limit}/day). Try again tomorrow."
            )

        if not row:
            row = DailyActionQuota(
                user_id=safe_user_id,
                action_key=safe_action_key,
                day_key=day_key,
                count=1,
                date_created=now,
                date_updated=now,
            )
        else:
            row.count = int(row.count or 0) + 1
            row.date_updated = now

        session.add(row)
        session.commit()
        session.refresh(row)
        return int(row.count or 0)
