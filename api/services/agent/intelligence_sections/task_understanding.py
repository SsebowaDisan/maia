from __future__ import annotations

import re
from urllib.parse import urlparse

from api.services.agent.llm_intent import classify_intent_tags, enrich_task_intelligence
from api.services.agent.planner_helpers import infer_intent_signals_from_text

from .constants import EMAIL_RE, URL_RE
from .models import TaskIntelligence
from .text_utils import compact


MARKDOWN_LINK_URL_RE = re.compile(r"\[[^\]]+\]\((https?://[^)\s]+)\)", re.IGNORECASE)


def _extract_first_email(*chunks: str) -> str:
    joined = " ".join(str(chunk or "").strip() for chunk in chunks if str(chunk or "").strip())
    match = EMAIL_RE.search(joined)
    return match.group(1).strip() if match else ""


def _extract_first_url(*chunks: str) -> str:
    joined = " ".join(str(chunk or "").strip() for chunk in chunks if str(chunk or "").strip())
    markdown_match = MARKDOWN_LINK_URL_RE.search(joined)
    if markdown_match:
        clean_markdown_url = _normalize_url_candidate(markdown_match.group(1))
        if clean_markdown_url:
            return clean_markdown_url
    match = URL_RE.search(joined)
    if not match:
        return ""
    return _normalize_url_candidate(match.group(0))


def _normalize_url_candidate(raw_url: str) -> str:
    text = str(raw_url or "").strip()
    if not text:
        return ""

    if "](" in text:
        parts = [part.strip() for part in text.split("](") if part.strip()]
        for part in parts:
            normalized_part = _normalize_url_candidate(part)
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


def derive_task_intelligence(*, message: str, agent_goal: str | None = None) -> TaskIntelligence:
    raw = f"{message} {agent_goal or ''}".strip()
    lexical_signals = infer_intent_signals_from_text(
        message=message,
        agent_goal=agent_goal,
    )
    target_url = str(lexical_signals.get("url") or "").strip() or _extract_first_url(raw)
    host = (urlparse(target_url).hostname or "").strip().lower() if target_url else ""
    delivery_email = str(lexical_signals.get("recipient_email") or "").strip() or _extract_first_email(raw)
    requires_delivery = bool(delivery_email) or bool(lexical_signals.get("wants_send"))
    requires_web_inspection = bool(target_url) or bool(lexical_signals.get("explicit_web_discovery"))
    requested_report = bool(lexical_signals.get("wants_report"))
    heuristic = {
        "objective": compact(message, 280),
        "target_url": target_url,
        "delivery_email": delivery_email,
        "requires_delivery": requires_delivery,
        "requires_web_inspection": requires_web_inspection,
        "requested_report": requested_report,
        "requires_contact_form_submission": bool(lexical_signals.get("wants_contact_form")),
        "wants_docs_output": bool(lexical_signals.get("wants_docs_output")),
        "wants_sheets_output": bool(lexical_signals.get("wants_sheets_output")),
        "wants_highlight_extract": bool(lexical_signals.get("wants_highlight_words")),
        "wants_location_lookup": bool(lexical_signals.get("wants_location_info")),
    }
    intent_tags = classify_intent_tags(
        message=message,
        agent_goal=agent_goal,
        heuristic=heuristic,
    )
    llm_intent = enrich_task_intelligence(
        message=message,
        agent_goal=agent_goal,
        heuristic=heuristic,
    )
    llm_target_url = str(llm_intent.get("target_url") or "").strip().rstrip(".,;)")
    if llm_target_url.startswith(("http://", "https://")):
        target_url = llm_target_url
        host = (urlparse(target_url).hostname or "").strip().lower()
    llm_delivery_email = str(llm_intent.get("delivery_email") or "").strip()
    if "@" in llm_delivery_email and "." in llm_delivery_email:
        delivery_email = llm_delivery_email
    if isinstance(llm_intent.get("requires_delivery"), bool):
        requires_delivery = bool(llm_intent.get("requires_delivery"))
    if isinstance(llm_intent.get("requires_web_inspection"), bool):
        requires_web_inspection = bool(llm_intent.get("requires_web_inspection"))
    if isinstance(llm_intent.get("requested_report"), bool):
        requested_report = bool(llm_intent.get("requested_report"))
    if not delivery_email:
        requires_delivery = False
    objective = str(llm_intent.get("objective") or "").strip() or compact(message, 280)
    preferred_tone = str(llm_intent.get("preferred_tone") or "").strip()[:80]
    preferred_format = str(llm_intent.get("preferred_format") or "").strip()[:80]
    llm_tags = llm_intent.get("intent_tags")
    if isinstance(llm_tags, list):
        normalized = [
            str(item).strip().lower()
            for item in llm_tags
            if str(item).strip()
        ]
        intent_tags = list(dict.fromkeys([*intent_tags, *normalized]))[:8]

    return TaskIntelligence(
        objective=objective,
        target_url=target_url,
        target_host=host,
        delivery_email=delivery_email,
        requires_delivery=requires_delivery,
        requires_web_inspection=requires_web_inspection,
        requested_report=requested_report,
        preferred_tone=preferred_tone,
        preferred_format=preferred_format,
        intent_tags=tuple(intent_tags[:8]),
    )
