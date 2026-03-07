from __future__ import annotations

import re
from typing import Any

DEFAULT_LANGUAGE_RULE = (
    "Language rule: respond in the same language as the user's latest message. "
    "If the user explicitly asks for translation or another language, follow that request."
)

_LANGUAGE_LABELS: dict[str, str] = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "ru": "Russian",
    "ar": "Arabic",
    "hi": "Hindi",
    "tr": "Turkish",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
}

_SCRIPT_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("ar", re.compile(r"[\u0600-\u06FF]")),
    ("ru", re.compile(r"[\u0400-\u04FF]")),
    ("hi", re.compile(r"[\u0900-\u097F]")),
    ("th", re.compile(r"[\u0E00-\u0E7F]")),
    ("ja", re.compile(r"[\u3040-\u30FF]")),  # Hiragana + Katakana
    ("ko", re.compile(r"[\uAC00-\uD7AF]")),  # Hangul
    ("zh", re.compile(r"[\u4E00-\u9FFF]")),  # Han
]

_LATIN_STOPWORDS: dict[str, set[str]] = {
    "es": {
        "el", "la", "los", "las", "de", "del", "que", "en", "y", "para", "con", "como", "por",
    },
    "fr": {
        "le", "la", "les", "des", "de", "du", "et", "en", "pour", "avec", "comme", "est",
    },
    "de": {
        "der", "die", "das", "und", "ist", "mit", "für", "auf", "ein", "eine", "den", "dem",
    },
    "it": {
        "il", "lo", "la", "gli", "le", "di", "del", "e", "con", "per", "come", "che",
    },
    "pt": {
        "o", "a", "os", "as", "de", "do", "da", "e", "com", "para", "que", "como",
    },
    "nl": {
        "de", "het", "een", "en", "van", "voor", "met", "op", "dat", "is", "als",
    },
    "tr": {
        "ve", "bir", "bu", "için", "ile", "gibi", "da", "de", "ne", "olan",
    },
}

_LATIN_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ']+")
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", re.IGNORECASE)
_URL_ARTIFACT_TOKENS = {"http", "https", "www"}
_ALLOWED_SHORT_TOKENS = {"y", "e"}


def _normalize_language_code(value: Any) -> str:
    text = " ".join(str(value or "").split()).strip().lower()
    if not text:
        return ""
    text = text.replace("_", "-")
    parts = [part for part in text.split("-") if part]
    if not parts:
        return ""
    primary = re.sub(r"[^a-z]", "", parts[0])[:8]
    if not primary:
        return ""
    return primary


def _infer_latin_language_code(text: str) -> str | None:
    tokens = [
        token.lower()
        for token in _LATIN_TOKEN_RE.findall(text)
        if (len(token) >= 2 or token.lower() in _ALLOWED_SHORT_TOKENS)
        and token.lower() not in _URL_ARTIFACT_TOKENS
    ][:100]
    if len(tokens) < 3:
        return None
    scores: dict[str, int] = {}
    distinct_hits: dict[str, set[str]] = {}
    for code, words in _LATIN_STOPWORDS.items():
        matched = {token for token in tokens if token in words}
        score = len(matched)
        if score > 0:
            scores[code] = score
            distinct_hits[code] = matched
    if not scores:
        return None
    best_code, best_score = max(scores.items(), key=lambda item: item[1])
    second_score = max((score for code, score in scores.items() if code != best_code), default=0)
    best_distinct = len(distinct_hits.get(best_code) or set())
    if best_score <= 1 or best_distinct <= 1 or (best_score == second_score):
        return None
    return best_code


def infer_user_language_code(text: str) -> str | None:
    normalized = " ".join(str(text or "").split()).strip()
    if not normalized:
        return None
    normalized = _MARKDOWN_LINK_RE.sub(lambda match: f" {match.group(1)} ", normalized)
    normalized = _URL_RE.sub(" ", normalized)
    normalized = _EMAIL_RE.sub(" ", normalized)
    for code, pattern in _SCRIPT_RULES:
        if pattern.search(normalized):
            return code
    latin_code = _infer_latin_language_code(normalized)
    if latin_code:
        return latin_code
    if re.search(r"[A-Za-z]", normalized):
        return "en"
    return None


def resolve_response_language(
    requested_language: str | None,
    latest_message: str,
) -> str | None:
    requested = _normalize_language_code(requested_language)
    if requested:
        return requested
    return infer_user_language_code(latest_message)


def response_language_label(code: str | None) -> str:
    normalized = _normalize_language_code(code)
    if not normalized:
        return ""
    return _LANGUAGE_LABELS.get(normalized, normalized)


def build_response_language_rule(
    *,
    requested_language: str | None,
    latest_message: str,
) -> str:
    resolved = resolve_response_language(requested_language, latest_message)
    label = response_language_label(resolved)
    if label:
        return (
            f"Language rule: respond in {label}. "
            "If the user explicitly asks for translation or another language, follow that request."
        )
    return DEFAULT_LANGUAGE_RULE
