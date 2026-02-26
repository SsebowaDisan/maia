from __future__ import annotations

import json
from typing import Any

from api.services.agent.llm_runtime import call_json_response, env_bool, sanitize_json_value


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
        '  "requested_report": true,\n'
        '  "preferred_tone": "string",\n'
        '  "preferred_format": "string"\n'
        "}\n"
        "Rules:\n"
        "- Preserve facts from the input; do not invent URLs or emails.\n"
        "- Keep objective concise and actionable.\n"
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

    bool_keys = ("requires_delivery", "requires_web_inspection", "requested_report")
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
    return enriched
