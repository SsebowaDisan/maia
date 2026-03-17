"""JTI-based token blocklist.

Supports revoking individual tokens (by JTI) or all tokens for a user
issued before a certain timestamp.  Expired entries are cleaned up
periodically via ``cleanup_expired()``.

Table: maia_token_blocklist
"""
from __future__ import annotations

import time
from typing import Optional

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine


class TokenBlocklistEntry(SQLModel, table=True):
    __tablename__ = "maia_token_blocklist"

    jti: str = Field(primary_key=True)
    user_id: str = Field(index=True)
    blocked_at: float = Field(default_factory=time.time)
    expires_at: float = Field(default=0.0)
    reason: str = Field(default="logout")


# ── Ensure table exists ──────────────────────────────────────────────────────

SQLModel.metadata.create_all(engine, tables=[TokenBlocklistEntry.__table__])


# ── Public API ────────────────────────────────────────────────────────────────

def block_token(
    jti: str,
    user_id: str,
    expires_at: float,
    reason: str = "logout",
) -> None:
    """Block a single token by its JTI."""
    entry = TokenBlocklistEntry(
        jti=jti,
        user_id=user_id,
        blocked_at=time.time(),
        expires_at=expires_at,
        reason=reason,
    )
    with Session(engine) as session:
        session.merge(entry)
        session.commit()


def block_all_user_tokens(user_id: str) -> None:
    """Insert a special 'all' entry that blocks every token issued before now."""
    entry = TokenBlocklistEntry(
        jti=f"all:{user_id}",
        user_id=user_id,
        blocked_at=time.time(),
        expires_at=time.time() + 90 * 86400,  # keep for 90 days
        reason="block_all",
    )
    with Session(engine) as session:
        session.merge(entry)
        session.commit()


def is_blocked(jti: str, user_id: str, issued_at: float) -> bool:
    """Return True if the token is revoked.

    Checks:
    1. Exact JTI match (single-token revocation).
    2. A ``block_all`` entry for the user whose ``blocked_at`` >= token ``iat``.
    """
    with Session(engine) as session:
        # 1. Direct JTI lookup
        exact = session.get(TokenBlocklistEntry, jti)
        if exact is not None:
            return True

        # 2. "Block all" entry — any token issued before the block timestamp
        stmt = (
            select(TokenBlocklistEntry)
            .where(TokenBlocklistEntry.jti == f"all:{user_id}")
            .where(TokenBlocklistEntry.user_id == user_id)
        )
        all_entry: Optional[TokenBlocklistEntry] = session.exec(stmt).first()
        if all_entry and all_entry.blocked_at >= issued_at:
            return True

    return False


def cleanup_expired() -> int:
    """Delete blocklist rows whose ``expires_at`` is in the past. Returns count."""
    now = time.time()
    with Session(engine) as session:
        stmt = select(TokenBlocklistEntry).where(
            TokenBlocklistEntry.expires_at < now,
            TokenBlocklistEntry.expires_at > 0,
        )
        rows = session.exec(stmt).all()
        for row in rows:
            session.delete(row)
        session.commit()
        return len(rows)
