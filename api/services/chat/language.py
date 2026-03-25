"""Language detection and response language resolution.

Uses the LLM to detect the user's language and any explicit language
requests — no hardcoded stopwords, no regex script detection.

The LLM handles: language detection, Persian vs Arabic distinction,
explicit "answer in X" commands, and cross-lingual response instructions.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE_RULE = (
    "Language rule: respond in the same language as the user's latest message. "
    "If the user explicitly asks for translation or another language, follow that request. "
    "IMPORTANT: The source documents may be in a different language than the user's question. "
    "By default, translate evidence from the source language to the user's language. "
    "Cite the original source but present findings in the user's language. "
    "If the user asks for text in the source's original language "
    "(e.g., 'show the original French text', 'quote it in German'), "
    "preserve the original language for those excerpts. "
    "You may include both original and translation when helpful."
)

# Label lookup for known codes — only used for display, NOT for detection
_LANGUAGE_LABELS: dict[str, str] = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German",
    "it": "Italian", "pt": "Portuguese", "nl": "Dutch", "ru": "Russian",
    "ar": "Arabic", "fa": "Persian", "hi": "Hindi", "ur": "Urdu",
    "tr": "Turkish", "ja": "Japanese", "ko": "Korean", "zh": "Chinese",
    "pl": "Polish", "sv": "Swedish", "da": "Danish", "fi": "Finnish",
    "no": "Norwegian", "el": "Greek", "he": "Hebrew", "th": "Thai",
    "vi": "Vietnamese", "id": "Indonesian", "ms": "Malay", "sw": "Swahili",
    "uk": "Ukrainian", "cs": "Czech", "ro": "Romanian", "hu": "Hungarian",
    "bn": "Bengali", "ta": "Tamil",
}


def _normalize_language_code(value: Any) -> str:
    text = " ".join(str(value or "").split()).strip().lower()
    if not text:
        return ""
    text = text.replace("_", "-")
    parts = [part for part in text.split("-") if part]
    if not parts:
        return ""
    primary = "".join(c for c in parts[0] if c.isalpha())[:8]
    return primary


def infer_user_language_code(text: str) -> str | None:
    """Infer language using the LLM — handles all languages, scripts, and dialects.

    Falls back to "en" if the LLM is unavailable.
    """
    normalized = " ".join(str(text or "").split()).strip()
    if not normalized:
        return None
    if len(normalized) < 3:
        return "en"

    try:
        from api.services.agent.llm_runtime import call_json_response
        result = call_json_response(
            system_prompt=(
                "You are a language detector. Given a text, determine:\n"
                "1. What language the text is written in (ISO 639-1 code)\n"
                "2. Whether the user explicitly requests a specific response language "
                "(e.g., 'answer in German', 'respond in Arabic', 'auf Deutsch antworten')\n\n"
                "Return JSON: {\"detected_language\": \"xx\", \"requested_language\": \"xx\" or null}\n\n"
                "Be precise: distinguish Persian (fa) from Arabic (ar), "
                "Ukrainian (uk) from Russian (ru), etc."
            ),
            user_prompt=normalized[:500],
            temperature=0.0,
            timeout_seconds=8,
            max_tokens=100,
        )
        if isinstance(result, dict):
            detected = _normalize_language_code(result.get("detected_language"))
            requested = _normalize_language_code(result.get("requested_language"))
            # Explicit request takes priority
            if requested:
                return requested
            if detected:
                return detected
    except Exception as exc:
        logger.debug("LLM language detection failed, using fallback: %s", exc)

    # Fallback: if LLM unavailable, assume English for Latin text
    if any(c.isascii() and c.isalpha() for c in normalized):
        return "en"
    return None


def resolve_response_language(
    requested_language: str | None,
    latest_message: str,
) -> str | None:
    """Resolve which language the response should be in.

    Priority:
    1. Explicit requested_language parameter (from settings/API)
    2. LLM detection of user's message language + any inline request
    """
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
    """Build the language instruction for the LLM system prompt.

    Handles:
    - User asks in Arabic → respond in Arabic
    - User asks in Persian → respond in Persian (not Arabic)
    - User says "answer in German" → respond in German
    - Source documents in French, user asks in English → translate to English
    """
    resolved = resolve_response_language(requested_language, latest_message)
    label = response_language_label(resolved)
    if label:
        return (
            f"Language rule: respond in {label}. "
            "If the user explicitly asks for translation or another language, follow that request. "
            "IMPORTANT: The source documents may be in a different language than the user's question. "
            "By default, translate evidence and findings into the response language. "
            "Cite the original source but present all content in the response language. "
            "EXCEPTION: If the user explicitly asks for text in the source's original language "
            "(e.g., 'give me the original German text', 'show the French paragraph', "
            "'quote it in Arabic'), preserve the original language for those specific excerpts. "
            "You may include both the original text and a translation when helpful."
        )
    return DEFAULT_LANGUAGE_RULE
