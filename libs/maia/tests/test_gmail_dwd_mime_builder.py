from __future__ import annotations

import base64
from email import policy
from email.parser import BytesParser

from maia.integrations.gmail_dwd.mime_builder import build_rfc2822_base64url


def test_build_rfc2822_base64url_contains_expected_headers() -> None:
    raw = build_rfc2822_base64url(
        from_email="disan@micrurus.com",
        to_email="recipient@example.com",
        subject="Maia DWD Test",
        body_text="Plain text body",
        body_html="<p>HTML body</p>",
        attachments=[("report.txt", b"attachment", "text/plain")],
    )

    parsed = BytesParser(policy=policy.default).parsebytes(
        base64.urlsafe_b64decode(raw.encode("utf-8"))
    )

    assert parsed["From"] == "disan@micrurus.com"
    assert parsed["To"] == "recipient@example.com"
    assert parsed["Subject"] == "Maia DWD Test"
    assert parsed["Date"]
    assert parsed["Message-ID"]
