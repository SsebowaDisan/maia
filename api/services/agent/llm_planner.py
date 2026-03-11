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


_ANALYTICS_TOOL_IDS = frozenset({
    "analytics.ga4.report",
    "analytics.ga4.full_report",
    "business.ga4_kpi_sheet_report",
})


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


def _compact_intent(intent_signals: dict[str, Any]) -> dict[str, Any]:
    """Extract only the fields the planner needs from the full enriched intent."""
    keys = (
        "objective",
        "target_url",
        "delivery_email",
        "requires_delivery",
        "requires_web_inspection",
        "requires_contact_form_submission",
        "requested_report",
        "wants_docs_output",
        "wants_sheets_output",
        "is_analytics_request",
        "routing_mode",
        "intent_tags",
        "preferred_tone",
        "preferred_format",
    )
    return {k: intent_signals[k] for k in keys if k in intent_signals}


def _build_intent_guard_rules(intent: dict[str, Any]) -> str:
    """Return hard-constraint rules derived from classified intent."""
    rules: list[str] = []
    is_analytics = bool(intent.get("is_analytics_request"))
    if not is_analytics:
        rules.append(
            "- NEVER select analytics or GA4 tools (analytics.ga4.*, business.ga4_kpi_sheet_report) "
            "because is_analytics_request=false in the classified intent."
        )
    else:
        rules.append(
            "- This IS a Google Analytics / GA4 request — include GA4 data tools as needed."
        )
    target_url = str(intent.get("target_url") or "").strip()
    if target_url:
        rules.append(
            f"- A specific URL was identified: {target_url!r}. Use browser.playwright.inspect to inspect it."
        )
    delivery_email = str(intent.get("delivery_email") or "").strip()
    requires_delivery = bool(intent.get("requires_delivery"))
    if delivery_email and requires_delivery:
        rules.append(
            f"- Email delivery was requested to {delivery_email!r}. "
            "Include gmail.draft and/or gmail.send steps with that address."
        )
    tags = intent.get("intent_tags")
    if isinstance(tags, list) and tags:
        rules.append(f"- Classified intent tags: {', '.join(str(t) for t in tags)}. "
                     "Use these to validate your tool choices.")
    return "\n".join(rules)


def _request_openai_plan(
    *,
    request: ChatRequest,
    allowed_tool_ids: list[str],
    preferred_tool_ids: list[str],
    intent_signals: dict[str, Any],
) -> dict[str, Any] | None:
    tool_catalog = _tool_catalog_rows(
        allowed_tool_ids=allowed_tool_ids,
        preferred_tool_ids=preferred_tool_ids,
    )
    compact_intent = _compact_intent(intent_signals)
    intent_guard_rules = _build_intent_guard_rules(compact_intent)
    user_payload = {
        "message": str(request.message or "").strip(),
        "agent_goal": str(request.agent_goal or "").strip(),
        "agent_mode": str(request.agent_mode or "").strip(),
        "classified_intent": compact_intent,
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
        "Hard constraints (enforce strictly — these come from pre-classified intent):\n"
        f"{intent_guard_rules}\n\n"
        "General rules:\n"
        "- Use only allowed_tool_ids.\n"
        "- Prefer preferred_tool_ids ONLY when they directly and specifically match the user's requested action.\n"
        "- Let classified_intent guide tool selection; it is more reliable than keyword matching.\n"
        "- User does not need to name APIs; infer the right tools from the task intent and tool_catalog.\n"
        "- Prefer business workflow wrappers for non-technical requests when they fully satisfy the task.\n"
        "- Use direct API tools when workflow wrappers are insufficient or unavailable.\n"
        f"- 1 to {MAX_PLANNER_STEPS} steps.\n"
        "- Put practical execution order in the steps list.\n"
        "- Keep params minimal and concrete.\n"
        "- If the request asks where a company is located/found, include steps that gather location evidence.\n"
        "- If the request asks to submit a website contact form, include `browser.contact_form.send` with URL + message params.\n"
        "- For route/travel planning requests, prefer `business.route_plan`.\n"
        "- For GA4 KPI report requests into Sheets, prefer `business.ga4_kpi_sheet_report` (only when is_analytics_request=true).\n"
        "- For cloud incident digest email requests, prefer `business.cloud_incident_digest_email`.\n"
        "- For invoice create/send requests, prefer `business.invoice_workflow`.\n"
        "- For meeting/calendar scheduling requests, prefer `business.meeting_scheduler`.\n"
        "- For proposal/RFP drafting requests, prefer `business.proposal_workflow`.\n"
        "- When `agent_mode` is `company_agent`, prefer server-side execution tools.\n"
        "- Include workspace roadmap logging steps only when explicitly requested.\n\n"
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
    intent_signals: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not env_bool("MAIA_AGENT_LLM_PLANNER_ENABLED", default=True):
        return []
    if not allowed_tool_ids:
        return []

    effective_intent = intent_signals if isinstance(intent_signals, dict) else {}
    preferred = {
        str(item).strip()
        for item in (preferred_tool_ids or set())
        if str(item).strip() in allowed_tool_ids
    }
    # When analytics is not the intent, strip GA4 tools from allowed set so the LLM
    # cannot accidentally select them even if they appear in the catalog.
    if not bool(effective_intent.get("is_analytics_request")):
        allowed_tool_ids = allowed_tool_ids - _ANALYTICS_TOOL_IDS

    payload = _request_openai_plan(
        request=request,
        allowed_tool_ids=sorted(allowed_tool_ids),
        preferred_tool_ids=sorted(preferred),
        intent_signals=effective_intent,
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
