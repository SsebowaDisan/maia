from __future__ import annotations

from unittest.mock import MagicMock, patch

from maia.integrations.gmail_dwd.sender import send_email


def test_send_email_calls_gmail_users_messages_send_with_raw_payload() -> None:
    service = MagicMock()
    send_mock = service.users.return_value.messages.return_value.send
    send_mock.return_value.execute.return_value = {"id": "msg-001"}

    with patch("maia.integrations.gmail_dwd.sender.build_gmail_service", return_value=service):
        result = send_email(
            to_email="recipient@example.com",
            subject="Report",
            body_text="Hello",
            env={
                "MAIA_GMAIL_IMPERSONATE": "disan@micrurus.com",
                "MAIA_GMAIL_FROM": "disan@micrurus.com",
            },
        )

    kwargs = send_mock.call_args.kwargs
    assert kwargs["userId"] == "me"
    assert isinstance(kwargs["body"], dict)
    assert isinstance(kwargs["body"].get("raw"), str)
    assert kwargs["body"]["raw"]
    assert result["id"] == "msg-001"
