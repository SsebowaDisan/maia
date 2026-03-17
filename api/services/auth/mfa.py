"""MFA enrollment management — enroll, activate, verify, and disable TOTP.

Encryption follows the same pattern as ``api.services.connectors.vault``:
derive a per-user Fernet key via HKDF from the platform JWT secret.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import time
import uuid

from sqlmodel import Session, SQLModel, select

from api.models.mfa import MfaEnrollment
from api.services.auth.totp import generate_totp_secret, get_provisioning_uri, verify_totp
from ktem.db.engine import engine

logger = logging.getLogger(__name__)

_MFA_SECRET = os.getenv("MAIA_JWT_SECRET", "dev-secret")


# ---------------------------------------------------------------------------
# Key derivation (mirrors vault.py pattern)
# ---------------------------------------------------------------------------

def _derive_key(user_id: str) -> bytes:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=user_id.encode(),
        info=b"maia-mfa-v1",
        backend=default_backend(),
    )
    raw_key = hkdf.derive(_MFA_SECRET.encode())
    return base64.urlsafe_b64encode(raw_key)


def _fernet(user_id: str):
    from cryptography.fernet import Fernet
    return Fernet(_derive_key(user_id))


def _encrypt(user_id: str, plaintext: str) -> str:
    return _fernet(user_id).encrypt(plaintext.encode()).decode()


def _decrypt(user_id: str, ciphertext: str) -> str:
    return _fernet(user_id).decrypt(ciphertext.encode()).decode()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


def _generate_backup_codes(count: int = 8) -> list[str]:
    """Generate *count* one-time backup codes (12-char hex each)."""
    return [secrets.token_hex(6) for _ in range(count)]


def _get_enrollment(session: Session, user_id: str) -> MfaEnrollment | None:
    return session.exec(
        select(MfaEnrollment).where(MfaEnrollment.user_id == user_id)
    ).first()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enroll_mfa(user_id: str) -> dict:
    """Start MFA enrolment: generate secret, encrypt, store, return setup data."""
    _ensure_tables()
    secret = generate_totp_secret()
    backup_codes = _generate_backup_codes()

    encrypted_secret = _encrypt(user_id, secret)
    encrypted_backups = _encrypt(user_id, json.dumps(backup_codes))

    # Fetch user email for provisioning URI (best-effort)
    email = f"{user_id}@maia"
    try:
        from api.services.auth.store import get_user
        user = get_user(user_id)
        if user:
            email = user.email
    except Exception:
        pass

    uri = get_provisioning_uri(secret, email)

    with Session(engine) as session:
        existing = _get_enrollment(session, user_id)
        if existing:
            session.delete(existing)
            session.flush()

        enrollment = MfaEnrollment(
            id=uuid.uuid4().hex,
            user_id=user_id,
            totp_secret_encrypted=encrypted_secret,
            is_active=False,
            backup_codes_json=encrypted_backups,
            created_at=time.time(),
        )
        session.add(enrollment)
        session.commit()

    return {
        "secret": secret,
        "provisioning_uri": uri,
        "backup_codes": backup_codes,
    }


def activate_mfa(user_id: str, code: str) -> bool:
    """Verify a TOTP code and mark enrolment as active."""
    with Session(engine) as session:
        enrollment = _get_enrollment(session, user_id)
        if not enrollment:
            return False

        secret = _decrypt(user_id, enrollment.totp_secret_encrypted)
        if not verify_totp(secret, code):
            return False

        enrollment.is_active = True
        enrollment.last_used_at = time.time()
        session.add(enrollment)
        session.commit()
        return True


def verify_mfa(user_id: str, code: str) -> bool:
    """Verify a TOTP code or one-time backup code."""
    with Session(engine) as session:
        enrollment = _get_enrollment(session, user_id)
        if not enrollment or not enrollment.is_active:
            return False

        secret = _decrypt(user_id, enrollment.totp_secret_encrypted)

        # Try TOTP first
        if verify_totp(secret, code):
            enrollment.last_used_at = time.time()
            session.add(enrollment)
            session.commit()
            return True

        # Try backup codes
        try:
            backup_codes: list[str] = json.loads(
                _decrypt(user_id, enrollment.backup_codes_json)
            )
        except Exception:
            backup_codes = []

        if code in backup_codes:
            backup_codes.remove(code)
            enrollment.backup_codes_json = _encrypt(
                user_id, json.dumps(backup_codes)
            )
            enrollment.last_used_at = time.time()
            session.add(enrollment)
            session.commit()
            return True

        return False


def disable_mfa(user_id: str) -> bool:
    """Remove MFA enrolment entirely."""
    with Session(engine) as session:
        enrollment = _get_enrollment(session, user_id)
        if not enrollment:
            return False
        session.delete(enrollment)
        session.commit()
        return True


def has_mfa(user_id: str) -> bool:
    """Return True if the user has an *active* MFA enrolment."""
    with Session(engine) as session:
        enrollment = _get_enrollment(session, user_id)
        return bool(enrollment and enrollment.is_active)
