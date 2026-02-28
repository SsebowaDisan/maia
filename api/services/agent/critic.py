from __future__ import annotations

import json
from typing import Any

from api.services.agent.llm_runtime import call_text_response, env_bool


def review_final_answer(
    *,
    request_message: str,
    answer_text: str,
    source_urls: list[str],
) -> dict[str, Any]:
    if not env_bool("MAIA_AGENT_CRITIC_ENABLED", default=True):
        return {"needs_human_review": False, "critic_note": ""}

    payload = {
        "request_message": " ".join(str(request_message or "").split()).strip()[:600],
        "answer": str(answer_text or "").strip()[:5000],
        "source_urls": [
            str(item).strip()
            for item in (source_urls or [])
            if str(item).strip()
        ][:12],
    }
    verdict = call_text_response(
        system_prompt=(
            "Review the following answer for factual correctness and safety. "
            "Return 'OK' when no issues are found, or explain concrete issues."
        ),
        user_prompt=f"Input:\n{json.dumps(payload, ensure_ascii=True)}",
        temperature=0.0,
        timeout_seconds=12,
        max_tokens=220,
    )
    clean_verdict = " ".join(str(verdict or "").split()).strip()
    if not clean_verdict:
        return {"needs_human_review": False, "critic_note": ""}

    normalized = clean_verdict.lower().strip(". ")
    ok_values = {"ok", "no issues", "safe", "looks good"}
    if normalized in ok_values or normalized.startswith("ok "):
        return {"needs_human_review": False, "critic_note": ""}
    return {
        "needs_human_review": True,
        "critic_note": clean_verdict[:420],
    }

