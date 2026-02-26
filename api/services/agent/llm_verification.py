from __future__ import annotations

import json
from typing import Any

from api.services.agent.llm_runtime import call_json_response, env_bool, sanitize_json_value
from api.services.agent.models import AgentAction, AgentSource


def build_llm_verification_check(
    *,
    task: dict[str, Any],
    executed_steps: list[dict[str, Any]],
    actions: list[AgentAction],
    sources: list[AgentSource],
) -> dict[str, Any] | None:
    if not env_bool("MAIA_AGENT_LLM_VERIFICATION_ENABLED", default=True):
        return None
    payload = {
        "task": sanitize_json_value(task),
        "executed_steps": sanitize_json_value(executed_steps[-12:]),
        "actions": sanitize_json_value(
            [
                {
                    "tool_id": item.tool_id,
                    "status": item.status,
                    "summary": item.summary,
                }
                for item in actions[-12:]
            ]
        ),
        "source_count": len(sources),
        "source_urls": [str(source.url or "").strip() for source in sources[:8] if str(source.url or "").strip()],
    }
    prompt = (
        "Review run quality and return one verification check JSON.\n"
        "Schema:\n"
        '{ "status": "pass|warn", "detail": "short detail (<=160 chars)" }\n'
        "Rules:\n"
        "- Use pass only when execution appears complete and grounded.\n"
        "- Use warn when important gaps exist.\n"
        "- No markdown.\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    response = call_json_response(
        system_prompt=(
            "You are a strict quality checker for enterprise agent runs. "
            "Return JSON only."
        ),
        user_prompt=prompt,
        temperature=0.0,
        timeout_seconds=12,
        max_tokens=120,
    )
    if not isinstance(response, dict):
        return None
    status = str(response.get("status") or "").strip().lower()
    if status not in {"pass", "warn"}:
        return None
    detail = " ".join(str(response.get("detail") or "").split()).strip()[:160]
    if not detail:
        return None
    return {
        "name": "LLM quality review",
        "status": status,
        "detail": detail,
    }
