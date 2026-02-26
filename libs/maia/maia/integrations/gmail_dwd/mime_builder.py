from __future__ import annotations

import base64
import mimetypes
from email import policy
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Iterable

AttachmentInput = tuple[str, bytes, str | None]


def _split_mimetype(mimetype: str | None, *, filename: str) -> tuple[str, str]:
    final = (mimetype or "").strip() or (mimetypes.guess_type(filename)[0] or "application/octet-stream")
    main_type, _, sub_type = final.partition("/")
    if not main_type or not sub_type:
        return ("application", "octet-stream")
    return (main_type, sub_type)


def build_rfc2822_message(
    *,
    from_email: str,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    attachments: Iterable[AttachmentInput] | None = None,
) -> bytes:
    msg = EmailMessage(policy=policy.SMTP)
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject.strip() or "(no subject)"
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg.set_content(body_text or "")

    if body_html:
        msg.add_alternative(body_html, subtype="html")

    for filename, content, mimetype in list(attachments or []):
        main_type, sub_type = _split_mimetype(mimetype, filename=filename)
        msg.add_attachment(
            content,
            maintype=main_type,
            subtype=sub_type,
            filename=filename,
        )

    return msg.as_bytes()


def encode_base64url(message_bytes: bytes) -> str:
    return base64.urlsafe_b64encode(message_bytes).decode("utf-8")


def build_rfc2822_base64url(
    *,
    from_email: str,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    attachments: Iterable[AttachmentInput] | None = None,
) -> str:
    message_bytes = build_rfc2822_message(
        from_email=from_email,
        to_email=to_email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        attachments=attachments,
    )
    return encode_base64url(message_bytes)
