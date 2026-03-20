from __future__ import annotations

from functools import lru_cache
import re
from urllib.parse import urlparse

from api.schemas import ChatRequest
from api.services.agent.llm_intent import (
    ALLOWED_WEB_ROUTING_MODES,
    classify_intent_tags,
    detect_web_routing_mode,
    enrich_task_intelligence,
)

# Greedily match URLs but strip common trailing punctuation (.,;:)>'"]) via negative lookbehind.
URL_RE = re.compile(r"https?://[^\s]+(?<![.,;:)\]>\"'])", re.IGNORECASE)
EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
PLANNING_CONTEXT_PREFIXES = (
    "contract objective:",
    "required outputs:",
    "required facts:",
    "success checks:",
    "deliverables:",
    "constraints:",
    "conversation context:",
)


def extract_url(text: str) -> str:
    match = URL_RE.search(text)
    return match.group(0).strip() if match else ""


def extract_email(text: str) -> str:
    match = EMAIL_RE.search(text)
    return match.group(1).strip() if match else ""


def sanitize_search_query(text: str, *, fallback_url: str = "") -> str:
    cleaned_lines: list[str] = []
    for raw_line in str(text or "").splitlines():
        normalized_line = " ".join(raw_line.split()).strip()
        if not normalized_line:
            continue
        lowered = normalized_line.lower()
        if any(lowered.startswith(prefix) for prefix in PLANNING_CONTEXT_PREFIXES):
            continue
        cleaned_lines.append(normalized_line)
    cleaned_text = " ".join(cleaned_lines) if cleaned_lines else str(text or "")

    sanitized = EMAIL_RE.sub("", cleaned_text)
    sanitized = URL_RE.sub("", sanitized)
    sanitized = " ".join(sanitized.split())
    if sanitized:
        return sanitized[:220]
    if fallback_url:
        host = (urlparse(fallback_url).hostname or "").strip()
        if host:
            return f"site:{host}"
    return "web research request"


def preferred_highlight_color(_: str) -> str:
    return "yellow"


def _coerce_bool(value: object) -> bool | None:
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


def _heuristic_intent_tags(heuristic: dict[str, object]) -> list[str]:
    tags: list[str] = []
    if bool(heuristic.get("requires_web_inspection")) or bool(heuristic.get("target_url")):
        tags.append("web_research")
    if bool(heuristic.get("requested_report")):
        tags.append("report_generation")
    if bool(heuristic.get("requires_delivery")) or bool(heuristic.get("delivery_email")):
        tags.append("email_delivery")
    if bool(heuristic.get("requires_contact_form_submission")):
        tags.append("contact_form_submission")
    if bool(heuristic.get("wants_docs_output")):
        tags.append("docs_write")
    if bool(heuristic.get("wants_sheets_output")):
        tags.append("sheets_update")
    if bool(heuristic.get("wants_highlight_extract")):
        tags.append("highlight_extract")
    if bool(heuristic.get("wants_location_lookup")):
        tags.append("location_lookup")
    return list(dict.fromkeys(tags))[:8]


@lru_cache(maxsize=2048)
def _infer_intent_signals_cached(
    message: str,
    agent_goal: str,
    llm_intent_enabled: bool,
    llm_intent_tags_enabled: bool,
    llm_web_routing_enabled: bool,
) -> dict[str, object]:
    message_text = str(message or "").strip()
    goal_text = str(agent_goal or "").strip()
    combined = f"{message_text} {goal_text}".strip()
    url = extract_url(combined)
    recipient = extract_email(combined)
    heuristic: dict[str, object] = {
        "url": url,
        "target_url": url,
        "recipient_email": recipient,
        "requires_delivery": bool(recipient),
        "requires_web_inspection": bool(url),
        "requires_contact_form_submission": False,
        "requested_report": False,
        "wants_docs_output": False,
        "wants_sheets_output": False,
        "wants_highlight_extract": False,
        "wants_location_lookup": False,
        "wants_file_scope": False,
        "requires_attachment_delivery": False,
    }

    llm_intent = (
        enrich_task_intelligence(
            message=message_text,
            agent_goal=goal_text,
            heuristic=heuristic,
        )
        if llm_intent_enabled
        else {}
    )
    if isinstance(llm_intent, dict):
        llm_url = str(llm_intent.get("target_url") or "").strip().rstrip(".,;)")
        if llm_url.startswith(("http://", "https://")):
            url = llm_url
        llm_email = str(llm_intent.get("delivery_email") or "").strip()
        if "@" in llm_email and "." in llm_email:
            recipient = llm_email

    merged_heuristic: dict[str, object] = {
        **heuristic,
        "url": url,
        "target_url": url,
        "recipient_email": recipient,
    }
    if isinstance(llm_intent, dict):
        merged_heuristic.update(llm_intent)

    tags = (
        classify_intent_tags(
            message=message_text,
            agent_goal=goal_text,
            heuristic=merged_heuristic,
        )
        if llm_intent_tags_enabled
        else _heuristic_intent_tags(merged_heuristic)
    )
    tag_set = {
        str(item).strip().lower()
        for item in tags
        if str(item).strip()
    }

    routing_mode = str(
        (llm_intent.get("routing_mode") if isinstance(llm_intent, dict) else "") or ""
    ).strip().lower()
    if routing_mode not in ALLOWED_WEB_ROUTING_MODES and llm_web_routing_enabled:
        routing = detect_web_routing_mode(
            message=message_text,
            agent_goal=goal_text,
            heuristic=merged_heuristic,
        )
        routing_mode = str(routing.get("routing_mode") or "").strip().lower()
    if routing_mode not in ALLOWED_WEB_ROUTING_MODES:
        if url:
            routing_mode = "url_scrape"
        else:
            routing_mode = "none"

    def _flag(key: str, *, default: bool = False) -> bool:
        value = llm_intent.get(key) if isinstance(llm_intent, dict) else None
        coerced = _coerce_bool(value)
        if coerced is not None:
            return coerced
        return default

    requires_web_inspection = _flag(
        "requires_web_inspection",
        default=bool(url),
    )
    requires_delivery = _flag("requires_delivery", default=bool(recipient))
    requires_contact_form_submission = _flag(
        "requires_contact_form_submission",
        default=False,
    )
    wants_report = _flag("requested_report", default=False) or (
        "report_generation" in tag_set
    )
    wants_docs_output = _flag("wants_docs_output", default=False) or (
        "docs_write" in tag_set
    )
    wants_sheets_output = _flag(
        "wants_sheets_output",
        default=False,
    ) or ("sheets_update" in tag_set)
    wants_highlight_words = _flag(
        "wants_highlight_extract",
        default=False,
    ) or ("highlight_extract" in tag_set)
    wants_location_info = _flag(
        "wants_location_lookup",
        default=False,
    ) or ("location_lookup" in tag_set)
    wants_file_scope = _flag("wants_file_scope", default=False)
    wants_attachment_delivery = _flag(
        "requires_attachment_delivery",
        default=False,
    )
    wants_send = (
        bool(recipient)
        or requires_delivery
        or ("email_delivery" in tag_set)
        or requires_contact_form_submission
    )
    explicit_web_discovery = routing_mode in {"online_research", "url_scrape"} or requires_web_inspection

    return {
        "url": url,
        "recipient_email": recipient,
        "routing_mode": routing_mode,
        "explicit_web_discovery": explicit_web_discovery,
        "wants_location_info": wants_location_info,
        "wants_send": wants_send,
        "wants_report": wants_report,
        "wants_highlight_words": wants_highlight_words,
        "wants_contact_form": requires_contact_form_submission or ("contact_form_submission" in tag_set),
        "wants_docs_output": wants_docs_output,
        "wants_sheets_output": wants_sheets_output,
        "wants_file_scope": wants_file_scope,
        "wants_attachment_delivery": wants_attachment_delivery,
        "highlight_color": preferred_highlight_color(combined),
    }


def infer_intent_signals_from_text(
    *,
    message: str,
    agent_goal: str | None = None,
) -> dict[str, object]:
    inferred = _infer_intent_signals_cached(
        str(message or ""),
        str(agent_goal or ""),
        True,
        True,
        True,
    )
    return dict(inferred)


def intent_signals(request: ChatRequest) -> dict[str, object]:
    return infer_intent_signals_from_text(
        message=str(request.message or ""),
        agent_goal=request.agent_goal,
    )
