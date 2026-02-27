from __future__ import annotations

import json
from typing import Any

from api.services.agent.llm_runtime import call_json_response, env_bool, sanitize_json_value

ALLOWED_INTENT_TAGS = (
    "web_research",
    "location_lookup",
    "report_generation",
    "docs_write",
    "sheets_update",
    "highlight_extract",
    "email_delivery",
    "contact_form_submission",
)


def _coerce_bool(value: Any) -> bool | None:
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


def _normalize_intent_tags(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    cleaned: list[str] = []
    for item in raw:
        value = str(item or "").strip().lower()
        if not value:
            continue
        if value not in ALLOWED_INTENT_TAGS:
            continue
        if value in cleaned:
            continue
        cleaned.append(value)
    return cleaned[:8]


def enrich_task_intelligence(
    *,
    message: str,
    agent_goal: str | None,
    heuristic: dict[str, Any],
) -> dict[str, Any]:
    if not env_bool("MAIA_AGENT_LLM_INTENT_ENABLED", default=True):
        return {}
    input_payload = {
        "message": str(message or "").strip(),
        "agent_goal": str(agent_goal or "").strip(),
        "heuristic": sanitize_json_value(heuristic),
    }
    prompt = (
        "Extract execution intent from the request and return JSON only.\n"
        "Schema:\n"
        "{\n"
        '  "objective": "string",\n'
        '  "target_url": "string",\n'
        '  "delivery_email": "string",\n'
        '  "requires_delivery": true,\n'
        '  "requires_web_inspection": true,\n'
        '  "requires_contact_form_submission": true,\n'
        '  "requested_report": true,\n'
        '  "preferred_tone": "string",\n'
        '  "preferred_format": "string"\n'
        "}\n"
        "Rules:\n"
        "- Preserve facts from the input; do not invent URLs or emails.\n"
        "- Keep objective concise and actionable.\n"
        "- Include intent_tags only from allowed tags if strongly applicable.\n"
        "- Use empty string when unknown for string fields.\n\n"
        f"Input:\n{json.dumps(input_payload, ensure_ascii=True)}"
    )
    payload = call_json_response(
        system_prompt=(
            "You extract structured task intent for enterprise agent workflows. "
            "Output strict JSON only."
        ),
        user_prompt=prompt,
        temperature=0.0,
        timeout_seconds=14,
        max_tokens=700,
    )
    if not isinstance(payload, dict):
        return {}
    enriched = sanitize_json_value(payload)
    if not isinstance(enriched, dict):
        return {}

    bool_keys = (
        "requires_delivery",
        "requires_web_inspection",
        "requires_contact_form_submission",
        "requested_report",
    )
    for key in bool_keys:
        coerced = _coerce_bool(enriched.get(key))
        if coerced is not None:
            enriched[key] = coerced
        elif key in enriched:
            enriched.pop(key, None)

    for key in ("objective", "target_url", "delivery_email", "preferred_tone", "preferred_format"):
        if key not in enriched:
            continue
        enriched[key] = str(enriched.get(key) or "").strip()[:320]
    tags = _normalize_intent_tags(enriched.get("intent_tags"))
    if tags:
        enriched["intent_tags"] = tags
    elif "intent_tags" in enriched:
        enriched.pop("intent_tags", None)
    return enriched


def classify_intent_tags(
    *,
    message: str,
    agent_goal: str | None,
    heuristic: dict[str, Any],
) -> list[str]:
    heuristic_tags: list[str] = []
    if not isinstance(heuristic, dict):
        heuristic = {}
    if bool(heuristic.get("requires_web_inspection")) or bool(heuristic.get("target_url")):
        heuristic_tags.append("web_research")
    if bool(heuristic.get("requested_report")):
        heuristic_tags.append("report_generation")
    if bool(heuristic.get("requires_delivery")) or bool(heuristic.get("delivery_email")):
        heuristic_tags.append("email_delivery")
    if bool(heuristic.get("requires_contact_form_submission")):
        heuristic_tags.append("contact_form_submission")
    if bool(heuristic.get("wants_docs_output")):
        heuristic_tags.append("docs_write")
    if bool(heuristic.get("wants_sheets_output")):
        heuristic_tags.append("sheets_update")
    if bool(heuristic.get("wants_highlight_extract")):
        heuristic_tags.append("highlight_extract")
    if bool(heuristic.get("wants_location_lookup")):
        heuristic_tags.append("location_lookup")
    heuristic_tags = list(dict.fromkeys(_normalize_intent_tags(heuristic_tags)))

    if not env_bool("MAIA_AGENT_LLM_INTENT_TAGS_ENABLED", default=True):
        return heuristic_tags[:8]
    input_payload = {
        "message": str(message or "").strip(),
        "agent_goal": str(agent_goal or "").strip(),
        "heuristic": sanitize_json_value(heuristic),
        "allowed_tags": list(ALLOWED_INTENT_TAGS),
    }
    prompt = (
        "Classify the user request into intent tags.\n"
        "Return JSON only in this schema:\n"
        '{ "intent_tags": ["tag_1", "tag_2"] }\n'
        "Rules:\n"
        "- Use only allowed_tags.\n"
        "- Include tags only if strongly relevant.\n"
        "- Prefer precision over recall.\n\n"
        f"Input:\n{json.dumps(input_payload, ensure_ascii=True)}"
    )
    payload = call_json_response(
        system_prompt=(
            "You classify enterprise agent requests into routing intent tags. "
            "Output strict JSON only."
        ),
        user_prompt=prompt,
        temperature=0.0,
        timeout_seconds=10,
        max_tokens=180,
    )
    llm_tags = _normalize_intent_tags(payload.get("intent_tags") if isinstance(payload, dict) else [])
    if not llm_tags:
        return heuristic_tags[:8]
    merged = list(dict.fromkeys([*heuristic_tags, *llm_tags]))
    return merged[:8]
