from __future__ import annotations

from unittest.mock import patch

from api.services.mailer_service import _normalize_report_markdown, send_report_email


def test_send_report_email_renders_markdown_html_template() -> None:
    with patch("api.services.mailer_service.send_report_email_dwd", return_value={"id": "msg-1"}) as send_mock:
        send_report_email(
            to_email="recipient@example.com",
            subject="Website Analysis Report",
            body_text="### Executive Summary\n- One\n- Two",
        )

    kwargs = send_mock.call_args.kwargs
    body_html = str(kwargs.get("body_html") or "")
    assert "Website Analysis Report" in body_html
    assert "<h3>Executive Summary</h3>" in body_html
    assert "<li>One</li>" in body_html
    assert "font-family:-apple-system" in body_html
    assert "Maia Report" not in body_html
    assert "Prepared and delivered by Maia" not in body_html


def test_normalize_report_markdown_splits_inline_heading_markers() -> None:
    normalized = _normalize_report_markdown(
        "# Website Analysis Report ### Executive Summary Prepare a comprehensive report on machine learning. "
        "### Detailed Analysis Machine learning is a subset of artificial intelligence."
    )
    assert normalized.startswith("# Website Analysis Report")
    assert "\n\n### Executive Summary\n\n" in normalized
    assert "\n\n### Detailed Analysis\n\n" in normalized
    assert "Prepare a comprehensive report on machine learning." in normalized
