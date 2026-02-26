from __future__ import annotations

import json
from typing import Any

from api.services.agent.llm_runtime import call_json_response, env_bool, sanitize_json_value


def infer_user_preferences(
    *,
    message: str,
    existing_preferences: dict[str, Any],
) -> dict[str, str]:
    if not env_bool("MAIA_AGENT_LLM_PERSONALIZATION_ENABLED", default=True):
        return {}
    payload = {
        "message": str(message or "").strip(),
        "existing_preferences": sanitize_json_value(existing_preferences or {}),
    }
    prompt = (
        "Infer user communication preferences from the request.\n"
        "Return JSON only in this schema:\n"
        '{ "tone": "string", "format": "string", "verbosity": "low|medium|high", "audience": "string" }\n'
        "Rules:\n"
        "- Use empty string when unknown.\n"
        "- Keep values short and practical.\n"
        "- Do not invent personal data.\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    response = call_json_response(
        system_prompt=(
            "You infer stable communication preferences for enterprise assistant users. "
            "Return strict JSON only."
        ),
        user_prompt=prompt,
        temperature=0.0,
        timeout_seconds=12,
        max_tokens=180,
    )
    if not isinstance(response, dict):
        return {}
    cleaned: dict[str, str] = {}
    for key in ("tone", "format", "verbosity", "audience"):
        value = str(response.get(key) or "").strip()
        if value:
            cleaned[key] = value[:80]
    return cleaned
