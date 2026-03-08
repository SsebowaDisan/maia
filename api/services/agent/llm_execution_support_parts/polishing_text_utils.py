from __future__ import annotations

import re

DEAR_PLACEHOLDER_RE = re.compile(r"(?im)^\s*dear\s*\[[^\]\n]{1,80}\]\s*,?\s*$")
EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
INTERNAL_CONTEXT_LINE_RE = re.compile(
    r"(?im)^(?:working context:|active role:|role-scoped context:|role verification obligations:|unresolved slots:).*$"
)
CITATION_ANCHOR_RE = re.compile(
    r"<a\b[^>]*class=['\"][^'\"]*\bcitation\b[^'\"]*['\"][^>]*>\s*\[(\d{1,4})\]\s*</a>",
    re.I,
)
GENERIC_ANCHOR_RE = re.compile(r"</?a\b[^>]*>", re.I)


def sanitize_delivery_body(*, body_text: str, recipient: str) -> str:
    clean = str(body_text or "").strip()
    if not clean:
        return ""
    clean = CITATION_ANCHOR_RE.sub(lambda match: f"[{match.group(1)}]", clean)
    clean = GENERIC_ANCHOR_RE.sub("", clean)
    recipient_text = " ".join(str(recipient or "").split()).strip()
    if recipient_text:
        clean = re.sub(re.escape(recipient_text), "the recipient", clean, flags=re.IGNORECASE)
    clean = INTERNAL_CONTEXT_LINE_RE.sub("", clean)
    clean = re.sub(r"(?im)^subject:\s*.+$", "", clean)
    clean = re.sub(r"(?im)^objective:\s*.+$", "", clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    clean = DEAR_PLACEHOLDER_RE.sub("Hello,", clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    return clean.strip()


def safe_trim_body(text: str, *, max_chars: int = 12000) -> str:
    clean = str(text or "").strip()
    if len(clean) <= max_chars:
        return clean
    window = clean[: max_chars + 1]
    cut = max(window.rfind("\n\n"), window.rfind(". "), window.rfind("! "), window.rfind("? "))
    if cut < int(max_chars * 0.7):
        cut = max_chars
    return window[:cut].rstrip()


def ends_with_fragment(text: str) -> bool:
    clean = str(text or "").rstrip()
    if not clean:
        return False
    if clean[-1] in ".!?:;)]}\"'":
        return False
    token_match = re.search(r"([A-Za-z]{1,2})\s*$", clean)
    return bool(token_match and len(clean) >= 240)


def inferred_focus_text(*, request_message: str, objective: str) -> str:
    source_text = " ".join(str(objective or request_message or "").split()).strip()
    if not source_text:
        return "Requested Topic"
    source_text = EMAIL_RE.sub("", source_text).strip()
    source_text = re.sub(r'["\'`]+', "", source_text).strip()
    match = re.search(r"\b(?:about|on|for)\s+(.+)$", source_text, flags=re.I)
    focus = match.group(1).strip() if match else source_text
    focus = re.split(
        r"\b(?:and then|then|and send|and email|and deliver|and share|send|deliver)\b",
        focus,
        maxsplit=1,
        flags=re.I,
    )[0].strip(" .,:;-")
    focus = re.sub(r"\s+", " ", focus).strip()
    return focus[:84] or "Requested Topic"
