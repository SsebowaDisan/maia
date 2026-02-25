from __future__ import annotations

import base64
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
import mimetypes
from pathlib import Path
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
        msg.set_content(body_html or "", subtype="html")
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

        filename = ""
        content_bytes = b""
        mime_type = "application/octet-stream"

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
        else:
            file_meta = self.session.request_json(
                method="GET",
                url=f"https://www.googleapis.com/drive/v3/files/{file_id}",
                params={"fields": "id,name,mimeType"},
            )
            filename = str(file_meta.get("name") or f"{file_id}.bin")
            mime_type = str(file_meta.get("mimeType") or "application/octet-stream")
            content_bytes = self.drive.download_file(file_id=str(file_id))

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

