from __future__ import annotations

import json
from typing import Any

from api.services.agent.llm_runtime import call_json_response, env_bool


def rewrite_task_for_execution(
    *,
    message: str,
    agent_goal: str | None = None,
    conversation_summary: str = "",
) -> dict[str, Any]:
    """Rewrite user request into a detailed execution brief."""
    clean_message = " ".join(str(message or "").split()).strip()
    clean_goal = " ".join(str(agent_goal or "").split()).strip()
    clean_context = " ".join(str(conversation_summary or "").split()).strip()
    if not clean_message:
        return {"detailed_task": "", "deliverables": [], "constraints": []}
    if not env_bool("MAIA_AGENT_LLM_TASK_REWRITE_ENABLED", default=True):
        fallback_text = clean_message
        if clean_goal:
            fallback_text = f"{fallback_text}\nGoal: {clean_goal}"
        if clean_context:
            fallback_text = f"{fallback_text}\nContext: {clean_context}"
        return {
            "detailed_task": fallback_text[:1000],
            "deliverables": [],
            "constraints": [],
        }

    payload = {
        "message": clean_message,
        "agent_goal": clean_goal,
        "conversation_summary": clean_context,
    }
    prompt = (
        "Rewrite this user request into an execution-ready task brief.\n"
        "Return JSON only:\n"
        '{ "detailed_task": "string", "deliverables": ["..."], "constraints": ["..."] }\n'
        "Rules:\n"
        "- Preserve user intent exactly; do not invent facts.\n"
        "- Keep `detailed_task` concise but specific (max 900 chars).\n"
        "- Include 1-6 deliverables when implied.\n"
        "- Include only explicit constraints from request/context.\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    response = call_json_response(
        system_prompt=(
            "You convert user requests into precise enterprise execution briefs. "
            "Output strict JSON only."
        ),
        user_prompt=prompt,
        temperature=0.0,
        timeout_seconds=12,
        max_tokens=420,
    )
    if not isinstance(response, dict):
        return {
            "detailed_task": clean_message[:1000],
            "deliverables": [],
            "constraints": [],
        }

    detailed_task = " ".join(str(response.get("detailed_task") or "").split()).strip()[:900]
    if not detailed_task:
        detailed_task = clean_message[:900]

    def _clean_list(raw: Any, *, limit: int) -> list[str]:
        if not isinstance(raw, list):
            return []
        items: list[str] = []
        for row in raw:
            text = " ".join(str(row or "").split()).strip()
            if not text or text in items:
                continue
            items.append(text[:220])
            if len(items) >= limit:
                break
        return items

    deliverables = _clean_list(response.get("deliverables"), limit=6)
    constraints = _clean_list(response.get("constraints"), limit=6)
    return {
        "detailed_task": detailed_task,
        "deliverables": deliverables,
        "constraints": constraints,
    }
