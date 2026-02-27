from __future__ import annotations

import json
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.llm_runtime import (
    call_json_response,
    env_bool,
    sanitize_json_value,
)

MAX_PLANNER_STEPS = 8


def _default_title(tool_id: str) -> str:
    label = str(tool_id).replace(".", " ").replace("_", " ").strip()
    return " ".join(piece.capitalize() for piece in label.split()) or "Planned step"


def _request_openai_plan(
    *,
    request: ChatRequest,
    allowed_tool_ids: list[str],
) -> dict[str, Any] | None:
    user_payload = {
        "message": str(request.message or "").strip(),
        "agent_goal": str(request.agent_goal or "").strip(),
        "agent_mode": str(request.agent_mode or "").strip(),
        "allowed_tool_ids": allowed_tool_ids,
    }
    prompt = (
        "Generate an execution plan for the user request.\n"
        "Return ONLY valid JSON in this exact shape:\n"
        "{\n"
        '  "steps": [\n'
        '    {"tool_id": "tool.id", "title": "Human readable title", "params": {}, '
        '"why_this_step":"string", "expected_evidence":["..."]}\n'
        "  ]\n"
        "}\n"
        f"Rules:\n"
        f"- Use only allowed_tool_ids.\n"
        f"- 1 to {MAX_PLANNER_STEPS} steps.\n"
        "- Put practical execution order in the steps list.\n"
        "- Keep params minimal and concrete.\n"
        "- If email delivery is requested, include draft/send style steps where applicable.\n\n"
        "- If the request asks where a company is located/found, include steps that gather location evidence.\n"
        "- If the request asks to submit a website contact form, include `browser.contact_form.send` with URL + message params.\n"
        "- When `agent_mode` is `company_agent`, prefer server-side execution tools and include roadmap logging steps "
        "(`workspace.sheets.track_step`, `workspace.docs.research_notes`) where relevant.\n\n"
        f"Input:\n{json.dumps(user_payload, ensure_ascii=True)}"
    )
    return call_json_response(
        system_prompt=(
            "You are a planning engine for a business AI agent. "
            "Produce concise executable plans and output strict JSON only."
        ),
        user_prompt=prompt,
        temperature=0.0,
        timeout_seconds=18,
        max_tokens=1400,
    )


def plan_with_llm(
    *,
    request: ChatRequest,
    allowed_tool_ids: set[str],
) -> list[dict[str, Any]]:
    if not env_bool("MAIA_AGENT_LLM_PLANNER_ENABLED", default=True):
        return []
    if not allowed_tool_ids:
        return []

    payload = _request_openai_plan(
        request=request,
        allowed_tool_ids=sorted(allowed_tool_ids),
    )
    if not isinstance(payload, dict):
        return []
    rows = payload.get("steps")
    if not isinstance(rows, list):
        return []

    planned_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        tool_id = str(row.get("tool_id") or "").strip()
        if tool_id not in allowed_tool_ids:
            continue
        title = str(row.get("title") or "").strip() or _default_title(tool_id)
        params_raw = row.get("params")
        params = sanitize_json_value(params_raw) if isinstance(params_raw, dict) else {}
        if not isinstance(params, dict):
            params = {}
        why_this_step = " ".join(str(row.get("why_this_step") or "").split()).strip()[:240]
        expected_evidence = [
            " ".join(str(item).split()).strip()[:220]
            for item in (row.get("expected_evidence") if isinstance(row.get("expected_evidence"), list) else [])
            if " ".join(str(item).split()).strip()
        ][:4]
        planned_rows.append(
            {
                "tool_id": tool_id,
                "title": title,
                "params": params,
                "why_this_step": why_this_step,
                "expected_evidence": expected_evidence,
            }
        )
        if len(planned_rows) >= MAX_PLANNER_STEPS:
            break

    return planned_rows
