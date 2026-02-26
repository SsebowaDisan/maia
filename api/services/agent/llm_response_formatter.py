from __future__ import annotations

import json
from typing import Any

from api.services.agent.llm_runtime import call_text_response, env_bool, sanitize_json_value


def polish_final_response(
    *,
    request_message: str,
    answer_text: str,
    verification_report: dict[str, Any] | None = None,
    preferences: dict[str, Any] | None = None,
) -> str:
    if not env_bool("MAIA_AGENT_LLM_RESPONSE_POLISH_ENABLED", default=True):
        return answer_text
    raw_answer = str(answer_text or "").strip()
    if not raw_answer:
        return answer_text

    payload = {
        "request_message": str(request_message or "").strip(),
        "answer_text": raw_answer,
        "verification_report": sanitize_json_value(verification_report or {}),
        "preferences": sanitize_json_value(preferences or {}),
    }
    prompt = (
        "Polish the final agent response markdown for clarity and readability.\n"
        "Rules:\n"
        "- Preserve all facts and statuses exactly.\n"
        "- Keep section order and meaning.\n"
        "- Improve formatting and sentence flow.\n"
        "- Do not add new claims.\n"
        "- Return markdown text only.\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    polished = call_text_response(
        system_prompt=(
            "You improve readability of enterprise status reports without altering facts."
        ),
        user_prompt=prompt,
        temperature=0.1,
        timeout_seconds=16,
        max_tokens=1800,
    )
    cleaned = str(polished or "").strip()
    if not cleaned:
        return answer_text
    return cleaned
