from __future__ import annotations

import re
from urllib.parse import urlparse

from api.schemas import ChatRequest

URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")


def extract_url(text: str) -> str:
    match = URL_RE.search(text)
    return match.group(0).strip() if match else ""


def extract_email(text: str) -> str:
    match = EMAIL_RE.search(text)
    return match.group(1).strip() if match else ""


def sanitize_search_query(text: str, *, fallback_url: str = "") -> str:
    sanitized = EMAIL_RE.sub("", text or "")
    sanitized = URL_RE.sub("", sanitized)
    sanitized = " ".join(sanitized.split())
    if sanitized:
        return sanitized
    if fallback_url:
        host = (urlparse(fallback_url).hostname or "").strip()
        if host:
            return f"site:{host} company overview services"
    return "company overview services"


def preferred_highlight_color(_: str) -> str:
    return "yellow"


def intent_signals(request: ChatRequest) -> dict[str, object]:
    message = str(request.message or "").strip()
    goal = str(request.agent_goal or "").strip()
    combined = f"{message} {goal}".strip()
    url = extract_url(combined)
    recipient = extract_email(combined)
    return {
        "url": url,
        "recipient_email": recipient,
        "explicit_web_discovery": False,
        "wants_location_info": False,
        "wants_send": bool(recipient),
        "wants_report": False,
        "wants_highlight_words": False,
        "wants_contact_form": False,
        "wants_docs_output": False,
        "wants_file_scope": False,
        "highlight_color": preferred_highlight_color(combined),
    }

