"""CredentialVault — encrypted credential storage per tenant per connector.

Responsibility: encrypt credentials at rest using Fernet symmetric encryption,
store ciphertext in the ConnectorBinding DB model, never log plaintext.

Key derivation: per-tenant key = HKDF(master_secret, salt=tenant_id).
Master secret read from env MAIA_VAULT_SECRET (falls back to a dev default
that logs a loud warning — never use the default in production).
"""
from __future__ import annotations

import base64
import json
import logging
import os
from datetime import datetime
from typing import Any

from sqlmodel import Session, select

from api.models.connector_binding import ConnectorBinding
from ktem.db.engine import engine

logger = logging.getLogger(__name__)

_VAULT_SECRET_ENV = "MAIA_VAULT_SECRET"
_DEV_FALLBACK = "dev-only-insecure-vault-secret-change-me"


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------

def _master_secret() -> bytes:
    raw = os.getenv(_VAULT_SECRET_ENV, "").strip()
    if not raw:
        logger.warning(
            "MAIA_VAULT_SECRET is not set. Using insecure dev fallback — "
            "set this env var before going to production."
        )
        raw = _DEV_FALLBACK
    return raw.encode()


def _derive_key(tenant_id: str) -> bytes:
    """Derive a 32-byte Fernet key for a specific tenant using HKDF."""
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from cryptography.hazmat.backends import default_backend

        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=tenant_id.encode(),
            info=b"maia-vault-v1",
            backend=default_backend(),
        )
        raw_key = hkdf.derive(_master_secret())
        return base64.urlsafe_b64encode(raw_key)
    except ImportError as exc:
        raise RuntimeError(
            "cryptography package required for vault. Run: pip install cryptography"
        ) from exc


def _fernet(tenant_id: str):
    from cryptography.fernet import Fernet
    return Fernet(_derive_key(tenant_id))


# ---------------------------------------------------------------------------
# Encrypt / decrypt helpers
# ---------------------------------------------------------------------------

def _encrypt(tenant_id: str, data: dict[str, Any]) -> str:
    """Encrypt a credential dict to a ciphertext string."""
    plaintext = json.dumps(data).encode()
    return _fernet(tenant_id).encrypt(plaintext).decode()


def _decrypt(tenant_id: str, ciphertext: str) -> dict[str, Any]:
    """Decrypt a ciphertext string back to a credential dict."""
    if not ciphertext:
        return {}
    try:
        plaintext = _fernet(tenant_id).decrypt(ciphertext.encode())
        return json.loads(plaintext.decode())
    except Exception:
        logger.warning("Vault: decryption failed for tenant %s — returning empty credentials.", tenant_id)
        return {}


# ---------------------------------------------------------------------------
# Vault operations
# ---------------------------------------------------------------------------

def _ensure_tables() -> None:
    from sqlmodel import SQLModel
    SQLModel.metadata.create_all(engine)


def store_credential(
    tenant_id: str,
    connector_id: str,
    credentials: dict[str, Any],
    *,
    auth_strategy: str = "api_key",
) -> ConnectorBinding:
    """Encrypt and persist credentials for a tenant+connector.

    If a binding already exists it is updated; otherwise a new one is created.
    Plaintext credentials are never written to the database.
    """
    _ensure_tables()
    ciphertext = _encrypt(tenant_id, credentials)

    with Session(engine) as session:
        binding = session.exec(
            select(ConnectorBinding)
            .where(ConnectorBinding.tenant_id == tenant_id)
            .where(ConnectorBinding.connector_id == connector_id)
        ).first()

        now = datetime.utcnow()
        if binding:
            binding.encrypted_credentials = ciphertext
            binding.auth_strategy = auth_strategy
            binding.date_updated = now
        else:
            binding = ConnectorBinding(
                tenant_id=tenant_id,
                connector_id=connector_id,
                encrypted_credentials=ciphertext,
                auth_strategy=auth_strategy,
                date_created=now,
                date_updated=now,
            )

        session.add(binding)
        session.commit()
        session.refresh(binding)
        return binding


def store_oauth_tokens(
    tenant_id: str,
    connector_id: str,
    *,
    access_token: str,
    refresh_token: str = "",
    token_expires_at: datetime | None = None,
    extra: dict[str, Any] | None = None,
) -> ConnectorBinding:
    """Encrypt and store OAuth2 tokens for a tenant+connector binding."""
    _ensure_tables()

    with Session(engine) as session:
        binding = session.exec(
            select(ConnectorBinding)
            .where(ConnectorBinding.tenant_id == tenant_id)
            .where(ConnectorBinding.connector_id == connector_id)
        ).first()

        now = datetime.utcnow()
        enc_access = _encrypt(tenant_id, {"token": access_token})
        enc_refresh = _encrypt(tenant_id, {"token": refresh_token}) if refresh_token else ""

        if binding:
            binding.encrypted_access_token = enc_access
            binding.encrypted_refresh_token = enc_refresh
            binding.token_expires_at = token_expires_at
            binding.auth_strategy = "oauth2"
            if extra:
                binding.extra_metadata = {**(binding.extra_metadata or {}), **extra}
            binding.date_updated = now
        else:
            binding = ConnectorBinding(
                tenant_id=tenant_id,
                connector_id=connector_id,
                encrypted_access_token=enc_access,
                encrypted_refresh_token=enc_refresh,
                token_expires_at=token_expires_at,
                auth_strategy="oauth2",
                extra_metadata=extra or {},
                date_created=now,
                date_updated=now,
            )

        session.add(binding)
        session.commit()
        session.refresh(binding)
        return binding


def get_credential(tenant_id: str, connector_id: str) -> dict[str, Any]:
    """Return decrypted credentials dict, or {} if not found."""
    with Session(engine) as session:
        binding = session.exec(
            select(ConnectorBinding)
            .where(ConnectorBinding.tenant_id == tenant_id)
            .where(ConnectorBinding.connector_id == connector_id)
            .where(ConnectorBinding.is_active == True)  # noqa: E712
        ).first()

    if not binding:
        return {}

    result: dict[str, Any] = {}

    if binding.encrypted_credentials:
        result.update(_decrypt(tenant_id, binding.encrypted_credentials))

    if binding.encrypted_access_token:
        token_data = _decrypt(tenant_id, binding.encrypted_access_token)
        if token_data.get("token"):
            result["access_token"] = token_data["token"]

    if binding.encrypted_refresh_token:
        refresh_data = _decrypt(tenant_id, binding.encrypted_refresh_token)
        if refresh_data.get("token"):
            result["refresh_token"] = refresh_data["token"]

    if binding.token_expires_at:
        result["token_expires_at"] = binding.token_expires_at.isoformat()

    return result


def revoke_credential(tenant_id: str, connector_id: str) -> bool:
    """Deactivate the binding and clear all encrypted fields. Returns True if found."""
    with Session(engine) as session:
        binding = session.exec(
            select(ConnectorBinding)
            .where(ConnectorBinding.tenant_id == tenant_id)
            .where(ConnectorBinding.connector_id == connector_id)
        ).first()

        if not binding:
            return False

        binding.encrypted_credentials = ""
        binding.encrypted_access_token = ""
        binding.encrypted_refresh_token = ""
        binding.is_active = False
        binding.date_updated = datetime.utcnow()
        session.add(binding)
        session.commit()
        return True


def get_binding(tenant_id: str, connector_id: str) -> ConnectorBinding | None:
    """Return the raw ConnectorBinding row (no decryption)."""
    with Session(engine) as session:
        return session.exec(
            select(ConnectorBinding)
            .where(ConnectorBinding.tenant_id == tenant_id)
            .where(ConnectorBinding.connector_id == connector_id)
        ).first()


def get_granted_scopes(tenant_id: str, connector_id: str) -> list[str]:
    """Return the list of OAuth scopes granted for this binding.

    Scopes are stored in extra_metadata["granted_scopes"] at OAuth callback time.
    Returns an empty list if no binding or no scope data.
    """
    binding = get_binding(tenant_id, connector_id)
    if not binding or not binding.extra_metadata:
        return []
    scopes = binding.extra_metadata.get("granted_scopes")
    if isinstance(scopes, list):
        return [str(s) for s in scopes if s]
    return []
