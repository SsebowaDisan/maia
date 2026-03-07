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
        "<body style=\"margin:0;background:#f1f3f4;padding:24px 12px;"
        "font-family:'Google Sans',Roboto,Arial,sans-serif;color:#202124;\">"
        "<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" "
        "style=\"max-width:760px;margin:0 auto;background:#ffffff;border:1px solid #dadce0;"
        "border-radius:12px;overflow:hidden;box-shadow:0 1px 2px rgba(60,64,67,.15);\">"
        "<tr><td style=\"padding:18px 24px 8px 24px;font-size:12px;letter-spacing:.08em;"
        "text-transform:uppercase;color:#5f6368;font-weight:600;\">Maia Report</td></tr>"
        "<tr><td style=\"padding:0 24px 24px 24px;font-size:15px;line-height:1.7;color:#202124;\">"
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
