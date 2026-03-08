from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

_FENCED_BLOCK_RE = re.compile(r"```[\s\S]*?```")
_INLINE_CODE_RE = re.compile(r"`[^`]+`")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_URL_RE = re.compile(r"https?://\S+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_EMAIL_RE = re.compile(r"\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b", flags=re.IGNORECASE)
_CITATION_ANCHOR_OPEN_RE = re.compile(
    r"<a\b[^>]*class=['\"][^'\"]*\bcitation\b[^'\"]*['\"][^>]*>",
    flags=re.IGNORECASE,
)
_ATTR_RE = re.compile(r"([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(['\"])(.*?)\2")
_EVIDENCE_SUFFIX_BLOCK_RE = re.compile(
    r"\n\nEvidence:\s+internal execution trace[\s\S]*\Z",
    flags=re.IGNORECASE,
)
_TOP_LEVEL_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", flags=re.IGNORECASE | re.MULTILINE)
_DEDUPE_SECTION_TITLES = {"evidence citations", "recommended next steps"}
_NOISY_SECTION_TITLES = {
    "delivery status",
    "delivery attempt overview",
    "contract gate",
    "contract gate summary",
    "verification",
    "verification and quality assessment",
    "research execution status",
    "execution summary",
    "execution issues",
    "task understanding",
    "execution plan",
    "files and documents",
}
_NOISY_SECTION_SUBSTRINGS = (
    "delivery status",
    "delivery attempt",
    "contract gate",
    "verification and quality",
    "execution summary",
    "execution issues",
    "files and documents",
)
_ANALYTICAL_INTENT_RE = re.compile(
    r"\b("
    r"analyz[ei]|analysis|analyse|"
    r"research\s+(?:on|about|into)|"
    r"report\s+on|"
    r"overview\s+of|"
    r"study\s+(?:of|on)|"
    r"profile\s+of|"
    r"assess(?:ment)?\s+(?:of|on)|"
    r"review\s+(?:of|on)|"
    r"investigate|investigation\s+(?:of|into)|"
    r"deep\s+(?:dive|research|analysis)|"
    r"comprehensive\s+(?:guide|overview|analysis|report|summary)|"
    r"(?:tell|explain)\s+me\s+(?:everything|all)\s+about|"
    r"background\s+(?:on|about)|"
    r"compare\s+(?:and\s+contrast\s+)?(?:[a-z]+\s+){0,4}(?:and|vs?\.?|versus)|"
    r"comparison\s+(?:of|between)|"
    r"evaluat(?:e|ion)\s+(?:of|on)|"
    r"brief(?:ing)?\s+on|"
    r"landscape\s+(?:of|for|in)|"
    r"state\s+of\s+(?:the\s+)?(?:art\s+)?(?:in\s+)?"
    r")\b",
    re.IGNORECASE,
)


def extract_citation_tail(answer_text: str) -> str:
    text = str(answer_text or "")
    if not text.strip():
        return ""
    match = re.search(r"(^|\n)##\s+Evidence\s+Citations\b", text, flags=re.IGNORECASE)
    if not match:
        return ""
    return text[match.start() :].strip()


def contains_citation_markers(answer_text: str) -> bool:
    text = str(answer_text or "")
    if not text.strip():
        return False
    if re.search(r"(^|\n)##\s+Evidence\s+Citations\b", text, flags=re.IGNORECASE):
        return True
    return bool(re.search(r"\[\d{1,3}\]", text))


def parse_ref_number_from_attrs(attrs: dict[str, str]) -> int:
    candidates = [
        attrs.get("data-evidence-id", ""),
        attrs.get("href", ""),
        attrs.get("id", ""),
        attrs.get("data-citation-number", ""),
    ]
    for candidate in candidates:
        match = re.search(r"(\d{1,4})", str(candidate or ""))
        if not match:
            continue
        try:
            value = int(match.group(1))
        except Exception:
            continue
        if value > 0:
            return value
    return 0


def normalize_citation_anchor_attrs(text: str) -> str:
    raw = str(text or "")
    if not raw:
        return raw

    def _replace(match: re.Match[str]) -> str:
        open_tag = match.group(0)
        attrs: dict[str, str] = {}
        for attr_match in _ATTR_RE.finditer(open_tag):
            key = str(attr_match.group(1) or "").strip().lower()
            value = str(attr_match.group(3) or "").strip()
            if key and key not in attrs:
                attrs[key] = value

        ref_id = parse_ref_number_from_attrs(attrs)
        if ref_id <= 0:
            return open_tag

        normalized = [
            f"href='#evidence-{ref_id}'",
            f"id='citation-{ref_id}'",
            "class='citation'",
            f"data-evidence-id='evidence-{ref_id}'",
        ]
        citation_number = " ".join(str(attrs.get("data-citation-number") or "").split()).strip()
        if citation_number.isdigit():
            normalized.append(f"data-citation-number='{citation_number}'")

        for key in ("data-file-id", "data-source-url", "data-page", "data-strength", "data-strength-tier"):
            value = " ".join(str(attrs.get(key) or "").split()).strip()
            if value:
                safe = value.replace("'", "&#39;")
                normalized.append(f"{key}='{safe}'")

        return f"<a {' '.join(normalized)}>"

    return _CITATION_ANCHOR_OPEN_RE.sub(_replace, raw)


def strip_redundant_evidence_suffix(text: str) -> str:
    raw = str(text or "")
    if not raw:
        return raw
    has_citations = bool(
        re.search(r"(^|\n)##\s+Evidence\s+Citations\b", raw, flags=re.IGNORECASE)
        or re.search(r"\[\d{1,3}\]", raw)
    )
    if not has_citations:
        return raw
    return _EVIDENCE_SUFFIX_BLOCK_RE.sub("", raw).strip()


def dedupe_terminal_sections(text: str) -> str:
    raw = str(text or "")
    if not raw:
        return raw
    matches = list(_TOP_LEVEL_SECTION_RE.finditer(raw))
    if not matches:
        return raw

    kept_chunks: list[str] = []
    cursor = 0
    seen: set[str] = set()
    for idx, match in enumerate(matches):
        section_start = match.start()
        section_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(raw)
        kept_chunks.append(raw[cursor:section_start])
        title_key = " ".join(str(match.group(1) or "").lower().split()).strip()
        if title_key in _DEDUPE_SECTION_TITLES:
            if title_key in seen:
                cursor = section_end
                continue
            seen.add(title_key)
        kept_chunks.append(raw[section_start:section_end])
        cursor = section_end
    kept_chunks.append(raw[cursor:])
    normalized = "".join(kept_chunks)
    normalized = re.sub(r"\n{4,}", "\n\n\n", normalized)
    return normalized.strip()


def section_title_key(value: str) -> str:
    return " ".join(str(value or "").lower().split()).strip()


def strip_noise_sections(text: str, *, keep_diagnostics: bool) -> str:
    raw = str(text or "")
    if not raw or keep_diagnostics:
        return raw
    matches = list(_TOP_LEVEL_SECTION_RE.finditer(raw))
    if not matches:
        return raw

    kept_chunks: list[str] = []
    cursor = 0
    for idx, match in enumerate(matches):
        section_start = match.start()
        section_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(raw)
        kept_chunks.append(raw[cursor:section_start])
        title_key = section_title_key(match.group(1))
        should_strip = (
            title_key in _NOISY_SECTION_TITLES
            or any(token in title_key for token in _NOISY_SECTION_SUBSTRINGS)
        )
        if not should_strip:
            kept_chunks.append(raw[section_start:section_end])
        cursor = section_end
    kept_chunks.append(raw[cursor:])
    normalized = "".join(kept_chunks)
    return re.sub(r"\n{4,}", "\n\n\n", normalized).strip()


def diagnostics_requested(request_message: str) -> bool:
    message = " ".join(str(request_message or "").split()).strip().lower()
    if not message:
        return False
    return bool(
        re.search(
            r"\b(debug|diagnostic|log|trace|contract gate|delivery status|execution plan|internal)\b",
            message,
        )
    )


def target_character_range(
    *,
    deep_research_mode: bool,
    verification_report: dict[str, Any],
    analytical_report: bool = False,
) -> tuple[int, int]:
    evidence_units = verification_report.get("evidence_units")
    evidence_count = len(evidence_units) if isinstance(evidence_units, list) else 0
    if deep_research_mode:
        if analytical_report:
            if evidence_count >= 12:
                return 8000, 20000
            if evidence_count >= 6:
                return 6000, 16000
            return 4000, 12000
        if evidence_count >= 12:
            return 3600, 8200
        if evidence_count >= 6:
            return 3000, 7200
        return 2200, 6200
    return 900, 2800


def is_analytical_report_question(request_message: str, *, deep_research_mode: bool = False) -> bool:
    text = str(request_message or "").strip()
    if not text:
        return False
    if deep_research_mode:
        return True
    return bool(_ANALYTICAL_INTENT_RE.search(text))


def normalize_for_language_detection(text: str) -> str:
    raw = str(text or "")
    if not raw.strip():
        return ""
    cleaned = _FENCED_BLOCK_RE.sub(" ", raw)
    cleaned = _INLINE_CODE_RE.sub(" ", cleaned)
    cleaned = _MARKDOWN_LINK_RE.sub(lambda match: f" {match.group(1)} ", cleaned)
    cleaned = _URL_RE.sub(" ", cleaned)
    cleaned = _HTML_TAG_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:2400]


def is_language_mismatch(
    *,
    request_message: str,
    requested_language: str | None,
    candidate_text: str,
    language_resolver: Callable[[str | None, str], str],
    language_inferer: Callable[[str], str],
) -> bool:
    request_clean = normalize_for_language_detection(request_message)
    candidate_clean = normalize_for_language_detection(candidate_text)
    if len(candidate_clean) < 80:
        return False
    expected = language_resolver(requested_language, request_clean)
    observed = language_inferer(candidate_clean)
    if not expected or not observed or expected == observed:
        return False
    return True


def strip_wrapping_markdown_fence(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    lines = cleaned.splitlines()
    while (
        len(lines) >= 3
        and lines[0].strip().startswith("```")
        and lines[-1].strip() == "```"
    ):
        lines = lines[1:-1]
    return "\n".join(lines).strip()


def emails_from_text(*parts: str) -> set[str]:
    emails: set[str] = set()
    for part in parts:
        for match in _EMAIL_RE.findall(str(part or "")):
            normalized = match.strip().lower()
            if normalized:
                emails.add(normalized)
    return emails


def redact_emails(text: str, *, emails: set[str]) -> str:
    result = str(text or "")
    if not result or not emails:
        return result
    for email in sorted(emails, key=len, reverse=True):
        result = re.sub(re.escape(email), "the recipient", result, flags=re.IGNORECASE)
    return result


def coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return None
