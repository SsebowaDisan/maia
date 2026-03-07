from __future__ import annotations

import re
import unicodedata
from typing import Any

from api.services.agent.llm_runtime import call_json_response

LEGACY_FALLBACK_CONVERSATION_ICON = "\U0001F4AC"
DEFAULT_CONVERSATION_LABEL = "New chat"
MAX_CONVERSATION_NAME_LEN = 25
DEFAULT_CONVERSATION_ICON_KEY = "message-circle"
CONVERSATION_ICON_KEY_FIELD = "conversation_icon_key"
CONVERSATION_ICON_REVIEWED_FIELD = "conversation_icon_reviewed"
ALLOWED_CONVERSATION_ICON_KEYS = (
    "message-circle",
    "briefcase",
    "bar-chart-3",
    "globe",
    "file-text",
    "search",
    "lightbulb",
    "calendar",
    "mail",
    "building-2",
    "shield",
    "rocket",
    "wrench",
    "code-2",
    "book-open",
    "list-checks",
)
_ALLOWED_CONVERSATION_ICON_KEY_SET = set(ALLOWED_CONVERSATION_ICON_KEYS)
_ICON_KEY_ALIASES = {
    "message": "message-circle",
    "chat": "message-circle",
    "conversation": "message-circle",
    "briefcase": "briefcase",
    "business": "briefcase",
    "company": "building-2",
    "building": "building-2",
    "chart": "bar-chart-3",
    "analytics": "bar-chart-3",
    "graph": "bar-chart-3",
    "globe": "globe",
    "web": "globe",
    "file": "file-text",
    "document": "file-text",
    "doc": "file-text",
    "search": "search",
    "research": "search",
    "idea": "lightbulb",
    "lightbulb": "lightbulb",
    "calendar": "calendar",
    "schedule": "calendar",
    "mail": "mail",
    "email": "mail",
    "building-2": "building-2",
    "shield": "shield",
    "security": "shield",
    "rocket": "rocket",
    "launch": "rocket",
    "wrench": "wrench",
    "tool": "wrench",
    "code": "code-2",
    "code2": "code-2",
    "code-2": "code-2",
    "book": "book-open",
    "book-open": "book-open",
    "list": "list-checks",
    "checklist": "list-checks",
    "list-checks": "list-checks",
}

_SPACE_RE = re.compile(r"\s+")
_URL_RE = re.compile(r"https?://\S+", flags=re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(r"^untitled(\s*-\s*.*)?$", flags=re.IGNORECASE)


def _clean_text(value: Any) -> str:
    text = _SPACE_RE.sub(" ", str(value or "").strip())
    return text.strip()


def _starts_with_icon(text: str) -> bool:
    if not text:
        return False
    first = next(iter(text), "")
    if not first:
        return False
    category = unicodedata.category(first)
    if category.startswith(("L", "N")):
        return False
    codepoint = ord(first)
    return category in {"So", "Sk"} or codepoint >= 0x2600


def _truncate_words(text: str, *, max_len: int = MAX_CONVERSATION_NAME_LEN) -> str:
    cleaned = _clean_text(text)
    if len(cleaned) <= max_len:
        return cleaned
    trimmed = cleaned[:max_len].rstrip()
    if len(trimmed) < max_len:
        return trimmed
    next_char = cleaned[max_len : max_len + 1]
    # If truncation already lands on a word boundary, keep the boundary text.
    if not next_char or next_char.isspace():
        return trimmed
    if " " not in trimmed:
        return trimmed
    return trimmed.rsplit(" ", 1)[0].rstrip()


def _extract_icon_candidate(value: Any) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    for char in text:
        if _starts_with_icon(char):
            return char
    return None


def normalize_conversation_icon_key(value: Any) -> str | None:
    text = _clean_text(value).lower()
    if not text:
        return None
    normalized = re.sub(r"[^a-z0-9\-_ ]+", "", text)
    normalized = normalized.replace("_", "-").replace(" ", "-")
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    if not normalized:
        return None
    if normalized in _ALLOWED_CONVERSATION_ICON_KEY_SET:
        return normalized
    alias = _ICON_KEY_ALIASES.get(normalized)
    if alias:
        return alias
    first_token = normalized.split("-", 1)[0].strip()
    if first_token:
        alias = _ICON_KEY_ALIASES.get(first_token)
        if alias:
            return alias
    return None


def _fallback_icon_key_from_text(text: str, *, agent_mode: str = "ask") -> str:
    normalized = _clean_text(text)
    if not normalized and str(agent_mode).strip().lower() == "company_agent":
        return "briefcase"
    if str(agent_mode).strip().lower() == "company_agent":
        return "briefcase"
    return DEFAULT_CONVERSATION_ICON_KEY


def extract_conversation_icon(name: str) -> str | None:
    text = _clean_text(name)
    if not text:
        return None
    first = next(iter(text), "")
    if _starts_with_icon(first):
        return first
    return None


def strip_icon_prefix(name: str) -> str:
    text = _clean_text(name)
    if not text:
        return ""
    chars = list(text)
    if len(chars) >= 2 and _starts_with_icon(chars[0]) and chars[1] == " ":
        return _clean_text("".join(chars[2:]))
    return text


def is_placeholder_conversation_name(name: str) -> bool:
    text = strip_icon_prefix(name)
    if not text:
        return True
    lowered = text.lower()
    if lowered == DEFAULT_CONVERSATION_LABEL.lower():
        return True
    return bool(_PLACEHOLDER_RE.match(text))


def normalize_conversation_name(
    name: str,
    *,
    fallback: str | None = None,
    icon: str | None = None,
) -> str:
    raw = _clean_text(name)
    _ = icon
    core = strip_icon_prefix(raw)
    if not core or is_placeholder_conversation_name(core):
        core = _clean_text(fallback or DEFAULT_CONVERSATION_LABEL)
    core = _truncate_words(core)
    if not core:
        core = DEFAULT_CONVERSATION_LABEL
    return core


def _fallback_title_from_message(message: str, *, agent_mode: str = "ask") -> str:
    cleaned = _clean_text(_URL_RE.sub("", message))
    cleaned = cleaned.strip(" -_.,:;!?`'\"")
    if not cleaned:
        base = "Company assistant" if str(agent_mode).strip() == "company_agent" else DEFAULT_CONVERSATION_LABEL
        return _truncate_words(base)

    tokens = [token for token in cleaned.split(" ") if token]
    title = " ".join(tokens[:10]).strip()
    if not title:
        title = "Company assistant" if str(agent_mode).strip() == "company_agent" else DEFAULT_CONVERSATION_LABEL
    return _truncate_words(title)


def _llm_icon_and_title(message: str, *, agent_mode: str) -> tuple[str | None, str | None]:
    payload = call_json_response(
        system_prompt=(
            "Generate a conversation title as JSON.\n"
            "Return exactly one JSON object with keys:\n"
            '- "title": descriptive chat title, 3-7 words, max 25 characters, no emoji\n'
            f'- "icon_key": one of {", ".join(ALLOWED_CONVERSATION_ICON_KEYS)}\n'
            'Choose the icon that best matches the chat topic. Avoid "message-circle" unless the topic is truly generic.\n'
            "No markdown and no extra text."
        ),
        user_prompt=(
            f"Agent mode: {agent_mode}\n"
            f"User first message: {message}\n\n"
            "Return JSON:"
        ),
        temperature=0.2,
        timeout_seconds=8,
        max_tokens=80,
    )
    if not isinstance(payload, dict):
        return None, None
    title = _clean_text(payload.get("title"))
    title = title.splitlines()[0].strip() if title else ""
    title = title.removeprefix("Title:").strip().strip("`\"' ")
    icon_key = normalize_conversation_icon_key(
        payload.get("icon_key") or payload.get("icon")
    )
    return icon_key, title or None


def generate_conversation_name(message: str, *, agent_mode: str = "ask") -> str:
    name, _icon_key = generate_conversation_identity(message, agent_mode=agent_mode)
    return name


def generate_conversation_icon_key(message: str, *, agent_mode: str = "ask") -> str:
    _name, icon_key = generate_conversation_identity(message, agent_mode=agent_mode)
    return icon_key


def infer_conversation_icon_key(value: str, *, agent_mode: str = "ask") -> str:
    normalized = normalize_conversation_icon_key(value)
    if normalized:
        return normalized
    llm_icon_key, _title = _llm_icon_and_title(_clean_text(value), agent_mode=agent_mode)
    llm_normalized = normalize_conversation_icon_key(llm_icon_key)
    if llm_normalized:
        return llm_normalized
    return _fallback_icon_key_from_text(value, agent_mode=agent_mode)


def generate_conversation_identity(
    message: str,
    *,
    agent_mode: str = "ask",
) -> tuple[str, str]:
    user_message = _clean_text(message)
    if not user_message:
        return normalize_conversation_name(""), DEFAULT_CONVERSATION_ICON_KEY

    llm_icon_key, candidate = _llm_icon_and_title(user_message, agent_mode=agent_mode)
    if not candidate or is_placeholder_conversation_name(candidate):
        candidate = _fallback_title_from_message(user_message, agent_mode=agent_mode)
    normalized_name = normalize_conversation_name(candidate)
    icon_key = normalize_conversation_icon_key(llm_icon_key) or _fallback_icon_key_from_text(
        f"{normalized_name} {user_message}",
        agent_mode=agent_mode,
    )
    return normalized_name, icon_key


def is_legacy_fallback_icon(icon: str | None) -> bool:
    return str(icon or "").strip() == LEGACY_FALLBACK_CONVERSATION_ICON
