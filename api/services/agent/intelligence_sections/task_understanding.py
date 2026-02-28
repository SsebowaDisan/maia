from __future__ import annotations

from urllib.parse import urlparse

from api.services.agent.llm_intent import classify_intent_tags, enrich_task_intelligence

from .constants import EMAIL_RE, URL_RE
from .models import TaskIntelligence
from .text_utils import compact


def _extract_first_email(*chunks: str) -> str:
    joined = " ".join(str(chunk or "").strip() for chunk in chunks if str(chunk or "").strip())
    match = EMAIL_RE.search(joined)
    return match.group(1).strip() if match else ""


def _extract_first_url(*chunks: str) -> str:
    joined = " ".join(str(chunk or "").strip() for chunk in chunks if str(chunk or "").strip())
    match = URL_RE.search(joined)
    return match.group(0).strip().rstrip(".,;)") if match else ""


def derive_task_intelligence(*, message: str, agent_goal: str | None = None) -> TaskIntelligence:
    raw = f"{message} {agent_goal or ''}".strip()
    lowered_raw = raw.lower()
    target_url = _extract_first_url(raw)
    host = (urlparse(target_url).hostname or "").strip().lower() if target_url else ""
    delivery_email = _extract_first_email(raw)
    requires_delivery = bool(delivery_email)
    requires_web_inspection = bool(target_url)
    requested_report = any(
        phrase in lowered_raw
        for phrase in (" report", " summary", " writeup", " findings")
    )
    heuristic = {
        "objective": compact(message, 280),
        "target_url": target_url,
        "delivery_email": delivery_email,
        "requires_delivery": requires_delivery,
        "requires_web_inspection": requires_web_inspection,
        "requested_report": requested_report,
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
