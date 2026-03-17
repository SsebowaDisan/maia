"""B9 — Developer API key service.

Responsibility: generate, verify, and revoke long-lived API keys for developer
programmatic access.

Key format:  mk_<32 random hex chars>
             "mk_" prefix makes keys easily identifiable in logs/secrets scanners.

Storage:     Only the SHA-256 hash is stored in the DB.
             The raw key is returned once at creation and never stored.
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
import time
from typing import Optional, Sequence

from sqlmodel import Session, select

from ktem.db.engine import engine
from api.models.api_key import ApiKey

logger = logging.getLogger(__name__)

_KEY_PREFIX = "mk_"
_KEY_BYTES = 32          # 32 random bytes → 64 hex chars
_PREFIX_DISPLAY_LEN = 12  # chars of raw key kept as prefix for display


def _ensure_tables() -> None:
    from sqlmodel import SQLModel
    SQLModel.metadata.create_all(engine)


# ── Public API ──────────────────────────────────────────────────────────────────

def create_api_key(
    user_id: str,
    tenant_id: str | None,
    label: str = "",
    scopes: list[str] | None = None,
    expires_at: float | None = None,
) -> tuple[ApiKey, str]:
    """Create a new API key.

    Returns:
        (ApiKey record, raw_key_string) — raw key shown once, never stored.
    """
    _ensure_tables()
    raw = _KEY_PREFIX + secrets.token_hex(_KEY_BYTES)
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    key_prefix = raw[:_PREFIX_DISPLAY_LEN]
    scope_str = " ".join(scopes) if scopes else "marketplace:publish marketplace:read"

    record = ApiKey(
        user_id=user_id,
        tenant_id=tenant_id,
        label=label,
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes=scope_str,
        expires_at=expires_at,
    )
    with Session(engine) as session:
        session.add(record)
        session.commit()
        session.refresh(record)
    logger.info("API key created: user=%s label=%r prefix=%s", user_id, label, key_prefix)
    return record, raw


def verify_api_key(raw_key: str) -> ApiKey | None:
    """Verify a raw API key and return the record if valid.

    Updates last_used_at on success.  Returns None if invalid, expired, or revoked.
    """
    if not raw_key.startswith(_KEY_PREFIX):
        return None
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    with Session(engine) as session:
        record = session.exec(
            select(ApiKey)
            .where(ApiKey.key_hash == key_hash)
            .where(ApiKey.is_active == True)  # noqa: E712
        ).first()
        if not record:
            return None
        if record.expires_at and record.expires_at < time.time():
            record.is_active = False
            session.add(record)
            session.commit()
            return None
        record.last_used_at = time.time()
        session.add(record)
        session.commit()
        session.refresh(record)
    return record


def list_api_keys(user_id: str) -> Sequence[ApiKey]:
    """Return all active API keys for a user (no raw key material)."""
    with Session(engine) as session:
        return session.exec(
            select(ApiKey)
            .where(ApiKey.user_id == user_id)
            .where(ApiKey.is_active == True)  # noqa: E712
            .order_by(ApiKey.created_at.desc())  # type: ignore[attr-defined]
        ).all()


def revoke_api_key(key_id: str, user_id: str) -> bool:
    """Revoke an API key by ID. Returns False if not found or not owned."""
    with Session(engine) as session:
        record = session.get(ApiKey, key_id)
        if not record or record.user_id != user_id:
            return False
        record.is_active = False
        session.add(record)
        session.commit()
    logger.info("API key revoked: id=%s user=%s", key_id, user_id)
    return True


def has_scope(record: ApiKey, required_scope: str) -> bool:
    """Check whether a key record grants the required scope."""
    return required_scope in record.scopes.split()
