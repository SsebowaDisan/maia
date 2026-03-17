"""TOTP (Time-based One-Time Password) service.

Wraps the ``pyotp`` library to generate secrets, provisioning URIs (for QR
codes), and verify 6-digit codes with a one-step tolerance window.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    import pyotp
except ImportError as _exc:
    raise ImportError(
        "pyotp is required for TOTP support. Install it with: pip install pyotp"
    ) from _exc


def generate_totp_secret() -> str:
    """Generate a new random TOTP secret (base32-encoded)."""
    return pyotp.random_base32()


def get_provisioning_uri(
    secret: str,
    email: str,
    issuer: str = "Maia",
) -> str:
    """Return an ``otpauth://`` URI suitable for QR code generation."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=issuer)


def verify_totp(secret: str, code: str) -> bool:
    """Verify a 6-digit TOTP *code* against *secret*.

    Allows 1-step tolerance (±30 s) to account for clock drift.
    """
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)
