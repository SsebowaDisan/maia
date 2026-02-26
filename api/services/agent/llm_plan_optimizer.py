from __future__ import annotations

import json
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.llm_runtime import (
    call_json_response,
    call_text_response,
    env_bool,
    sanitize_json_value,
)


def optimize_plan_rows(
    *,
    request: ChatRequest,
    rows: list[dict[str, Any]],
    allowed_tool_ids: set[str],
) -> list[dict[str, Any]]:
    if not env_bool("MAIA_AGENT_LLM_PLAN_CRITIC_ENABLED", default=True):
        return rows
    if not rows:
        return rows
    current_steps = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        tool_id = str(row.get("tool_id") or "").strip()
        if not tool_id:
            continue
        current_steps.append(
            {
                "tool_id": tool_id,
                "title": str(row.get("title") or "").strip(),
                "params": sanitize_json_value(row.get("params") if isinstance(row.get("params"), dict) else {}),
            }
        )
    if not current_steps:
        return rows

    payload = {
        "message": str(request.message or "").strip(),
        "agent_goal": str(request.agent_goal or "").strip(),
        "agent_mode": str(request.agent_mode or "").strip(),
        "allowed_tool_ids": sorted(allowed_tool_ids),
        "current_steps": current_steps,
    }
    prompt = (
        "Review and optimize the execution steps.\n"
        "Return JSON only in this schema:\n"
        "{\n"
        '  "steps": [\n'
        '    {"tool_id": "tool.id", "title": "Step title", "params": {}}\n'
        "  ]\n"
        "}\n"
        "Rules:\n"
        "- Keep practical order and include only allowed_tool_ids.\n"
        "- Add missing critical steps, remove redundant steps.\n"
        "- Fill obvious params (recipient, url, title, summary) when present in request.\n"
        "- If the user asks where a company is located/found, preserve or add location-evidence steps.\n"
        "- In company_agent mode, keep server-side delivery and roadmap logging steps when available.\n"
        "- Do not include more than 10 steps.\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    enriched = call_json_response(
        system_prompt=(
            "You are a strict planning critic for a company agent. "
            "Improve plans safely and output JSON only."
        ),
        user_prompt=prompt,
        temperature=0.0,
        timeout_seconds=16,
        max_tokens=1200,
    )
    if not isinstance(enriched, dict):
        return rows
    candidate_rows = enriched.get("steps")
    if not isinstance(candidate_rows, list):
        return rows
    optimized: list[dict[str, Any]] = []
    for candidate in candidate_rows:
        if not isinstance(candidate, dict):
            continue
        tool_id = str(candidate.get("tool_id") or "").strip()
        if tool_id not in allowed_tool_ids:
            continue
        title = str(candidate.get("title") or "").strip() or tool_id
        params = candidate.get("params")
        optimized.append(
            {
                "tool_id": tool_id,
                "title": title,
                "params": sanitize_json_value(params) if isinstance(params, dict) else {},
            }
        )
        if len(optimized) >= 10:
            break
    return optimized or rows


def rewrite_search_query(
    *,
    query: str,
    request: ChatRequest,
    fallback_url: str = "",
) -> str:
    if not env_bool("MAIA_AGENT_LLM_QUERY_REWRITE_ENABLED", default=True):
        return query
    payload = {
        "query": str(query or "").strip(),
        "message": str(request.message or "").strip(),
        "agent_goal": str(request.agent_goal or "").strip(),
        "fallback_url": str(fallback_url or "").strip(),
    }
    prompt = (
        "Rewrite the search query for higher precision in web research.\n"
        "Return only one line query text. No markdown, no explanation.\n"
        "Prefer company/domain-focused terms and avoid recipient emails.\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    rewritten = call_text_response(
        system_prompt=(
            "You optimize web search queries for business research workflows. "
            "Return only the improved query text."
        ),
        user_prompt=prompt,
        temperature=0.0,
        timeout_seconds=12,
        max_tokens=120,
    )
    clean = " ".join(str(rewritten or "").split()).strip()
    if not clean:
        return query
    return clean[:180]
