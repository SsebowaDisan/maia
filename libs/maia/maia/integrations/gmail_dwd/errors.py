from __future__ import annotations

import json
from typing import Any


class GmailDwdError(RuntimeError):
    """Base exception for Gmail DWD send failures."""

    def __init__(self, message: str, *, code: str = "gmail_dwd_error", status_code: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class GmailDwdConfigError(GmailDwdError):
    pass


class GmailDwdApiDisabledError(GmailDwdError):
    pass


class GmailDwdDelegationError(GmailDwdError):
    pass


class GmailDwdMailboxError(GmailDwdError):
    pass


class GmailDwdAuthError(GmailDwdError):
    pass


class GmailDwdDeliveryError(GmailDwdError):
    pass


def _extract_status_code(exc: Exception) -> int | None:
    resp = getattr(exc, "resp", None)
    status = getattr(resp, "status", None)
    if isinstance(status, int):
        return status
    if isinstance(status, str) and status.isdigit():
        return int(status)
    return None


def _extract_error_text(exc: Exception) -> str:
    text = str(exc or "").strip()
    content = getattr(exc, "content", None)
    if isinstance(content, bytes):
        try:
            decoded = content.decode("utf-8", errors="ignore").strip()
        except Exception:
            decoded = ""
        if decoded:
            try:
                parsed = json.loads(decoded)
                payload = parsed.get("error") if isinstance(parsed, dict) else None
                if isinstance(payload, dict):
                    message = str(payload.get("message") or "").strip()
                    if message:
                        return message
            except Exception:
                pass
            return decoded
    return text


def map_gmail_send_exception(exc: Exception, *, impersonate_email: str) -> GmailDwdError:
    if isinstance(exc, GmailDwdError):
        return exc

    status_code = _extract_status_code(exc)
    message = _extract_error_text(exc)
    lowered = message.lower()

    if any(
        token in lowered
        for token in (
            "gmail api has not been used",
            "access not configured",
            "api has not been used",
            "is disabled",
            "service disabled",
            "has not been enabled",
        )
    ):
        return GmailDwdApiDisabledError(
            "Gmail API is not enabled for the service account project. "
            "Enable Gmail API in Google Cloud Console and retry.",
            code="gmail_dwd_api_disabled",
            status_code=status_code,
        )

    if any(
        token in lowered
        for token in (
            "delegation denied",
            "unauthorized_client",
            "invalid_grant",
            "not a delegated user",
            "precondition check failed",
            "not authorized to access this resource/api",
        )
    ):
        return GmailDwdDelegationError(
            "Domain-wide delegation is not authorized for this service account/user. "
            f"Verify Admin Console delegation for {impersonate_email} with scope "
            "https://www.googleapis.com/auth/gmail.send.",
            code="gmail_dwd_delegation_denied",
            status_code=status_code,
        )

    if any(
        token in lowered
        for token in (
            "mailbox not found",
            "user not found",
            "recipient address rejected",
            "mail service not enabled",
            "account disabled",
            "account suspended",
        )
    ):
        return GmailDwdMailboxError(
            f"The impersonated mailbox {impersonate_email} is unavailable (not found, disabled, "
            "or suspended). Confirm mailbox status in Google Workspace.",
            code="gmail_dwd_mailbox_unavailable",
            status_code=status_code,
        )

    if status_code in (401, 403):
        return GmailDwdAuthError(
            "Failed to authenticate delegated Gmail request. Check Workspace Domain-Wide "
            "Delegation scope authorization (`https://www.googleapis.com/auth/gmail.send`) "
            f"and confirm impersonated mailbox `{impersonate_email}` exists and is active.",
            code="gmail_dwd_auth_failed",
            status_code=status_code,
        )

    return GmailDwdDeliveryError(
        f"Gmail DWD send failed: {message or exc}",
        code="gmail_dwd_send_failed",
        status_code=status_code,
    )
