from __future__ import annotations

import re
from urllib.parse import urlparse

from api.schemas import ChatRequest

URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")

WEB_DISCOVERY_HINTS = (
    "search online",
    "online research",
    "web research",
    "online sources",
    "internet",
    "browse",
    "look up",
    "latest",
    "recent",
    "news",
)
REPORT_HINTS = (
    "report",
    "summary",
    "writeup",
    "findings",
    "brief",
    "analysis",
)
DOCS_HINTS = (
    "google docs",
    "google doc",
    "write to docs",
    "write in docs",
    "research notes",
    "document",
    "doc ",
)
SHEETS_HINTS = (
    "google sheets",
    "google sheet",
    "spreadsheet",
    "sheet tracker",
    "tracker",
    "roadmap",
)
HIGHLIGHT_HINTS = (
    "highlight",
    "extract keywords",
    "keyword extraction",
    "highlight words",
    "copied words",
)
CONTACT_FORM_HINTS = (
    "contact form",
    "submit form",
    "inquiry form",
)
LOCATION_HINTS = (
    "where is",
    "where are",
    "location",
    "address",
    "distance",
    "route",
    "travel time",
)
FILE_SCOPE_HINTS = ("file", "files", "pdf", "document", "page", "pages")
SEND_HINTS = ("send", "email", "mail")


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
            return f"site:{host}"
    return "web research request"


def preferred_highlight_color(_: str) -> str:
    return "yellow"


def infer_intent_signals_from_text(
    *,
    message: str,
    agent_goal: str | None = None,
) -> dict[str, object]:
    message_text = str(message or "").strip()
    goal_text = str(agent_goal or "").strip()
    combined = f"{message_text} {goal_text}".strip()
    lowered = combined.lower()
    url = extract_url(combined)
    recipient = extract_email(combined)
    explicit_web_discovery = bool(url) or any(hint in lowered for hint in WEB_DISCOVERY_HINTS)
    wants_report = any(hint in lowered for hint in REPORT_HINTS)
    wants_docs_output = any(hint in lowered for hint in DOCS_HINTS)
    wants_sheets_output = any(hint in lowered for hint in SHEETS_HINTS)
    wants_highlight_words = any(hint in lowered for hint in HIGHLIGHT_HINTS)
    wants_contact_form = any(hint in lowered for hint in CONTACT_FORM_HINTS)
    wants_location_info = any(hint in lowered for hint in LOCATION_HINTS)
    wants_file_scope = any(hint in lowered for hint in FILE_SCOPE_HINTS)
    wants_send = bool(recipient) or any(hint in lowered for hint in SEND_HINTS)

    return {
        "url": url,
        "recipient_email": recipient,
        "explicit_web_discovery": explicit_web_discovery,
        "wants_location_info": wants_location_info,
        "wants_send": wants_send,
        "wants_report": wants_report,
        "wants_highlight_words": wants_highlight_words,
        "wants_contact_form": wants_contact_form,
        "wants_docs_output": wants_docs_output,
        "wants_sheets_output": wants_sheets_output,
        "wants_file_scope": wants_file_scope,
        "highlight_color": preferred_highlight_color(combined),
    }


def intent_signals(request: ChatRequest) -> dict[str, object]:
    return infer_intent_signals_from_text(
        message=str(request.message or ""),
        agent_goal=request.agent_goal,
    )
