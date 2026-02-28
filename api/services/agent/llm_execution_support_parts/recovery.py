from __future__ import annotations

import json
from typing import Any

from api.services.agent.llm_runtime import (
    call_json_response,
    env_bool,
    sanitize_json_value,
)


def suggest_failure_recovery(
    *,
    request_message: str,
    tool_id: str,
    step_title: str,
    error_text: str,
    recent_steps: list[dict[str, Any]],
) -> str:
    if not env_bool("MAIA_AGENT_LLM_RECOVERY_ENABLED", default=True):
        return ""
    payload = {
        "request_message": str(request_message or "").strip(),
        "tool_id": str(tool_id or "").strip(),
        "step_title": str(step_title or "").strip(),
        "error_text": str(error_text or "").strip(),
        "recent_steps": sanitize_json_value(recent_steps),
    }
    prompt = (
        "Given a failed tool execution, provide one concise recovery action.\n"
        "Return JSON only:\n"
        '{ "recovery_hint": "single actionable sentence" }\n'
        "Rules:\n"
        "- Be concrete and safe.\n"
        "- Do not suggest exposing secrets.\n"
        "- Max 140 characters.\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    response = call_json_response(
        system_prompt=(
            "You propose concise remediation actions for workflow failures. "
            "Output strict JSON only."
        ),
        user_prompt=prompt,
        temperature=0.0,
        timeout_seconds=12,
        max_tokens=120,
    )
    if not isinstance(response, dict):
        return ""
    hint = " ".join(str(response.get("recovery_hint") or "").split()).strip()
    return hint[:140]
