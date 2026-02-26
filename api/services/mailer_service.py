from __future__ import annotations

import html
import re
from typing import Iterable

from maia.integrations.gmail_dwd.mime_builder import AttachmentInput
from maia.integrations.gmail_dwd.sender import send_report_email as send_report_email_dwd


def _render_markdown_html(body_text: str) -> str:
    text = str(body_text or "").strip()
    if not text:
        return "<p>No report content generated.</p>"
    try:
        import markdown

        rendered = markdown.markdown(
            text,
            extensions=["extra", "sane_lists", "nl2br"],
            output_format="html5",
        )
    except Exception:
        escaped = html.escape(text).replace("\n", "<br/>")
        rendered = f"<p>{escaped}</p>"
    return rendered


def _sanitize_email_html(content_html: str) -> str:
    unsafe_tag_pattern = re.compile(r"<\s*(script|style|iframe|object|embed)[^>]*>.*?<\s*/\s*\1\s*>", re.I | re.S)
    safe = unsafe_tag_pattern.sub("", content_html)
    safe = re.sub(r"javascript\s*:", "", safe, flags=re.I)
    return safe


def _default_html_body(body_text: str) -> str:
    rendered = _sanitize_email_html(_render_markdown_html(body_text))
    return (
        "<html>"
        "<body style=\"margin:0;background:#f5f5f7;padding:24px 12px;"
        "font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Segoe UI',sans-serif;color:#1d1d1f;\">"
        "<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" "
        "style=\"max-width:760px;margin:0 auto;background:#ffffff;border:1px solid #e5e5ea;"
        "border-radius:18px;overflow:hidden;box-shadow:0 18px 45px rgba(0,0,0,0.08);\">"
        "<tr><td style=\"padding:22px 24px 10px 24px;font-size:13px;letter-spacing:.08em;"
        "text-transform:uppercase;color:#8e8e93;font-weight:600;\">Maia Report</td></tr>"
        "<tr><td style=\"padding:0 24px 24px 24px;font-size:15px;line-height:1.65;color:#1f1f22;\">"
        f"{rendered}"
        "</td></tr>"
        "</table>"
        "</body>"
        "</html>"
    )


def send_report_email(
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    attachments: Iterable[AttachmentInput] | None = None,
) -> dict[str, object]:
    return send_report_email_dwd(
        to_email=to_email,
        subject=subject,
        body_text=body_text,
        body_html=body_html or _default_html_body(body_text),
        attachments=attachments,
    )
