"""Computer Use session persistence helpers.

Thin read/write layer over ComputerUseSessionRecord.
All functions use a short-lived SQLModel Session to stay safe under
concurrent HTTP requests.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any

from sqlmodel import Session, select

from ktem.db.engine import engine
from ktem.db.models import ComputerUseSessionRecord

logger = logging.getLogger(__name__)


def create_record(
    session_id: str,
    user_id: str,
    start_url: str = "",
) -> None:
    """Insert a new active session record."""
    record = ComputerUseSessionRecord(
        session_id=session_id,
        user_id=user_id,
        start_url=start_url,
        status="active",
        date_created=datetime.datetime.now(datetime.timezone.utc),
    )
    with Session(engine) as db:
        db.add(record)
        db.commit()
    logger.debug("session_record: created %s user=%s", session_id, user_id)


def close_record(session_id: str) -> None:
    """Mark a session as closed."""
    with Session(engine) as db:
        row = db.get(ComputerUseSessionRecord, session_id)
        if row is not None:
            row.status = "closed"
            row.date_closed = datetime.datetime.now(datetime.timezone.utc)
            db.add(row)
            db.commit()
    logger.debug("session_record: closed %s", session_id)


def mark_stale_active_sessions() -> int:
    """Mark all previously-active sessions as stale.

    Called once at registry startup — any session left in 'active' state
    from a prior process is a zombie (the browser process no longer exists).
    Returns the number of rows updated.
    """
    with Session(engine) as db:
        rows = db.exec(
            select(ComputerUseSessionRecord).where(
                ComputerUseSessionRecord.status == "active"
            )
        ).all()
        for row in rows:
            row.status = "stale"
            row.date_closed = datetime.datetime.now(datetime.timezone.utc)
            db.add(row)
        db.commit()
    if rows:
        logger.info("session_record: marked %d stale sessions on startup", len(rows))
    return len(rows)


def list_records(user_id: str) -> list[dict[str, Any]]:
    """Return all session records for a user, newest first."""
    with Session(engine) as db:
        rows = db.exec(
            select(ComputerUseSessionRecord)
            .where(ComputerUseSessionRecord.user_id == user_id)
            .order_by(ComputerUseSessionRecord.date_created.desc())  # type: ignore[arg-type]
        ).all()
    return [
        {
            "session_id": r.session_id,
            "user_id": r.user_id,
            "start_url": r.start_url,
            "status": r.status,
            "date_created": r.date_created.isoformat(),
            "date_closed": r.date_closed.isoformat() if r.date_closed else None,
        }
        for r in rows
    ]
