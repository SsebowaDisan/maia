from __future__ import annotations

from unittest.mock import patch

from api.services.mailer_service import send_report_email


def test_send_report_email_renders_markdown_html_template() -> None:
    with patch("api.services.mailer_service.send_report_email_dwd", return_value={"id": "msg-1"}) as send_mock:
        send_report_email(
            to_email="recipient@example.com",
            subject="Website Analysis Report",
            body_text="### Executive Summary\n- One\n- Two",
        )

    kwargs = send_mock.call_args.kwargs
    body_html = str(kwargs.get("body_html") or "")
    assert "<h3>Executive Summary</h3>" in body_html
    assert "<li>One</li>" in body_html
