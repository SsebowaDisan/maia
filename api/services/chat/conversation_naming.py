from __future__ import annotations

import re
import unicodedata
from typing import Any

from api.services.agent.llm_runtime import call_json_response, call_text_response

FALLBACK_CONVERSATION_ICON = "💬"
DEFAULT_CONVERSATION_LABEL = "New chat"
MAX_CONVERSATION_NAME_LEN = 72

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
    final_icon = (
        extract_conversation_icon(raw)
        or _extract_icon_candidate(icon)
        or FALLBACK_CONVERSATION_ICON
    )
    core = strip_icon_prefix(raw)
    if not core or is_placeholder_conversation_name(core):
        core = _clean_text(fallback or DEFAULT_CONVERSATION_LABEL)
    core = _truncate_words(core)
    if not core:
        core = DEFAULT_CONVERSATION_LABEL
    return f"{final_icon} {core}"


def _fallback_title_from_message(message: str, *, agent_mode: str = "ask") -> str:
    cleaned = _clean_text(_URL_RE.sub("", message))
    cleaned = cleaned.strip(" -_.,:;!?`'\"")
    if not cleaned:
        base = "Company assistant" if str(agent_mode).strip() == "company_agent" else DEFAULT_CONVERSATION_LABEL
        return _truncate_words(base)

    tokens = [token for token in cleaned.split(" ") if token]
    title = " ".join(tokens[:7]).strip()
    if not title:
        title = "Company assistant" if str(agent_mode).strip() == "company_agent" else DEFAULT_CONVERSATION_LABEL
    return _truncate_words(title)


def _llm_icon_from_message(message: str, *, agent_mode: str, title: str) -> str | None:
    llm_icon = call_text_response(
        system_prompt=(
            "Choose one emoji icon for a chat.\n"
            "Rules:\n"
            "- Return exactly one emoji and nothing else.\n"
            "- Make the emoji reflect the user's intent.\n"
            "- Do not return words."
        ),
        user_prompt=(
            f"Agent mode: {agent_mode}\n"
            f"Title: {title}\n"
            f"User first message: {message}\n\n"
            "Return emoji:"
        ),
        temperature=0.1,
        timeout_seconds=8,
        max_tokens=8,
    )
    return _extract_icon_candidate(llm_icon)


def _llm_icon_and_title(message: str, *, agent_mode: str) -> tuple[str | None, str | None]:
    payload = call_json_response(
        system_prompt=(
            "Generate conversation metadata as JSON.\n"
            "Return exactly one JSON object with keys:\n"
            '- "icon": one emoji only\n'
            '- "title": concise chat title, 2-6 words, no emoji\n'
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
    icon = _extract_icon_candidate(payload.get("icon"))
    return icon, title or None


def generate_conversation_name(message: str, *, agent_mode: str = "ask") -> str:
    user_message = _clean_text(message)
    if not user_message:
        return normalize_conversation_name("")

    icon, candidate = _llm_icon_and_title(user_message, agent_mode=agent_mode)
    if not candidate or is_placeholder_conversation_name(candidate):
        candidate = _fallback_title_from_message(user_message, agent_mode=agent_mode)
    if not icon:
        icon = _llm_icon_from_message(user_message, agent_mode=agent_mode, title=candidate)
    return normalize_conversation_name(candidate, icon=icon)
