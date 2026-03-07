from __future__ import annotations

import html
import re
from typing import Iterable

from maia.integrations.gmail_dwd.mime_builder import AttachmentInput
from maia.integrations.gmail_dwd.sender import send_report_email as send_report_email_dwd


_INLINE_HEADING_MARKER_RE = re.compile(r"(?<!\n)\s+(#{1,6}\s+)")
_LINE_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_TITLEISH_TOKEN_RE = re.compile(r"^[A-Z][A-Za-z0-9&/+._-]*$")


def _split_long_heading_text(raw_heading: str) -> tuple[str, str]:
    heading = " ".join(str(raw_heading or "").split()).strip()
    if not heading:
        return "", ""

    words = heading.split()
    if len(words) <= 8:
        return heading, ""

    # If heading-like title words are followed by sentence prose, keep only the
    # compact title and move the remainder into normal paragraph text.
    first_lower_idx = next((idx for idx, token in enumerate(words[1:], 1) if token[:1].islower()), -1)
    if (
        first_lower_idx >= 2
        and _TITLEISH_TOKEN_RE.match(words[0])
        and _TITLEISH_TOKEN_RE.match(words[1])
    ):
        keep_count = min(3, max(2, first_lower_idx - 1))
        title = " ".join(words[:keep_count]).strip(" .,:;")
        remainder = " ".join(words[keep_count:]).strip()
        if title and remainder:
            return title, remainder

    for delimiter in (": ", " - ", " — ", "; ", ". "):
        index = heading.find(delimiter)
        if 18 <= index <= 120:
            title = heading[:index].strip(" .,:;")
            remainder = heading[index + len(delimiter) :].strip()
            if title and remainder:
                return title, remainder

    title = " ".join(words[:10]).strip(" .,:;")
    remainder = " ".join(words[10:]).strip()
    return title or heading, remainder


def _normalize_report_markdown(body_text: str) -> str:
    text = str(body_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""

    if text.startswith("```") and text.endswith("```"):
        text = re.sub(r"^```(?:markdown|md)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)

    text = _INLINE_HEADING_MARKER_RE.sub(r"\n\n\1", text)

    normalized_lines: list[str] = []
    for raw_line in text.split("\n"):
        line = str(raw_line or "")
        stripped = line.strip()
        heading_match = _LINE_HEADING_RE.match(stripped)
        if not heading_match:
            normalized_lines.append(line)
            continue

        marker, heading_text = heading_match.groups()
        compact_heading = " ".join(str(heading_text or "").split()).strip()
        title_text, remainder = _split_long_heading_text(compact_heading)
        normalized_lines.append(f"{marker} {title_text}".rstrip())
        if remainder:
            normalized_lines.append("")
            normalized_lines.append(remainder)

    cleaned = "\n".join(normalized_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _render_markdown_html(body_text: str) -> str:
    text = _normalize_report_markdown(body_text)
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


def _default_html_body(body_text: str, *, subject: str = "") -> str:
    rendered = _sanitize_email_html(_render_markdown_html(body_text))
    clean_subject = html.escape(" ".join(str(subject or "").split()).strip())
    return (
        "<html>"
        "<body style=\"margin:0;background:radial-gradient(1200px 500px at 50% -20%,#ffffff 0%,#f2f3f7 48%,#eceef3 100%);padding:32px 14px;"
        "font-family:-apple-system,BlinkMacSystemFont,'SF Pro Text','SF Pro Display','Segoe UI',Roboto,Arial,sans-serif;color:#1d1d1f;\">"
        "<style>"
        ".maia-report-wrap h1{margin:0 0 12px 0;font-size:30px;line-height:1.18;font-weight:660;letter-spacing:-0.022em;color:#101013;}"
        ".maia-report-wrap h2{margin:24px 0 10px 0;font-size:23px;line-height:1.28;font-weight:640;letter-spacing:-0.016em;color:#151518;}"
        ".maia-report-wrap h3{margin:18px 0 8px 0;font-size:18px;line-height:1.34;font-weight:620;letter-spacing:-0.01em;color:#1d1d1f;}"
        ".maia-report-wrap h4,.maia-report-wrap h5,.maia-report-wrap h6{margin:14px 0 8px 0;font-size:15px;line-height:1.4;font-weight:600;color:#202024;}"
        ".maia-report-wrap p{margin:0 0 14px 0;font-size:15px;line-height:1.74;color:#2c2c31;}"
        ".maia-report-wrap ul,.maia-report-wrap ol{margin:0 0 16px 0;padding-left:22px;color:#2c2c31;}"
        ".maia-report-wrap li{margin:0 0 9px 0;font-size:15px;line-height:1.7;}"
        ".maia-report-wrap a{color:#0a66d9;text-decoration:underline;word-break:break-word;}"
        ".maia-report-wrap blockquote{margin:14px 0;padding:10px 14px;border-left:3px solid #d2d2d7;color:#44444a;background:#f7f7fa;border-radius:12px;}"
        ".maia-report-wrap code{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,'Liberation Mono',monospace;"
        "background:#f4f4f6;border:1px solid #e2e2e8;border-radius:6px;padding:1px 5px;font-size:13px;}"
        ".maia-report-wrap pre{background:#f4f4f6;border:1px solid #e2e2e8;border-radius:12px;padding:12px;overflow:auto;margin:0 0 14px 0;}"
        ".maia-report-wrap table{width:100%;border-collapse:collapse;margin:12px 0;}"
        ".maia-report-wrap th,.maia-report-wrap td{border:1px solid #e5e5ea;padding:8px 10px;text-align:left;font-size:14px;line-height:1.5;}"
        ".maia-report-wrap th{background:#f7f7f9;font-weight:600;color:#1f1f23;}"
        "</style>"
        "<table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" "
        "style=\"max-width:820px;margin:0 auto;background:linear-gradient(180deg,#ffffff 0%,#fbfcff 100%);"
        "border:1px solid #dadce3;border-radius:24px;overflow:hidden;box-shadow:0 30px 72px -46px rgba(0,0,0,.52);\">"
        "<tr><td style=\"padding:22px 30px 12px 30px;border-bottom:1px solid #ececf2;\">"
        "<div style=\"font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#6e6e73;font-weight:640;\">Maia Report</div>"
        + (
            f"<div style=\"margin-top:8px;font-size:30px;line-height:1.16;font-weight:650;letter-spacing:-0.02em;color:#111114;\">{clean_subject}</div>"
            if clean_subject
            else ""
        )
        + "<div style=\"margin-top:8px;font-size:13px;color:#86868b;\">Prepared and delivered by Maia</div>"
        "</td></tr>"
        "<tr><td style=\"padding:24px 30px 32px 30px;\">"
        f"<div class=\"maia-report-wrap\" style=\"font-size:15px;line-height:1.72;color:#2b2b30;\">{rendered}</div>"
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
        body_html=body_html or _default_html_body(body_text, subject=subject),
        attachments=attachments,
    )
