from __future__ import annotations

import json
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.policy import get_capability_matrix
from api.services.agent.llm_runtime import (
    call_json_response,
    env_bool,
    sanitize_json_value,
)

MAX_PLANNER_STEPS = 8


def _default_title(tool_id: str) -> str:
    label = str(tool_id).replace(".", " ").replace("_", " ").strip()
    return " ".join(piece.capitalize() for piece in label.split()) or "Planned step"


def _tool_catalog_rows(
    *,
    allowed_tool_ids: list[str],
    preferred_tool_ids: list[str],
) -> list[dict[str, str]]:
    capability_by_tool_id = {
        item.tool_id: item
        for item in get_capability_matrix()
    }
    preferred = set(preferred_tool_ids)
    rows: list[dict[str, str]] = []
    for tool_id in allowed_tool_ids:
        capability = capability_by_tool_id.get(tool_id)
        rows.append(
            {
                "tool_id": tool_id,
                "domain": str(capability.domain if capability else "unknown"),
                "action_class": str(capability.action_class if capability else "read"),
                "description": str(capability.description if capability else tool_id)[:180],
                "preferred": "yes" if tool_id in preferred else "no",
            }
        )
    return rows[:140]


def _request_openai_plan(
    *,
    request: ChatRequest,
    allowed_tool_ids: list[str],
    preferred_tool_ids: list[str],
) -> dict[str, Any] | None:
    tool_catalog = _tool_catalog_rows(
        allowed_tool_ids=allowed_tool_ids,
        preferred_tool_ids=preferred_tool_ids,
    )
    user_payload = {
        "message": str(request.message or "").strip(),
        "agent_goal": str(request.agent_goal or "").strip(),
        "agent_mode": str(request.agent_mode or "").strip(),
        "allowed_tool_ids": allowed_tool_ids,
        "preferred_tool_ids": preferred_tool_ids,
        "tool_catalog": tool_catalog,
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
        "- Prefer preferred_tool_ids when they satisfy the objective.\n"
        "- User does not need to name APIs; infer the right tools from the task intent and tool_catalog.\n"
        "- Prefer business workflow wrappers for non-technical requests when they fully satisfy the task.\n"
        "- Use direct API tools when workflow wrappers are insufficient or unavailable.\n"
        f"- 1 to {MAX_PLANNER_STEPS} steps.\n"
        "- Put practical execution order in the steps list.\n"
        "- Keep params minimal and concrete.\n"
        "- If email delivery is requested, include draft/send style steps where applicable.\n\n"
        "- If the request asks where a company is located/found, include steps that gather location evidence.\n"
        "- If the request asks to submit a website contact form, include `browser.contact_form.send` with URL + message params.\n"
        "- For route/travel planning requests, prefer `business.route_plan` (non-technical wrapper).\n"
        "- For GA4 KPI report requests into Sheets, prefer `business.ga4_kpi_sheet_report`.\n"
        "- For cloud incident digest email requests, prefer `business.cloud_incident_digest_email`.\n"
        "- For invoice create/send requests, prefer `business.invoice_workflow`.\n"
        "- For meeting/calendar scheduling requests, prefer `business.meeting_scheduler`.\n"
        "- For proposal/RFP drafting requests, prefer `business.proposal_workflow`.\n"
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
    preferred_tool_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    if not env_bool("MAIA_AGENT_LLM_PLANNER_ENABLED", default=True):
        return []
    if not allowed_tool_ids:
        return []

    preferred = {
        str(item).strip()
        for item in (preferred_tool_ids or set())
        if str(item).strip() in allowed_tool_ids
    }
    payload = _request_openai_plan(
        request=request,
        allowed_tool_ids=sorted(allowed_tool_ids),
        preferred_tool_ids=sorted(preferred),
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
