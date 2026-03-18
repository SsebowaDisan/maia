from __future__ import annotations

import base64
import html
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
import mimetypes
from pathlib import Path
import re
from typing import Any

from api.services.google.auth import GoogleAuthSession
from api.services.google.drive import GoogleDriveService
from api.services.google.errors import GoogleApiError
from api.services.google.events import emit_google_event


def _normalize_recipients(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _decode_urlsafe_base64(raw_value: str) -> bytes:
    padding = "=" * ((4 - len(raw_value) % 4) % 4)
    return base64.urlsafe_b64decode((raw_value + padding).encode("utf-8"))


def _encode_urlsafe_base64(raw_bytes: bytes) -> str:
    return base64.urlsafe_b64encode(raw_bytes).decode("utf-8")


_HTML_TAG_PATTERN = re.compile(r"<[a-zA-Z][^>]*>")
_URL_PATTERN = re.compile(r"(https?://[^\s<]+)")
_MARKDOWN_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$")
_LIST_BULLET_PATTERN = re.compile(r"^[-*]\s+(.+)$")
_LIST_ORDERED_PATTERN = re.compile(r"^\d+\.\s+(.+)$")


def _looks_like_html(value: str) -> bool:
    return bool(_HTML_TAG_PATTERN.search(value or ""))


def _html_to_text(value: str) -> str:
    normalized = str(value or "")
    normalized = re.sub(r"(?i)<br\s*/?>", "\n", normalized)
    normalized = re.sub(r"(?i)</p\s*>", "\n\n", normalized)
    normalized = re.sub(r"(?i)</div\s*>", "\n", normalized)
    stripped = re.sub(r"<[^>]+>", "", normalized)
    return html.unescape(stripped).strip()


def _text_to_html(value: str) -> str:
    normalized = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        normalized = "No message content provided."

    def _linkify(text: str) -> str:
        def _replace(match: re.Match[str]) -> str:
            raw_url = match.group(1)
            trimmed = raw_url
            trailing = ""
            while trimmed and trimmed[-1] in ".,);:!?":
                trailing = trimmed[-1] + trailing
                trimmed = trimmed[:-1]
            href = html.escape(trimmed, quote=True)
            label = html.escape(trimmed)
            return (
                f"<a href=\"{href}\" target=\"_blank\" rel=\"noopener noreferrer\">{label}</a>"
                f"{html.escape(trailing)}"
            )

        return _URL_PATTERN.sub(_replace, text)

    def _format_inline(text: str) -> str:
        escaped = html.escape(text.strip())
        escaped = re.sub(
            r"`([^`]+)`",
            lambda m: (
                "<code style=\"padding:1px 5px;border-radius:6px;background:#f2f4f7;"
                "font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;\">"
                f"{m.group(1)}</code>"
            ),
            escaped,
        )
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
        escaped = re.sub(r"__(.+?)__", r"<strong>\1</strong>", escaped)
        return _linkify(escaped)

    rows = normalized.split("\n")
    parts: list[str] = []
    paragraph_lines: list[str] = []
    in_unordered = False
    in_ordered = False

    def _flush_paragraph() -> None:
        nonlocal paragraph_lines
        if not paragraph_lines:
            return
        paragraph = " ".join(item.strip() for item in paragraph_lines if item.strip()).strip()
        paragraph_lines = []
        if paragraph:
            parts.append(f"<p style=\"margin:0 0 12px 0;\">{paragraph}</p>")

    def _close_lists() -> None:
        nonlocal in_unordered, in_ordered
        if in_unordered:
            parts.append("</ul>")
            in_unordered = False
        if in_ordered:
            parts.append("</ol>")
            in_ordered = False

    for raw_line in rows:
        stripped = raw_line.strip()
        if not stripped:
            _flush_paragraph()
            _close_lists()
            continue

        heading_match = _MARKDOWN_HEADING_PATTERN.match(stripped)
        if heading_match:
            _flush_paragraph()
            _close_lists()
            level = min(4, max(1, len(heading_match.group(1))))
            heading_text = _format_inline(heading_match.group(2))
            parts.append(
                f"<h{level} style=\"margin:16px 0 10px 0;font-size:{30 - (level * 3)}px;"
                "line-height:1.25;font-weight:700;\">"
                f"{heading_text}</h{level}>"
            )
            continue

        bullet_match = _LIST_BULLET_PATTERN.match(stripped)
        if bullet_match:
            _flush_paragraph()
            if in_ordered:
                parts.append("</ol>")
                in_ordered = False
            if not in_unordered:
                parts.append("<ul style=\"margin:0 0 12px 0;padding-left:20px;\">")
                in_unordered = True
            parts.append(f"<li style=\"margin:0 0 6px 0;\">{_format_inline(bullet_match.group(1))}</li>")
            continue

        ordered_match = _LIST_ORDERED_PATTERN.match(stripped)
        if ordered_match:
            _flush_paragraph()
            if in_unordered:
                parts.append("</ul>")
                in_unordered = False
            if not in_ordered:
                parts.append("<ol style=\"margin:0 0 12px 0;padding-left:22px;\">")
                in_ordered = True
            parts.append(f"<li style=\"margin:0 0 6px 0;\">{_format_inline(ordered_match.group(1))}</li>")
            continue

        if stripped.endswith(":") and len(stripped) <= 80:
            _flush_paragraph()
            _close_lists()
            parts.append(
                "<h3 style=\"margin:14px 0 8px 0;font-size:18px;line-height:1.3;font-weight:650;\">"
                f"{_format_inline(stripped[:-1])}</h3>"
            )
            continue

        paragraph_lines.append(_format_inline(stripped))

    _flush_paragraph()
    _close_lists()
    rich_content = "".join(parts) if parts else "<p style=\"margin:0;\">No message content provided.</p>"
    return (
        "<div style=\"font-family:Arial,sans-serif;font-size:14px;line-height:1.55;"
        "color:#111827;white-space:normal;\">"
        f"{rich_content}"
        "</div>"
    )


class GmailService:
    def __init__(self, *, session: GoogleAuthSession) -> None:
        self.session = session
        self.drive = GoogleDriveService(session=session)

    def _build_message(
        self,
        *,
        to: str | list[str],
        subject: str,
        body_html: str,
        cc: str | list[str] | None = None,
        bcc: str | list[str] | None = None,
    ) -> EmailMessage:
        to_list = _normalize_recipients(to)
        if not to_list:
            raise GoogleApiError(
                code="gmail_missing_recipients",
                message="At least one recipient is required.",
                status_code=400,
            )
        msg = EmailMessage()
        msg["To"] = ", ".join(to_list)
        msg["Subject"] = subject.strip() or "(no subject)"
        cc_list = _normalize_recipients(cc)
        bcc_list = _normalize_recipients(bcc)
        if cc_list:
            msg["Cc"] = ", ".join(cc_list)
        if bcc_list:
            msg["Bcc"] = ", ".join(bcc_list)
        normalized_body = str(body_html or "").strip()
        if _looks_like_html(normalized_body):
            text_body = _html_to_text(normalized_body)
            msg.set_content(text_body or "")
            msg.add_alternative(normalized_body, subtype="html")
        else:
            msg.set_content(normalized_body)
            msg.add_alternative(_text_to_html(normalized_body), subtype="html")
        return msg

    def create_draft(
        self,
        *,
        to: str | list[str],
        subject: str,
        body_html: str,
        cc: str | list[str] | None = None,
        bcc: str | list[str] | None = None,
    ) -> dict[str, Any]:
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="gmail.draft_creating",
            message="Creating Gmail draft",
            data={"subject": subject},
        )
        msg = self._build_message(to=to, subject=subject, body_html=body_html, cc=cc, bcc=bcc)
        raw = _encode_urlsafe_base64(msg.as_bytes())
        response = self.session.request_json(
            method="POST",
            url="https://gmail.googleapis.com/gmail/v1/users/me/drafts",
            payload={"message": {"raw": raw}},
        )
        draft = response.get("draft") if isinstance(response, dict) else {}
        draft_id = str((draft or {}).get("id") or "")
        message_id = str(((draft or {}).get("message") or {}).get("id") or "")
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="gmail.draft_created",
            message="Gmail draft created",
            data={"draft_id": draft_id, "message_id": message_id},
        )
        return {"draft_id": draft_id, "message_id": message_id}

    def _load_draft_message(self, *, draft_id: str) -> EmailMessage:
        payload = self.session.request_json(
            method="GET",
            url=f"https://gmail.googleapis.com/gmail/v1/users/me/drafts/{draft_id}",
            params={"format": "raw"},
        )
        raw = str(((payload.get("message") or {}).get("raw")) or "").strip()
        if not raw:
            raise GoogleApiError(
                code="gmail_draft_raw_missing",
                message="Draft payload did not include raw message body.",
                status_code=502,
            )
        parsed = BytesParser(policy=policy.default).parsebytes(_decode_urlsafe_base64(raw))
        if not isinstance(parsed, EmailMessage):
            raise GoogleApiError(
                code="gmail_draft_invalid",
                message="Unable to parse Gmail draft content.",
                status_code=502,
            )
        return parsed

    def add_attachment(
        self,
        *,
        draft_id: str,
        file_id: str | None = None,
        local_path: str | None = None,
    ) -> dict[str, Any]:
        if not draft_id.strip():
            raise GoogleApiError(
                code="gmail_draft_id_missing",
                message="draft_id is required.",
                status_code=400,
            )
        if not file_id and not local_path:
            raise GoogleApiError(
                code="gmail_attachment_source_missing",
                message="Provide file_id or local_path for attachment.",
                status_code=400,
            )

        filename, content_bytes, mime_type = self._resolve_attachment_content(
            file_id=file_id,
            local_path=local_path,
        )

        msg = self._load_draft_message(draft_id=draft_id)
        if not msg.is_multipart():
            msg.make_mixed()
        main_type, _, sub_type = mime_type.partition("/")
        msg.add_attachment(
            content_bytes,
            maintype=main_type or "application",
            subtype=sub_type or "octet-stream",
            filename=filename,
        )
        raw = _encode_urlsafe_base64(msg.as_bytes())
        self.session.request_json(
            method="PUT",
            url=f"https://gmail.googleapis.com/gmail/v1/users/me/drafts/{draft_id}",
            payload={"id": draft_id, "message": {"raw": raw}},
        )
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="gmail.attachment_added",
            message="Attachment added to Gmail draft",
            data={"draft_id": draft_id, "filename": filename, "size_bytes": len(content_bytes)},
        )
        return {"ok": True, "draft_id": draft_id, "filename": filename}

    def _resolve_attachment_content(
        self,
        *,
        file_id: str | None = None,
        local_path: str | None = None,
    ) -> tuple[str, bytes, str]:
        if not file_id and not local_path:
            raise GoogleApiError(
                code="gmail_attachment_source_missing",
                message="Provide file_id or local_path for attachment.",
                status_code=400,
            )

        if local_path:
            path = Path(local_path)
            if not path.exists() or not path.is_file():
                raise GoogleApiError(
                    code="gmail_attachment_file_missing",
                    message=f"Attachment file not found: {local_path}",
                    status_code=400,
                )
            filename = path.name
            content_bytes = path.read_bytes()
            mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            return filename, content_bytes, mime_type

        normalized_file_id = str(file_id or "").strip()
        file_meta = self.session.request_json(
            method="GET",
            url=f"https://www.googleapis.com/drive/v3/files/{normalized_file_id}",
            params={"fields": "id,name,mimeType"},
        )
        filename = str(file_meta.get("name") or f"{normalized_file_id}.bin")
        mime_type = str(file_meta.get("mimeType") or "application/octet-stream")
        if mime_type.startswith("application/vnd.google-apps."):
            content_bytes = self.drive.export_pdf_bytes(file_id=normalized_file_id)
            mime_type = "application/pdf"
            if "." not in filename:
                filename = f"{filename}.pdf"
        else:
            content_bytes = self.drive.download_file(file_id=normalized_file_id)
        return filename, content_bytes, mime_type

    def send_draft(self, *, draft_id: str) -> dict[str, Any]:
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="gmail.send_started",
            message="Sending Gmail draft",
            data={"draft_id": draft_id},
        )
        response = self.session.request_json(
            method="POST",
            url="https://gmail.googleapis.com/gmail/v1/users/me/drafts/send",
            payload={"id": draft_id},
        )
        message_id = str(response.get("id") or "")
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="gmail.sent",
            message="Gmail draft sent",
            data={"draft_id": draft_id, "message_id": message_id},
        )
        return {"message_id": message_id}

    def send_message(
        self,
        *,
        to: str | list[str],
        subject: str,
        body_html: str,
        cc: str | list[str] | None = None,
        bcc: str | list[str] | None = None,
    ) -> dict[str, Any]:
        msg = self._build_message(to=to, subject=subject, body_html=body_html, cc=cc, bcc=bcc)
        raw = _encode_urlsafe_base64(msg.as_bytes())
        response = self.session.request_json(
            method="POST",
            url="https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            payload={"raw": raw},
        )
        message_id = str(response.get("id") or "")
        thread_id = str(response.get("threadId") or "")
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="gmail.sent",
            message="Gmail message sent",
            data={"message_id": message_id, "thread_id": thread_id},
        )
        return {"message_id": message_id, "thread_id": thread_id}

    def send_message_with_attachments(
        self,
        *,
        to: str | list[str],
        subject: str,
        body_html: str,
        attachments: list[dict[str, str]],
        cc: str | list[str] | None = None,
        bcc: str | list[str] | None = None,
    ) -> dict[str, Any]:
        msg = self._build_message(to=to, subject=subject, body_html=body_html, cc=cc, bcc=bcc)
        normalized_attachments = []
        for row in attachments[:16]:
            if not isinstance(row, dict):
                continue
            local_path = str(row.get("local_path") or "").strip()
            file_id = str(row.get("file_id") or "").strip()
            if not local_path and not file_id:
                continue
            normalized_attachments.append({"local_path": local_path, "file_id": file_id})

        if normalized_attachments:
            if not msg.is_multipart():
                msg.make_mixed()
            for row in normalized_attachments:
                filename, content_bytes, mime_type = self._resolve_attachment_content(
                    file_id=row.get("file_id") or None,
                    local_path=row.get("local_path") or None,
                )
                main_type, _, sub_type = mime_type.partition("/")
                msg.add_attachment(
                    content_bytes,
                    maintype=main_type or "application",
                    subtype=sub_type or "octet-stream",
                    filename=filename,
                )

        raw = _encode_urlsafe_base64(msg.as_bytes())
        response = self.session.request_json(
            method="POST",
            url="https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            payload={"raw": raw},
        )
        message_id = str(response.get("id") or "")
        thread_id = str(response.get("threadId") or "")
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="gmail.sent",
            message="Gmail message with attachments sent",
            data={
                "message_id": message_id,
                "thread_id": thread_id,
                "attachments_count": len(normalized_attachments),
            },
        )
        return {
            "message_id": message_id,
            "thread_id": thread_id,
            "attachments_count": len(normalized_attachments),
        }

    def search_messages(self, *, query: str, max_results: int = 20) -> dict[str, Any]:
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="gmail.search_started",
            message="Searching Gmail messages",
            data={"query": query, "max_results": max_results},
        )
        response = self.session.request_json(
            method="GET",
            url="https://gmail.googleapis.com/gmail/v1/users/me/messages",
            params={"q": query, "maxResults": max(1, min(int(max_results), 100))},
        )
        messages = response.get("messages")
        normalized = messages if isinstance(messages, list) else []
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="gmail.search_completed",
            message="Gmail search complete",
            data={"count": len(normalized)},
        )
        return {"messages": normalized}
