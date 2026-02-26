from __future__ import annotations

import base64
from typing import Any, Iterable, Mapping

from .client import build_gmail_service, get_gmail_service
from .config import GmailDwdConfig, get_from_email, get_impersonate_email
from .errors import GmailDwdConfigError, map_gmail_send_exception
from .mime_builder import AttachmentInput, build_rfc2822_base64url


def send_email(
    *,
    to: str | None = None,
    to_email: str | None = None,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    attachments: Iterable[AttachmentInput] | None = None,
    config: GmailDwdConfig | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    recipient = str(to_email or to or "").strip()
    if not recipient:
        raise GmailDwdConfigError(
            "Recipient email is required.",
            code="gmail_dwd_recipient_missing",
        )

    if config is None:
        from_email = get_from_email(env)
        impersonate_email = get_impersonate_email(env)
        service = build_gmail_service(env=env)
    else:
        from_email = config.from_email
        impersonate_email = config.impersonate_email
        service = get_gmail_service(config)

    raw_message = build_rfc2822_base64url(
        from_email=from_email,
        to_email=recipient,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        attachments=attachments,
    )

    try:
        response = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": raw_message})
            .execute()
        )
        data = dict(response or {})
    except Exception as exc:
        raise map_gmail_send_exception(exc, impersonate_email=impersonate_email) from exc

    return {
        "id": str(data.get("id") or ""),
        "thread_id": str(data.get("threadId") or ""),
        "label_ids": data.get("labelIds") if isinstance(data.get("labelIds"), list) else [],
        "raw_size_bytes": len(base64.urlsafe_b64decode(raw_message.encode("utf-8"))),
    }


def send_report_email(
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    attachments: Iterable[AttachmentInput] | None = None,
) -> dict[str, Any]:
    return send_email(
        to_email=to_email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        attachments=attachments,
    )
