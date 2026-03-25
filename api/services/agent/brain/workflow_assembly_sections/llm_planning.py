from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .common import _ROLE_CATALOG_PROMPT, logger


def _fallback_plan_from_description(description: str, tenant_id: str = "", ops: Any | None = None) -> dict[str, Any]:
    text = " ".join(str(description or "").split()).strip()
    llm_plan = ops._infer_fallback_plan_via_llm(text, tenant_id=tenant_id)
    if isinstance(llm_plan, dict):
        steps = llm_plan.get("steps")
        edges = llm_plan.get("edges")
        connectors = llm_plan.get("connectors_needed")
        if isinstance(steps, list) and steps:
            normalized_steps: list[dict[str, Any]] = []
            for index, row in enumerate(steps[:6], start=1):
                if isinstance(row, dict):
                    normalized_steps.append({
                        "step_id": str(row.get("step_id") or "").strip() or f"step_{index}",
                        "agent_role": str(row.get("agent_role") or "").strip() or f"agent_{index}",
                        "description": str(row.get("description") or "").strip() or f"Execute agent_{index} responsibilities for this request.",
                        "tools_needed": row.get("tools_needed") if isinstance(row.get("tools_needed"), list) else [],
                    })
            if normalized_steps:
                return {"steps": normalized_steps, "edges": edges if isinstance(edges, list) else [], "connectors_needed": connectors if isinstance(connectors, list) else []}
    return {"steps": [], "edges": [], "connectors_needed": []}


def _degraded_plan_without_llm(description: str, ops: Any | None = None) -> dict[str, Any]:
    text = " ".join(str(description or "").split()).strip()
    if not text:
        return {"steps": [], "edges": [], "connectors_needed": []}
    lowered = text.lower()
    recipient = ops._extract_email(text)
    send_requested = bool(recipient) or any(marker in lowered for marker in ("send", "email", "mail", "deliver"))
    research_requested = any(marker in lowered for marker in ("research", "sources", "evidence", "search", "investigate"))
    write_requested = any(marker in lowered for marker in ("write", "rewrite", "draft", "report", "summary"))
    steps: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    connectors_needed: list[dict[str, str]] = []
    if research_requested:
        steps.append({"step_id": "step_1", "agent_role": "researcher", "description": text, "tools_needed": ["research"]})
    else:
        steps.append({"step_id": "step_1", "agent_role": "operator", "description": text, "tools_needed": []})
    if write_requested and len(steps) == 1:
        steps.append({"step_id": "step_2", "agent_role": "writer", "description": "Synthesize the findings into a clear response for the user.", "tools_needed": ["report"]})
        edges.append({"from_step": "step_1", "to_step": "step_2"})
    if send_requested:
        deliverer_step_id = f"step_{len(steps) + 1}"
        delivery_target = recipient or "the requested recipient"
        steps.append({"step_id": deliverer_step_id, "agent_role": "deliverer", "description": f"Send the final response by email to {delivery_target}.", "tools_needed": ["email"]})
        if len(steps) > 1:
            edges.append({"from_step": steps[-2]["step_id"], "to_step": deliverer_step_id})
        connectors_needed.append({"connector_id": "gmail", "reason": "to deliver the requested email"})
    return {"steps": steps, "edges": edges, "connectors_needed": connectors_needed}


def _infer_fallback_plan_via_llm(description: str, tenant_id: str = "", ops: Any | None = None) -> dict[str, Any]:
    if not description:
        return {}
    prompt = (
        "Build a compact fallback workflow plan for this request.\n"
        "Return valid JSON only with this schema:\n"
        "{\n"
        '  "steps":[{"step_id":"step_1","agent_role":"role","description":"task","tools_needed":["optional.tool"]}],\n'
        '  "edges":[{"from_step":"step_1","to_step":"step_2"}],\n'
        '  "connectors_needed":[{"connector_id":"id","reason":"why"}]\n'
        "}\n"
        "Rules:\n- Do not force generic role templates.\n- Roles must come from request context.\n- Include delivery/sending only if explicitly requested.\n- If the user says not to browse/search, do not include browser/search connectors.\n- Keep it minimal and executable.\n\n"
        f"Request:\n{description[:1200]}"
    )
    parsed, _reason = ops._request_json_from_llm(system_prompt="You are a strict JSON planner. Return JSON only.", user_prompt=prompt, timeout_seconds=ops._fallback_intent_timeout_seconds(), max_tokens=900)
    return parsed if isinstance(parsed, dict) else {}


def _expand_thin_team_via_llm(*, plan: dict[str, Any], description: str, tenant_id: str = "", ops: Any | None = None) -> dict[str, Any]:
    steps = plan.get("steps")
    if not isinstance(steps, list) or len(steps) < 2:
        return plan
    unique_roles = {ops._normalize_role_key(str(step.get("agent_role") or "")) for step in steps if isinstance(step, dict) and str(step.get("agent_role") or "").strip()}
    if len(unique_roles) >= 3:
        return plan
    prompt = (
        "A workflow plan is structurally valid but the team may be too thin for collaborative work.\n"
        "Return valid JSON only in the same schema:\n"
        "{\n"
        '  "steps":[{"step_id":"step_1","agent_role":"role","description":"task","tools_needed":["tool.id"]}],\n'
        '  "edges":[{"from_step":"step_1","to_step":"step_2"}],\n'
        '  "connectors_needed":[{"connector_id":"id","reason":"why"}]\n'
        "}\n"
        "Rules:\n- Preserve the user request exactly.\n- Keep the workflow minimal.\n- Only enrich the team if more role diversity will materially improve evidence quality, review quality, or delivery quality.\n- Prefer adding roles such as supervisor, analyst, reviewer, browser specialist, document reader, email specialist, or delivery specialist when justified.\n- Do not add filler steps.\n- Maximum 6 steps.\n\n"
        f"User request:\n{description[:1200]}\n\nRole catalog:\n{_ROLE_CATALOG_PROMPT}\n\nCurrent plan:\n{json.dumps(plan, ensure_ascii=False)}"
    )
    revised, _reason = ops._request_json_from_llm(system_prompt="You improve workflow team composition. Return JSON only.", user_prompt=prompt, timeout_seconds=min(max(ops._fallback_intent_timeout_seconds() + 2.0, 5.0), 20.0), max_tokens=1200)
    if not isinstance(revised, dict):
        return plan
    revised_plan = ops._sanitize_plan(revised, description=description)
    revised_steps = revised_plan.get("steps")
    if not isinstance(revised_steps, list) or not revised_steps:
        return plan
    revised_roles = {ops._normalize_role_key(str(step.get("agent_role") or "")) for step in revised_steps if isinstance(step, dict) and str(step.get("agent_role") or "").strip()}
    return revised_plan if len(revised_roles) > len(unique_roles) else plan


def _promote_supervisor_presence_via_llm(*, plan: dict[str, Any], description: str, tenant_id: str = "", ops: Any | None = None) -> dict[str, Any]:
    steps = plan.get("steps")
    if not isinstance(steps, list) or len(steps) < 4:
        return plan
    unique_roles = {ops._normalize_role_key(str(step.get("agent_role") or "")) for step in steps if isinstance(step, dict) and str(step.get("agent_role") or "").strip()}
    if any("supervisor" in role or role in {"team lead", "lead"} for role in unique_roles):
        return plan
    prompt = (
        "This workflow is complex enough that it may need an explicit supervisor role in the team.\n"
        "Return valid JSON only in the same schema:\n"
        "{\n"
        '  "steps":[{"step_id":"step_1","agent_role":"role","description":"task","tools_needed":["tool.id"]}],\n'
        '  "edges":[{"from_step":"step_1","to_step":"step_2"}],\n'
        '  "connectors_needed":[{"connector_id":"id","reason":"why"}]\n'
        "}\n"
        "Rules:\n- Keep the workflow minimal and executable.\n- Add a supervisor role only if it materially improves coordination, evidence review, or delivery readiness.\n- If you add a supervisor, give that role a real coordination or review task instead of filler narration.\n- Preserve the existing specialist work.\n- Maximum 6 steps.\n\n"
        f"User request:\n{description[:1200]}\n\nRole catalog:\n{_ROLE_CATALOG_PROMPT}\n\nCurrent plan:\n{json.dumps(plan, ensure_ascii=False)}"
    )
    revised, _reason = ops._request_json_from_llm(system_prompt="You improve workflow team composition for complex collaborative work. Return JSON only.", user_prompt=prompt, timeout_seconds=min(max(ops._fallback_intent_timeout_seconds() + 2.0, 5.0), 20.0), max_tokens=1200)
    if not isinstance(revised, dict):
        return plan
    revised_plan = ops._sanitize_plan(revised, description=description)
    revised_steps = revised_plan.get("steps")
    if not isinstance(revised_steps, list) or not revised_steps:
        return plan
    revised_roles = {ops._normalize_role_key(str(step.get("agent_role") or "")) for step in revised_steps if isinstance(step, dict) and str(step.get("agent_role") or "").strip()}
    return revised_plan if any("supervisor" in role or role in {"team lead", "lead"} for role in revised_roles) else plan


def _request_json_from_llm(*, system_prompt: str, user_prompt: str, timeout_seconds: float, max_tokens: int, ops: Any | None = None) -> tuple[dict[str, Any] | None, str]:
    last_reason = "no runtime attempted"
    try:
        from api.services.agent.llm_runtime import call_json_response, has_openai_credentials
        if has_openai_credentials():
            payload = call_json_response(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.0, timeout_seconds=max(5, int(timeout_seconds)), max_tokens=max_tokens, enable_thinking=True, use_fallback_models=True)
            if isinstance(payload, dict):
                return payload, "openai"
            diagnosis = ops._diagnose_openai_runtime_issue(timeout_seconds=max(5.0, float(timeout_seconds)))
            last_reason = diagnosis or "openai returned empty payload"
        else:
            last_reason = "openai credentials missing"
    except Exception as exc:
        logger.debug("OpenAI JSON planner call failed: %s", exc)
        last_reason = f"openai error: {str(exc)[:160]}"
    try:
        anthropic_key = str(__import__('os').getenv("ANTHROPIC_API_KEY", "")).strip()
        if anthropic_key:
            from api.services.agents.llm_utils import call_llm_json
            payload = call_llm_json(f"{system_prompt}\n\nReturn valid JSON only.\n\n{user_prompt}", temperature=0.0, max_tokens=max(300, min(2000, int(max_tokens))))
            if isinstance(payload, dict):
                return payload, "anthropic"
            last_reason = "anthropic returned non-dict payload"
        elif "missing" in last_reason:
            last_reason = "openai credentials missing; anthropic credentials missing"
    except Exception as exc:
        logger.debug("Anthropic JSON planner call failed: %s", exc)
        last_reason = f"anthropic error: {str(exc)[:160]}"
    return None, last_reason


def _diagnose_openai_runtime_issue(*, timeout_seconds: float) -> str:
    try:
        from api.services.agent.llm_runtime import openai_api_key, _openai_base_url, _openai_chat_model
        key = str(openai_api_key() or "").strip()
        if not key:
            return "openai credentials missing"
        base = str(_openai_base_url() or "").strip().rstrip("/")
        model = str(_openai_chat_model() or "").strip()
        if not base or not model:
            return "openai runtime incomplete"
        request_obj = Request(
            f"{base}/chat/completions",
            method="POST",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            data=json.dumps({"model": model, "temperature": 0.0, "max_tokens": 32, "messages": [{"role": "user", "content": "Return JSON: {\"ok\":true}"}]}).encode("utf-8"),
        )
        with urlopen(request_obj, timeout=max(8, int(timeout_seconds))):
            return ""
    except HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="ignore")
        except Exception:
            body = ""
        marker = ""
        if "insufficient_quota" in body:
            marker = "insufficient_quota"
        elif "invalid_api_key" in body:
            marker = "invalid_api_key"
        elif "rate_limit" in body or "429" in body:
            marker = "rate_limited"
        code = f"http_{int(getattr(exc, 'code', 0) or 0)}"
        return f"openai unavailable: {marker or code}"
    except Exception as exc:
        return f"openai unavailable: {type(exc).__name__}"
