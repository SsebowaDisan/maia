from __future__ import annotations

import base64
from email.message import EmailMessage
from typing import Any

from api.services.google.gmail import GmailService


class _FakeSession:
    def __init__(self) -> None:
        self.user_id = "user_1"
        self.run_id = "run_1"
        self.calls: list[dict[str, Any]] = []

    def request_json(
        self,
        *,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 30,
        retry_on_unauthorized: bool = True,
    ) -> dict[str, Any]:
        _ = (headers, timeout, retry_on_unauthorized)
        self.calls.append(
            {
                "method": method,
                "url": url,
                "params": params or {},
                "payload": payload or {},
            }
        )
        return {
            "draft": {
                "id": "draft_123",
                "message": {"id": "msg_456"},
            }
        }


def test_gmail_create_draft_returns_structured_ids() -> None:
    session = _FakeSession()
    service = GmailService(session=session)  # type: ignore[arg-type]

    result = service.create_draft(
        to="owner@example.com",
        subject="Test Draft",
        body_html="<p>Hello world</p>",
    )

    assert result["draft_id"] == "draft_123"
    assert result["message_id"] == "msg_456"
    assert len(session.calls) == 1
    assert session.calls[0]["method"] == "POST"
    assert session.calls[0]["url"].endswith("/gmail/v1/users/me/drafts")
    assert "message" in session.calls[0]["payload"]
    assert "raw" in (session.calls[0]["payload"]["message"] or {})


class _AttachmentSession:
    def __init__(self, *, mime_type: str) -> None:
        self.user_id = "user_1"
        self.run_id = "run_1"
        self.mime_type = mime_type
        self.calls: list[dict[str, Any]] = []

    def request_json(
        self,
        *,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 30,
        retry_on_unauthorized: bool = True,
    ) -> dict[str, Any]:
        _ = (headers, timeout, retry_on_unauthorized)
        normalized_params = params or {}
        normalized_payload = payload or {}
        self.calls.append(
            {
                "method": method,
                "url": url,
                "params": normalized_params,
                "payload": normalized_payload,
            }
        )

        if (
            method == "GET"
            and "/drive/v3/files/" in url
            and normalized_params.get("fields") == "id,name,mimeType"
        ):
            return {"id": "file_1", "name": "Research Report", "mimeType": self.mime_type}

        if (
            method == "GET"
            and "/gmail/v1/users/me/drafts/" in url
            and normalized_params.get("format") == "raw"
        ):
            msg = EmailMessage()
            msg["To"] = "owner@example.com"
            msg["Subject"] = "Draft"
            msg.set_content("body", subtype="html")
            encoded = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
            return {"message": {"raw": encoded}}

        if method == "PUT" and "/gmail/v1/users/me/drafts/" in url:
            return {"id": "draft_123"}

        if method == "POST" and url.endswith("/gmail/v1/users/me/messages/send"):
            return {"id": "msg_send_1", "threadId": "thread_send_1"}

        raise AssertionError(f"Unexpected request: method={method} url={url} params={normalized_params}")


def test_gmail_add_attachment_exports_google_docs_file_to_pdf() -> None:
    session = _AttachmentSession(mime_type="application/vnd.google-apps.document")
    service = GmailService(session=session)  # type: ignore[arg-type]
    calls = {"export": 0, "download": 0}

    def _export_pdf_bytes(*, file_id: str) -> bytes:
        assert file_id == "file_1"
        calls["export"] += 1
        return b"%PDF-1.4 stub"

    def _download_file(*, file_id: str) -> bytes:
        assert file_id == "file_1"
        calls["download"] += 1
        return b""

    service.drive.export_pdf_bytes = _export_pdf_bytes  # type: ignore[method-assign]
    service.drive.download_file = _download_file  # type: ignore[method-assign]

    result = service.add_attachment(draft_id="draft_123", file_id="file_1")

    assert result["ok"] is True
    assert calls["export"] == 1
    assert calls["download"] == 0


def test_gmail_add_attachment_downloads_regular_drive_file() -> None:
    session = _AttachmentSession(mime_type="application/pdf")
    service = GmailService(session=session)  # type: ignore[arg-type]
    calls = {"export": 0, "download": 0}

    def _export_pdf_bytes(*, file_id: str) -> bytes:
        assert file_id == "file_1"
        calls["export"] += 1
        return b""

    def _download_file(*, file_id: str) -> bytes:
        assert file_id == "file_1"
        calls["download"] += 1
        return b"%PDF-1.4 file"

    service.drive.export_pdf_bytes = _export_pdf_bytes  # type: ignore[method-assign]
    service.drive.download_file = _download_file  # type: ignore[method-assign]

    result = service.add_attachment(draft_id="draft_123", file_id="file_1")

    assert result["ok"] is True
    assert calls["export"] == 0
    assert calls["download"] == 1


def test_gmail_send_message_with_attachments_uses_send_endpoint() -> None:
    session = _AttachmentSession(mime_type="application/pdf")
    service = GmailService(session=session)  # type: ignore[arg-type]
    calls = {"export": 0, "download": 0}

    def _export_pdf_bytes(*, file_id: str) -> bytes:
        assert file_id == "file_1"
        calls["export"] += 1
        return b""

    def _download_file(*, file_id: str) -> bytes:
        assert file_id == "file_1"
        calls["download"] += 1
        return b"%PDF-1.4 attachment"

    service.drive.export_pdf_bytes = _export_pdf_bytes  # type: ignore[method-assign]
    service.drive.download_file = _download_file  # type: ignore[method-assign]

    result = service.send_message_with_attachments(
        to="owner@example.com",
        subject="Attachment send",
        body_html="<p>Body</p>",
        attachments=[{"file_id": "file_1"}],
    )

    assert result["message_id"] == "msg_send_1"
    assert result["thread_id"] == "thread_send_1"
    assert result["attachments_count"] == 1
    assert calls["export"] == 0
    assert calls["download"] == 1
    assert any(
        call["method"] == "POST" and call["url"].endswith("/gmail/v1/users/me/messages/send")
        for call in session.calls
    )
