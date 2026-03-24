from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Optional

from api.services.agent.brain.team_role_catalog import display_name_for_role

from .common import _SYSTEM_PROMPT


def assemble_workflow(*, description: str, tenant_id: str = "", on_event: Optional[Callable] = None, ops: Any | None = None) -> dict[str, Any]:
    run_id = f"assembly_{uuid.uuid4().hex[:8]}"
    planner_available, planner_label = ops._planner_runtime_available()
    bootstrap_plan: dict[str, Any] | None = None
    if not planner_available:
        bootstrap_plan = ops._degraded_plan_without_llm(description)
        if not bootstrap_plan.get("steps"):
            error_detail = "LLM planner is not configured. Set OPENAI_API_KEY (or an OpenAI-compatible runtime) to use Brain assemble-and-run."
            ops._emit(on_event, run_id, {"event_type": "assembly_error", "title": "Assembly failed", "detail": error_detail, "data": {"from_agent": "brain", "planner_runtime": planner_label}})
            return {"definition": None, "step_count": 0, "connectors_needed": [], "schedule": None, "run_id": run_id, "error": error_detail}

    fallback_reason = ""
    if planner_available:
        assembly_payload, planner_reason = ops._request_json_from_llm(system_prompt=_SYSTEM_PROMPT, user_prompt=f"Build a workflow for this task:\n\n{description[:1200]}", timeout_seconds=ops._assembly_timeout_seconds(), max_tokens=1200)
    else:
        assembly_payload, planner_reason = bootstrap_plan or {}, f"planner runtime unavailable ({planner_label})"
    plan = assembly_payload if isinstance(assembly_payload, dict) else {"steps": [], "edges": [], "connectors_needed": []}
    if not plan.get("steps"):
        fallback_reason = f"primary planner returned no valid steps ({planner_reason})"
        plan = ops._fallback_plan_from_description(description, tenant_id=tenant_id)
        if not plan.get("steps"):
            degraded_plan = ops._degraded_plan_without_llm(description)
            if degraded_plan.get("steps"):
                plan = degraded_plan
            else:
                error_detail = "The AI took too long to plan the workflow. Try a simpler description." if "timeout" in fallback_reason.lower() else "The AI could not build a valid workflow plan. Please try rephrasing your request."
                lower_reason = fallback_reason.lower()
                if "insufficient_quota" in lower_reason or "quota" in lower_reason:
                    error_detail = "Brain planner quota is exhausted. Update LLM billing/quota, then retry."
                elif "invalid_api_key" in lower_reason or "unauthorized" in lower_reason:
                    error_detail = "Brain planner credentials are invalid. Update OPENAI_API_KEY, then retry."
                ops._emit(on_event, run_id, {"event_type": "assembly_error", "title": "Assembly failed", "detail": error_detail, "data": {"from_agent": "brain", "fallback_reason": fallback_reason}})
                return {"definition": None, "step_count": 0, "connectors_needed": [], "schedule": None, "run_id": run_id, "error": error_detail}

    plan = ops._sanitize_plan(plan, description=description)
    plan = ops._expand_thin_team_via_llm(plan=plan, description=description, tenant_id=tenant_id)
    plan = ops._promote_supervisor_presence_via_llm(plan=plan, description=description, tenant_id=tenant_id)
    if not plan.get("steps"):
        ops._emit(on_event, run_id, {"event_type": "assembly_error", "title": "Assembly failed", "detail": "Planner produced no valid executable worker steps.", "data": {"from_agent": "brain"}})
        return {"definition": None, "step_count": 0, "connectors_needed": [], "schedule": None, "run_id": run_id, "error": "planner_no_valid_worker_steps"}

    steps = plan["steps"]
    edges = plan.get("edges", [])
    connectors = plan.get("connectors_needed", [])
    for i, step in enumerate(steps):
        time.sleep(0.5)
        ops._emit(on_event, run_id, {"event_type": "assembly_step_added", "title": f"Step {i + 1}: {step.get('agent_role', 'agent')}", "detail": step.get("description", ""), "data": {"step_id": step["step_id"], "agent_role": step.get("agent_role", "agent"), "description": step.get("description", ""), "tools_needed": step.get("tools_needed", []), "position": {"x": 100 + i * 300, "y": 200}, "from_agent": "brain"}})
    for edge in edges:
        time.sleep(0.3)
        ops._emit(on_event, run_id, {"event_type": "assembly_edge_added", "title": f"{edge['from_step']} → {edge['to_step']}", "detail": "", "data": {"from_step": edge["from_step"], "to_step": edge["to_step"]}})
    for connector in connectors:
        ops._emit(on_event, run_id, {"event_type": "assembly_connector_needed", "title": f"Connector needed: {connector.get('connector_id', '')}", "detail": connector.get("reason", ""), "data": connector})
    try:
        from api.services.agent.brain.schedule_parser import parse_schedule
        schedule = parse_schedule(description, tenant_id=tenant_id)
        if schedule.get("detected"):
            ops._emit(on_event, run_id, {"event_type": "assembly_schedule_detected", "title": f"Schedule detected: {schedule.get('description', '')}", "detail": f"Cron: {schedule.get('cron', '')}", "data": schedule})
    except Exception:
        schedule = {"detected": False}
    definition = ops._build_definition(description, steps, edges, tenant_id=tenant_id)
    ops._emit(on_event, run_id, {"event_type": "assembly_complete", "title": "Team assembled", "detail": f"{len(steps)} steps, {len(set(s.get('agent_role', '') for s in steps))} agents", "data": {"definition": definition, "step_count": len(steps), "agent_count": len(set(s.get('agent_role', '') for s in steps)), "connectors_needed": connectors, "schedule": schedule if schedule.get("detected") else None, "from_agent": "brain"}})
    return {"definition": definition, "step_count": len(steps), "connectors_needed": connectors, "schedule": schedule if schedule.get("detected") else None, "run_id": run_id}


def _build_definition(description: str, steps: list[dict], edges: list[dict], tenant_id: str = "", ops: Any | None = None) -> dict[str, Any]:
    wf_id = f"wf-{uuid.uuid4().hex[:8]}"
    name = description[:60].strip()
    if len(description) > 60:
        name = name.rsplit(" ", 1)[0] + "..."
    role_to_agent_id = ops._resolve_agent_roles([s.get("agent_role", "agent") for s in steps], tenant_id, request_description=description, role_tasks={str(s.get("agent_role", "agent")): str(s.get("description", "")).strip() for s in steps})
    normalized_role_map = {ops._normalize_role_key(role): agent_id for role, agent_id in role_to_agent_id.items()}
    return {
        "workflow_id": wf_id,
        "name": name,
        "description": description[:300],
        "version": "1.0.0",
        "steps": [
            {
                "step_id": s["step_id"],
                "agent_id": ops._resolve_agent_id_for_step(role_to_agent_id=role_to_agent_id, normalized_role_map=normalized_role_map, step=s),
                "description": s.get("description", ""),
                "step_config": {"role": str(s.get("agent_role", "agent")).strip() or "agent", "name": display_name_for_role(str(s.get("agent_role", "agent"))), "tool_ids": ops._normalize_step_tool_ids(step=s, request_description=description)},
                "output_key": f"output_{s['step_id']}",
                "input_mapping": ops._infer_input_mapping(s, steps, edges, request_description=description),
                "timeout_s": ops._infer_step_timeout_seconds(step=s, request_description=description),
            }
            for s in steps
        ],
        "edges": [{"from_step": e["from_step"], "to_step": e["to_step"]} for e in edges],
    }


def _infer_step_timeout_seconds(*, step: dict[str, Any], request_description: str, ops: Any | None = None) -> int:
    normalized_tools = {" ".join(str(tool_id or "").split()).strip().lower() for tool_id in (step.get("tools_needed") or []) if str(tool_id or "").strip()}
    normalized_tools.update({" ".join(str(tool_id or "").split()).strip().lower() for tool_id in ops._normalize_step_tool_ids(step=step, request_description=request_description) if str(tool_id or "").strip()})
    role = " ".join(str(step.get("agent_role") or "").split()).strip().lower()
    description = " ".join(str(step.get("description") or "").split()).strip().lower()
    request = " ".join(str(request_description or "").split()).strip().lower()
    combined_text = " ".join(part for part in (role, description, request) if part)
    timeout_s = 300
    if normalized_tools.intersection({"marketing.web_research", "web.extract.structured", "browser.playwright.inspect", "browser.playwright.browse_and_capture"}):
        timeout_s = max(timeout_s, 720)
        if any(marker in combined_text for marker in ("authoritative", "peer-reviewed", "evidence citations", "inline citations", "citation-rich", "write an email", "send an email")):
            timeout_s = max(timeout_s, 1200)
    if normalized_tools.intersection({"report.generate"}):
        timeout_s = max(timeout_s, 420)
    if normalized_tools.intersection({"gmail.draft", "gmail.send", "mailer.report_send", "email.draft", "email.send"}):
        timeout_s = max(timeout_s, 420)
    if any(token in role for token in ("research", "browser", "document")) or any(token in description for token in ("research", "browse", "inspect", "extract", "verify")):
        timeout_s = max(timeout_s, 600)
    if "deep research" in request or "comprehensive research" in request:
        timeout_s = max(timeout_s, 900)
    return min(max(300, timeout_s), 1800)
