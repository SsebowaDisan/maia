from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
MARKDOWN_LINK_URL_RE = re.compile(r"\[[^\]]+\]\((https?://[^)\s]+)\)", re.IGNORECASE)
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
DELIVERY_TARGET_HINT_RE = re.compile(
    r"(?:recipient(?:\s+for\s+(?:the\s+)?)?(?:findings|research report|report)?\s*[:=]\s*([^\n.;]+))",
    re.IGNORECASE,
)
DELIVERY_TARGET_ALT_RE = re.compile(
    r"(?:delivery\s+target\s*[:=]\s*([^\n.;]+))",
    re.IGNORECASE,
)
NO_HARDCODE_WORDS_CONSTRAINT = (
    "Never use hardcoded words or keyword lists; rely on LLM semantic understanding."
)


def clean_text_list(raw: Any, *, limit: int, max_item_len: int = 220) -> list[str]:
    if not isinstance(raw, list):
        return []
    rows: list[str] = []
    for item in raw:
        text = " ".join(str(item or "").split()).strip()
        if not text or text in rows:
            continue
        rows.append(text[:max_item_len])
        if len(rows) >= max(1, int(limit)):
            break
    return rows


def enforce_contract_constraints(raw: Any) -> list[str]:
    rows = clean_text_list(raw, limit=6)
    if NO_HARDCODE_WORDS_CONSTRAINT in rows:
        return rows[:6]
    return [NO_HARDCODE_WORDS_CONSTRAINT, *rows][:6]


def normalize_for_match(text: str) -> str:
    return " ".join(str(text or "").lower().split()).strip()


def tokenize_for_scope(text: str) -> set[str]:
    def _canonical_token(raw: str) -> str:
        token = str(raw or "").strip().lower()
        for suffix in (
            "ization",
            "ation",
            "ions",
            "ion",
            "ments",
            "ment",
            "ities",
            "ity",
            "ing",
            "ed",
            "s",
        ):
            if token.endswith(suffix) and (len(token) - len(suffix)) >= 4:
                token = token[: -len(suffix)]
                break
        return token

    return {
        _canonical_token(match.group(0))
        for match in WORD_RE.finditer(str(text or ""))
        if len(match.group(0)) >= 4
    }


def scope_filter_required_facts(
    *,
    rows: list[str],
    message: str,
    agent_goal: str,
) -> list[str]:
    request_tokens = tokenize_for_scope(" ".join([message, agent_goal]))
    if not request_tokens:
        return rows[:6]
    filtered: list[str] = []
    for row in rows:
        fact_tokens = tokenize_for_scope(row)
        if not fact_tokens:
            continue
        overlap = fact_tokens.intersection(request_tokens)
        if len(overlap) >= 1:
            filtered.append(row)
            if len(filtered) >= 6:
                break
    return filtered


def normalize_url_candidate(raw_url: str) -> str:
    text = str(raw_url or "").strip()
    if not text:
        return ""

    if "](" in text:
        parts = [part.strip() for part in text.split("](") if part.strip()]
        for part in parts:
            normalized_part = normalize_url_candidate(part)
            if normalized_part:
                return normalized_part
        return ""

    text = text.strip("<>[]()\"'")
    text = text.rstrip(".,;)")
    text = text.rstrip("]")
    if not text.startswith(("http://", "https://")):
        return ""
    parsed = urlparse(text)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return text


def extract_first_url(*chunks: str) -> str:
    joined = " ".join(str(chunk or "").strip() for chunk in chunks if str(chunk or "").strip())
    markdown_match = MARKDOWN_LINK_URL_RE.search(joined)
    if markdown_match:
        clean_markdown_url = normalize_url_candidate(markdown_match.group(1))
        if clean_markdown_url:
            return clean_markdown_url
    match = URL_RE.search(joined)
    if not match:
        return ""
    return normalize_url_candidate(match.group(0))


def extract_delivery_target(*chunks: str) -> str:
    joined = "\n".join(str(chunk or "").strip() for chunk in chunks if str(chunk or "").strip())
    if not joined:
        return ""

    match = EMAIL_RE.search(joined)
    if match:
        return match.group(1).strip()

    for pattern in (DELIVERY_TARGET_HINT_RE, DELIVERY_TARGET_ALT_RE):
        hint_match = pattern.search(joined)
        if not hint_match:
            continue
        candidate = " ".join(str(hint_match.group(1) or "").split()).strip(" .,;:")
        if candidate:
            return candidate[:180]
    return ""
