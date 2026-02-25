from __future__ import annotations

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

