"""Brain Workflow Assembly — LLM builds a workflow from a description.

The Brain decomposes a task into steps, assigns agents, identifies
connectors, and emits events one at a time so the frontend can
animate the assembly in the theatre.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from typing import Any, Callable, Optional
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .team_role_catalog import (
    display_name_for_role,
    fallback_system_prompt_for_role,
    format_role_catalog_for_prompt,
    infer_fallback_role,
)

logger = logging.getLogger(__name__)

_ROLE_CATALOG_PROMPT = format_role_catalog_for_prompt()

_SYSTEM_PROMPT = """You are a workflow architect. Given a task description, decompose it into a team of agents that collaborate.

Respond with valid JSON only:
{
  "steps": [
    {
      "step_id": "step_1",
      "agent_role": "freeform role label that best fits the task",
      "description": "what this step does",
      "tools_needed": ["tool.id"] or []
    }
  ],
  "edges": [
    { "from_step": "step_1", "to_step": "step_2" }
  ],
  "connectors_needed": [
    { "connector_id": "gmail", "reason": "to send the email report" }
  ]
}

Rules:
- Define roles from the request context; do not force generic role templates.
- Choose from the role catalog when it helps the task, but only include roles that have real work to do.
- For multi-step work, include supervision or review roles when they add decision value.
- Use browser, document, email, delivery, or reviewer roles when the request explicitly needs those surfaces.
- Preserve the user's scope exactly. Do not inject arbitrary time windows, source types, or academic-only constraints unless the user explicitly asks for them.
- For a general 'research about X' request, prefer a balanced overview using authoritative representative sources rather than a latest-papers sweep.
- Only bias toward recent papers, last-30-days coverage, or narrow benchmark scans when the user explicitly asks for recency, papers, or benchmarks.
- If the user asks for an email deliverable, ensure one step synthesizes cited findings into delivery-ready writing and one step handles delivery.
- Keep it minimal — do not add steps that are not required by the request.
- Do not default to generic role chains (for example researcher→analyst→writer→deliverer) unless the request truly needs them.
- Use one step when one step is enough.
- Connect steps based on dependency logic, not fixed phase assumptions.
- Identify which connectors (gmail, google_analytics, slack, etc.) are needed.
- If the user provides a concrete recipient/target, preserve it in the relevant delivery step description.
- If the request says not to browse/search, do not add browser/search connectors or steps.
- Maximum 6 steps.
- step_id format: step_1, step_2, etc.

Role catalog:
__ROLE_CATALOG__""".replace("__ROLE_CATALOG__", _ROLE_CATALOG_PROMPT)

_RESERVED_ORCHESTRATOR_ROLES = {
    "brain",
    "maia brain",
    "maia_brain",
    "workflow architect",
    "workflow planner",
    "orchestrator",
}


def assemble_workflow(
    *,
    description: str,
    tenant_id: str = "",
    on_event: Optional[Callable] = None,
) -> dict[str, Any]:
    """Build a workflow from a natural language description.

    Emits events for each step/edge so the frontend can animate.
    Returns the complete workflow definition.
    """
    run_id = f"assembly_{uuid.uuid4().hex[:8]}"

    planner_available, planner_label = _planner_runtime_available()
    bootstrap_plan: dict[str, Any] | None = None
    if not planner_available:
        bootstrap_plan = _degraded_plan_without_llm(description)
        if not bootstrap_plan.get("steps"):
            error_detail = (
                "LLM planner is not configured. Set OPENAI_API_KEY (or an OpenAI-compatible runtime) "
                "to use Brain assemble-and-run."
            )
            _emit(on_event, run_id, {
                "event_type": "assembly_error",
                "title": "Assembly failed",
                "detail": error_detail,
                "data": {"from_agent": "brain", "planner_runtime": planner_label},
            })
            return {
                "definition": None,
                "step_count": 0,
                "connectors_needed": [],
                "schedule": None,
                "run_id": run_id,
                "error": error_detail,
            }

    fallback_reason = ""
    if planner_available:
        assembly_payload, planner_reason = _request_json_from_llm(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=f"Build a workflow for this task:\n\n{description[:1200]}",
            timeout_seconds=_assembly_timeout_seconds(),
            max_tokens=1200,
        )
    else:
        assembly_payload, planner_reason = bootstrap_plan or {}, f"planner runtime unavailable ({planner_label})"
    plan = assembly_payload if isinstance(assembly_payload, dict) else {"steps": [], "edges": [], "connectors_needed": []}
    if not plan.get("steps"):
        fallback_reason = f"primary planner returned no valid steps ({planner_reason})"
        plan = _fallback_plan_from_description(description, tenant_id=tenant_id)
        if not plan.get("steps"):
            degraded_plan = _degraded_plan_without_llm(description)
            if degraded_plan.get("steps"):
                plan = degraded_plan
            else:
                error_detail = (
                    "The AI took too long to plan the workflow. Try a simpler description."
                    if "timeout" in fallback_reason.lower()
                    else "The AI could not build a valid workflow plan. Please try rephrasing your request."
                )
                lower_reason = fallback_reason.lower()
                if "insufficient_quota" in lower_reason or "quota" in lower_reason:
                    error_detail = "Brain planner quota is exhausted. Update LLM billing/quota, then retry."
                elif "invalid_api_key" in lower_reason or "unauthorized" in lower_reason:
                    error_detail = "Brain planner credentials are invalid. Update OPENAI_API_KEY, then retry."
                _emit(on_event, run_id, {
                    "event_type": "assembly_error",
                    "title": "Assembly failed",
                    "detail": error_detail,
                    "data": {"from_agent": "brain", "fallback_reason": fallback_reason},
                })
                return {
                    "definition": None,
                    "step_count": 0,
                    "connectors_needed": [],
                    "schedule": None,
                    "run_id": run_id,
                    "error": error_detail,
                }

    plan = _sanitize_plan(plan, description=description)
    plan = _expand_thin_team_via_llm(plan=plan, description=description, tenant_id=tenant_id)
    plan = _promote_supervisor_presence_via_llm(plan=plan, description=description, tenant_id=tenant_id)
    if not plan.get("steps"):
        _emit(on_event, run_id, {
            "event_type": "assembly_error",
            "title": "Assembly failed",
            "detail": "Planner produced no valid executable worker steps.",
            "data": {"from_agent": "brain"},
        })
        return {
            "definition": None,
            "step_count": 0,
            "connectors_needed": [],
            "schedule": None,
            "run_id": run_id,
            "error": "planner_no_valid_worker_steps",
        }

    # Emit steps one at a time with delays
    steps = plan["steps"]
    edges = plan.get("edges", [])
    connectors = plan.get("connectors_needed", [])

    for i, step in enumerate(steps):
        time.sleep(0.5)  # Delay for animation
        _emit(on_event, run_id, {
            "event_type": "assembly_step_added",
            "title": f"Step {i + 1}: {step.get('agent_role', 'agent')}",
            "detail": step.get("description", ""),
            "data": {
                "step_id": step["step_id"],
                "agent_role": step.get("agent_role", "agent"),
                "description": step.get("description", ""),
                "tools_needed": step.get("tools_needed", []),
                "position": {"x": 100 + i * 300, "y": 200},
                "from_agent": "brain",
            },
        })

    # Emit edges
    for edge in edges:
        time.sleep(0.3)
        _emit(on_event, run_id, {
            "event_type": "assembly_edge_added",
            "title": f"{edge['from_step']} → {edge['to_step']}",
            "detail": "",
            "data": {"from_step": edge["from_step"], "to_step": edge["to_step"]},
        })

    # Emit connector needs
    for connector in connectors:
        _emit(on_event, run_id, {
            "event_type": "assembly_connector_needed",
            "title": f"Connector needed: {connector.get('connector_id', '')}",
            "detail": connector.get("reason", ""),
            "data": connector,
        })

    # Check for schedule in the description
    try:
        from .schedule_parser import parse_schedule
        schedule = parse_schedule(description, tenant_id=tenant_id)
        if schedule.get("detected"):
            _emit(on_event, run_id, {
                "event_type": "assembly_schedule_detected",
                "title": f"Schedule detected: {schedule.get('description', '')}",
                "detail": f"Cron: {schedule.get('cron', '')}",
                "data": schedule,
            })
    except Exception:
        schedule = {"detected": False}

    # Build the final workflow definition
    definition = _build_definition(description, steps, edges, tenant_id=tenant_id)

    _emit(on_event, run_id, {
        "event_type": "assembly_complete",
        "title": "Team assembled",
        "detail": f"{len(steps)} steps, {len(set(s.get('agent_role', '') for s in steps))} agents",
        "data": {
            "definition": definition,
            "step_count": len(steps),
            "agent_count": len(set(s.get("agent_role", "") for s in steps)),
            "connectors_needed": connectors,
            "schedule": schedule if schedule.get("detected") else None,
            "from_agent": "brain",
        },
    })

    return {
        "definition": definition,
        "step_count": len(steps),
        "connectors_needed": connectors,
        "schedule": schedule if schedule.get("detected") else None,
        "run_id": run_id,
    }


def _build_definition(
    description: str, steps: list[dict], edges: list[dict], tenant_id: str = "",
) -> dict[str, Any]:
    """Build a WorkflowDefinitionSchema-compatible dict with resolved agent IDs."""
    wf_id = f"wf-{uuid.uuid4().hex[:8]}"
    name = description[:60].strip()
    if len(description) > 60:
        name = name.rsplit(" ", 1)[0] + "..."

    # Resolve role names to real tenant agent IDs
    role_to_agent_id = _resolve_agent_roles(
        [s.get("agent_role", "agent") for s in steps],
        tenant_id,
        request_description=description,
        role_tasks={
            str(s.get("agent_role", "agent")): str(s.get("description", "")).strip()
            for s in steps
        },
    )
    normalized_role_map = {
        _normalize_role_key(role): agent_id
        for role, agent_id in role_to_agent_id.items()
    }

    return {
        "workflow_id": wf_id,
        "name": name,
        "description": description[:300],
        "version": "1.0.0",
        "steps": [
            {
                "step_id": s["step_id"],
                "agent_id": _resolve_agent_id_for_step(
                    role_to_agent_id=role_to_agent_id,
                    normalized_role_map=normalized_role_map,
                    step=s,
                ),
                "description": s.get("description", ""),
                "step_config": {
                    "role": str(s.get("agent_role", "agent")).strip() or "agent",
                    "name": display_name_for_role(str(s.get("agent_role", "agent"))),
                    "tool_ids": _normalize_step_tool_ids(
                        step=s,
                        request_description=description,
                    ),
                },
                "output_key": f"output_{s['step_id']}",
                "input_mapping": _infer_input_mapping(
                    s,
                    steps,
                    edges,
                    request_description=description,
                ),
                "timeout_s": _infer_step_timeout_seconds(
                    step=s,
                    request_description=description,
                ),
            }
            for s in steps
        ],
        "edges": [
            {"from_step": e["from_step"], "to_step": e["to_step"]}
            for e in edges
        ],
    }


def _infer_step_timeout_seconds(*, step: dict[str, Any], request_description: str) -> int:
    """Give heavy research/delivery steps realistic runtime budgets.

    The schema already supports per-step timeouts. Assembly should set them
    explicitly so deep web research and cited writing do not inherit the
    generic 300s default.
    """
    normalized_tools = {
        " ".join(str(tool_id or "").split()).strip().lower()
        for tool_id in (step.get("tools_needed") or [])
        if str(tool_id or "").strip()
    }
    normalized_tools.update(
        {
            " ".join(str(tool_id or "").split()).strip().lower()
            for tool_id in _normalize_step_tool_ids(
                step=step,
                request_description=request_description,
            )
            if str(tool_id or "").strip()
        }
    )
    role = " ".join(str(step.get("agent_role") or "").split()).strip().lower()
    description = " ".join(str(step.get("description") or "").split()).strip().lower()
    request = " ".join(str(request_description or "").split()).strip().lower()
    combined_text = " ".join(part for part in (role, description, request) if part)

    timeout_s = 300
    if normalized_tools.intersection(
        {
            "marketing.web_research",
            "web.extract.structured",
            "browser.playwright.inspect",
            "browser.playwright.browse_and_capture",
        }
    ):
        timeout_s = max(timeout_s, 720)
        if any(
            marker in combined_text
            for marker in (
                "authoritative",
                "peer-reviewed",
                "evidence citations",
                "inline citations",
                "citation-rich",
                "write an email",
                "send an email",
            )
        ):
            timeout_s = max(timeout_s, 1200)
    if normalized_tools.intersection({"report.generate"}):
        timeout_s = max(timeout_s, 420)
    if normalized_tools.intersection({"gmail.draft", "gmail.send", "mailer.report_send", "email.draft", "email.send"}):
        timeout_s = max(timeout_s, 420)
    if any(token in role for token in ("research", "browser", "document")) or any(
        token in description for token in ("research", "browse", "inspect", "extract", "verify")
    ):
        timeout_s = max(timeout_s, 600)
    if "deep research" in request or "comprehensive research" in request:
        timeout_s = max(timeout_s, 900)
    return min(max(300, timeout_s), 1800)


def _resolve_agent_roles(
    roles: list[str],
    tenant_id: str,
    request_description: str = "",
    role_tasks: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    """Map role names to real tenant agent IDs. Creates agents if they don't exist."""
    if not tenant_id:
        return {r: r for r in roles}
    mapping: dict[str, str] = {}
    role_tasks = role_tasks or {}
    llm_prompts = _generate_role_prompts_via_llm(
        roles=sorted({str(r or "").strip() for r in roles if str(r or "").strip()}),
        request_description=request_description,
        role_tasks=role_tasks,
        tenant_id=tenant_id,
    )
    try:
        from api.services.agents.definition_store import get_agent, list_agents, create_agent
        existing = list_agents(tenant_id)
        existing_by_name = {
            str(a.name or "").strip().lower(): str(a.agent_id or a.id)
            for a in existing
        }
        existing_by_id = {
            str(a.agent_id or a.id).strip().lower(): str(a.agent_id or a.id)
            for a in existing
        }
        for role in set(roles):
            role_lower = role.strip().lower()
            role_slug = _to_agent_slug(role_lower)
            # Try exact match by ID
            if role_lower in existing_by_id:
                chosen = existing_by_id[role_lower]
                if not _is_brain_agent_identifier(chosen):
                    mapping[role] = chosen
                    continue
            if role_slug in existing_by_id:
                chosen = existing_by_id[role_slug]
                if not _is_brain_agent_identifier(chosen):
                    mapping[role] = chosen
                    continue
            # Try match by name
            if role_lower in existing_by_name:
                chosen = existing_by_name[role_lower]
                if not _is_brain_agent_identifier(chosen):
                    mapping[role] = chosen
                    continue
            # Try fuzzy match
            matched = False
            for name, aid in existing_by_name.items():
                if _is_brain_agent_identifier(name) or _is_brain_agent_identifier(aid):
                    continue
                if role_lower in name or name in role_lower:
                    mapping[role] = aid
                    matched = True
                    break
            if matched:
                continue
            # Create a new agent with this role, using LLM-authored prompt context.
            try:
                from api.schemas.agent_definition.schema import AgentDefinitionSchema
                task_focus = str(role_tasks.get(role, "")).strip()
                agent_prompt = (
                    str(llm_prompts.get(role, "")).strip()
                    or str(llm_prompts.get(role_lower, "")).strip()
                    or (
                        f"You are responsible for the role '{role}'. "
                        f"Execute only your assigned step with evidence and clear handoff."
                    )
                )
                if task_focus:
                    agent_prompt = f"{agent_prompt}\n\nCurrent step focus: {task_focus[:500]}"
                chosen_id = role_slug
                suffix = 1
                while chosen_id in existing_by_id:
                    suffix += 1
                    candidate = f"{role_slug}-{suffix}"
                    chosen_id = candidate[:64].rstrip("-_")
                schema = AgentDefinitionSchema(
                    id=chosen_id,
                    name=role.title(),
                    system_prompt=agent_prompt,
                )
                new_agent = create_agent(tenant_id, tenant_id, schema)
                created_id = str(getattr(new_agent, "agent_id", None) or getattr(new_agent, "id", chosen_id))
                existing_by_id[created_id.lower()] = created_id
                existing_by_name[role_lower] = created_id
                mapping[role] = created_id
            except Exception:
                # Never return a non-existent role label as agent_id.
                fallback = existing_by_name.get(role_lower) or existing_by_id.get(role_slug)
                if not fallback and existing_by_id:
                    fallback = next(
                        (candidate for candidate in existing_by_id.values() if not _is_brain_agent_identifier(candidate)),
                        None,
                    )
                mapping[role] = str(fallback or "agent")
    except Exception:
        mapping = {r: r for r in roles}
    return mapping


def _resolve_agent_id_for_step(
    *,
    role_to_agent_id: dict[str, str],
    normalized_role_map: dict[str, str],
    step: dict[str, Any],
) -> str:
    raw_role = str(step.get("agent_role", "agent") or "agent")
    role = raw_role.strip() or "agent"
    return (
        role_to_agent_id.get(raw_role)
        or role_to_agent_id.get(role)
        or normalized_role_map.get(_normalize_role_key(role))
        or role
    )


def _normalize_role_key(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _extract_email(text: str) -> str:
    match = re.search(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", str(text or ""))
    return str(match.group(1)).strip().rstrip(".,;:!?") if match else ""


def _derive_request_focus(request_description: str) -> str:
    text = " ".join(str(request_description or "").split()).strip()
    if not text:
        return "the requested topic"

    cleaned = re.sub(
        r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(?:and|then)?\s*(?:write|draft|compose|send|deliver|email|mail)\b[\s\S]*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"^\s*(?:please\s+)?(?:make|do|perform|conduct|carry out|start|run)\s+(?:the\s+)?research\s+(?:about|on)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"^\s*(?:research|analyse|analyze|investigate|study)\s+(?:about|on)?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = cleaned.strip(" .,:;!-")
    return cleaned or text.strip(" .,:;!-") or "the requested topic"


def _derive_primary_search_query(
    *,
    request_description: str,
    step: dict[str, Any],
) -> str:
    text = " ".join(str(request_description or "").split()).strip()
    if not text:
        return str(step.get("description") or "").strip() or "the requested topic"

    target_url_match = re.search(r"https?://[^\s]+", text, flags=re.IGNORECASE)
    if target_url_match:
        return target_url_match.group(0).strip().rstrip(".,;:!?")

    focus = _derive_request_focus(text)
    focus = re.sub(
        r"\b(?:using|with)\s+multiple\s+authoritative\s+sources\b",
        "",
        focus,
        flags=re.IGNORECASE,
    )
    focus = re.sub(
        r"\b(?:with|including)\s+inline\s+citations\b",
        "",
        focus,
        flags=re.IGNORECASE,
    )
    focus = " ".join(focus.split()).strip(" .,:;!-")
    return focus or _derive_request_focus(text)


def _step_role_family(step: dict[str, Any]) -> str:
    role = _normalize_role_key(str(step.get("agent_role") or ""))
    description = " ".join(str(step.get("description") or "").split()).strip().lower()
    text = f"{role} {description}".strip()

    def _matches(*terms: str) -> bool:
        return any(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) for term in terms)

    def _role_matches(*terms: str) -> bool:
        return any(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", role) for term in terms)

    if _role_matches("deliver", "deliverer", "delivery", "mailer", "sender", "dispatch"):
        return "delivery"
    if _role_matches("email specialist", "writer", "author", "editor", "content", "drafter"):
        return "writer"
    if _role_matches("reviewer", "fact checker", "fact-check", "qa"):
        return "reviewer"
    if _role_matches("analyst", "analysis"):
        return "analysis"
    if _role_matches("browser", "research", "document", "investigate"):
        return "research"

    if _matches("deliver", "delivery", "mailer", "sender", "dispatch"):
        return "delivery"
    if _matches("email specialist", "writer", "author", "editor", "content", "draft", "rewrite", "compose"):
        return "writer"
    if _matches("reviewer", "fact checker", "fact-check", "verify", "qa"):
        return "reviewer"
    if _matches("analyst", "analysis", "compare", "metric", "trend", "evaluate"):
        return "analysis"
    if _matches("browser", "research", "document", "evidence", "search", "source", "investigate"):
        return "research"
    return "general"


def _request_needs_research_email_flow(request_description: str) -> bool:
    request = " ".join(str(request_description or "").split()).strip().lower()
    if not request:
        return False
    has_email_target = bool(_extract_email(request_description))
    wants_delivery = has_email_target or any(
        marker in request for marker in ("send", "email", "mail", "deliver")
    )
    wants_research = any(
        marker in request
        for marker in ("research", "investigate", "look up", "search", "sources", "evidence", "findings")
    )
    return wants_delivery and wants_research


def _research_step_description(focus: str) -> str:
    return (
        f"Research {focus} using multiple authoritative sources and extract source-backed findings with inline citations. "
        "Return a concise executive research brief with short headings, a premium polished tone, and a final "
        "Evidence Citations section. Synthesize the strongest converging evidence across representative sources "
        "instead of relying on a single article whenever broader support is available. Prefer an executive brief that "
        "lands around 1000-1500 characters when that range can preserve the strongest evidence clearly; exceed it only "
        "when compressing further would materially weaken clarity or citation integrity. Keep the output directly reusable "
        "in email drafting, typically fitting on a single screen when the topic is broad. Every inline citation marker "
        "[n] must resolve to a numbered row in the final Evidence Citations section. "
        "Do not draft or send the email."
    )


def _review_step_description(focus: str) -> str:
    return (
        f"Review the research findings about {focus}, verify the strongest supported claims, and challenge any weak "
        "or contradictory evidence before writing. Preserve inline citations and the final Evidence Citations section. "
        "Do not draft or send the email."
    )


def _writer_step_description(focus: str, recipient: str) -> str:
    return (
        f"Compose a polished, citation-rich email draft about {focus}"
        + (f" for {recipient}" if recipient else "")
        + ". Write the full send-ready draft with a clear Subject line, a professional greeting, a refined premium body, "
          "a compact executive summary, scannable key findings with inline citations, a final Evidence Citations section, "
          "and a professional sign-off. Use the cited research artifact from the previous step as the source of truth. "
          "Do not introduce new sources or renumber citations unless you are explicitly removing unsupported claims and "
          "keeping the remaining numbering internally consistent. Keep inline citations intact and preserve source "
          "numbering consistently. "
          "This stage drafts only; do not dispatch the email."
    )


def _delivery_step_description(recipient: str) -> str:
    if recipient:
        return f"Send the cited email draft produced by the previous step to {recipient} without changing its substance."
    return "Send the cited email draft produced by the previous step without changing its substance."


def _rebalance_research_email_steps(
    *,
    steps: list[dict[str, Any]],
    request_description: str,
) -> list[dict[str, Any]]:
    if len(steps) < 2 or not _request_needs_research_email_flow(request_description):
        return steps

    focus = _derive_request_focus(request_description)
    recipient = _extract_email(request_description)
    updated_steps = [dict(step) for step in steps]
    families = [_step_role_family(step) for step in updated_steps]
    delivery_indexes = [index for index, family in enumerate(families) if family == "delivery"]
    if not delivery_indexes:
        return updated_steps

    delivery_index = delivery_indexes[-1]
    updated_steps[delivery_index]["description"] = _delivery_step_description(recipient)

    non_delivery_indexes = [index for index in range(delivery_index) if families[index] != "delivery"]
    if not non_delivery_indexes:
        return updated_steps

    research_index = non_delivery_indexes[0]
    updated_steps[research_index]["description"] = _research_step_description(focus)

    if len(non_delivery_indexes) == 1:
        return updated_steps

    writer_index = non_delivery_indexes[-1]
    if writer_index != research_index:
        updated_steps[writer_index]["description"] = _writer_step_description(focus, recipient)

    for index in non_delivery_indexes[1:-1]:
        updated_steps[index]["description"] = _review_step_description(focus)

    return updated_steps


def _rescope_step_descriptions(
    *,
    steps: list[dict[str, Any]],
    request_description: str,
) -> list[dict[str, Any]]:
    if len(steps) < 2:
        return steps

    focus = _derive_request_focus(request_description)
    recipient = _extract_email(request_description)
    has_delivery_step = any(_step_role_family(step) == "delivery" for step in steps)
    rescoped: list[dict[str, Any]] = []

    for index, step in enumerate(steps, start=1):
        updated = dict(step)
        family = _step_role_family(step)
        if family == "research":
            updated["description"] = _research_step_description(focus)
        elif family in {"analysis", "reviewer"}:
            updated["description"] = _review_step_description(focus)
        elif family == "writer":
            updated["description"] = _writer_step_description(focus, recipient)
        elif family == "delivery":
            updated["description"] = _delivery_step_description(recipient)
        elif index == 1 and has_delivery_step:
            updated["description"] = _research_step_description(focus)
        rescoped.append(updated)
    return _rebalance_research_email_steps(
        steps=rescoped,
        request_description=request_description,
    )


def _to_agent_slug(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-_")
    if not text:
        text = "agent"
    if len(text) < 3:
        text = f"{text}-agent"
    text = text[:64]
    text = text.strip("-_")
    if not text:
        text = "agent"
    if not text[0].isalnum():
        text = f"a{text}"
    if not text[-1].isalnum():
        text = f"{text}a"
    return text[:64]


def _infer_input_mapping(
    step: dict,
    all_steps: list[dict],
    edges: list[dict],
    *,
    request_description: str = "",
) -> dict[str, str]:
    """Infer input mapping from predecessor steps."""
    predecessors = [e["from_step"] for e in edges if e["to_step"] == step["step_id"]]
    mapping: dict[str, str] = {}
    if not predecessors:
        step_family = _step_role_family(step)
        if step_family in {"research", "analysis", "reviewer"}:
            primary_query = _derive_primary_search_query(
                request_description=request_description,
                step=step,
            )
            mapping["query"] = f"literal:{primary_query}"
            mapping["topic"] = f"literal:{primary_query}"
        else:
            mapping["query"] = f"literal:{step.get('description', '')}"
    else:
        for pred_id in predecessors:
            pred = next((s for s in all_steps if s["step_id"] == pred_id), None)
            if pred:
                key = pred.get("agent_role", pred_id)
                mapping[key] = f"output_{pred_id}"
    recipient = _extract_email(step.get("description", ""))
    if recipient:
        mapping.setdefault("to", f"literal:{recipient}")
        mapping.setdefault("recipient", f"literal:{recipient}")
    return mapping


def _parse_plan(raw: str) -> dict[str, Any]:
    """Parse the LLM's workflow plan."""
    text = raw.strip()
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start) if "```" in text[start:] else len(text)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start) if "```" in text[start:] else len(text)
        text = text[start:end].strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "steps" in parsed:
            return parsed
    except json.JSONDecodeError:
        pass

    # Try to find JSON
    for i in range(len(text)):
        if text[i] == "{":
            for j in range(len(text) - 1, i, -1):
                if text[j] == "}":
                    try:
                        parsed = json.loads(text[i:j + 1])
                        if isinstance(parsed, dict) and "steps" in parsed:
                            return parsed
                    except json.JSONDecodeError:
                        continue
    return {"steps": [], "edges": [], "connectors_needed": []}


def _fallback_plan_from_description(description: str, tenant_id: str = "") -> dict[str, Any]:
    """Return an LLM-guided fallback plan when the primary assembly call fails.

    This avoids fixed role/phase templates and lets the model derive
    context-specific roles and sequencing from the request itself.
    """
    text = " ".join(str(description or "").split()).strip()
    llm_plan = _infer_fallback_plan_via_llm(text, tenant_id=tenant_id)
    if isinstance(llm_plan, dict):
        steps = llm_plan.get("steps")
        edges = llm_plan.get("edges")
        connectors = llm_plan.get("connectors_needed")
        if isinstance(steps, list) and steps:
            normalized_steps: list[dict[str, Any]] = []
            for index, row in enumerate(steps[:6], start=1):
                if not isinstance(row, dict):
                    continue
                step_id = str(row.get("step_id") or "").strip() or f"step_{index}"
                agent_role = str(row.get("agent_role") or "").strip() or f"agent_{index}"
                description_value = str(row.get("description") or "").strip() or f"Execute {agent_role} responsibilities for this request."
                tools_needed = row.get("tools_needed")
                normalized_steps.append(
                    {
                        "step_id": step_id,
                        "agent_role": agent_role,
                        "description": description_value,
                        "tools_needed": tools_needed if isinstance(tools_needed, list) else [],
                    }
                )
            if normalized_steps:
                normalized_edges = edges if isinstance(edges, list) else []
                normalized_connectors = connectors if isinstance(connectors, list) else []
                return {
                    "steps": normalized_steps,
                    "edges": normalized_edges,
                    "connectors_needed": normalized_connectors,
                }

    return {"steps": [], "edges": [], "connectors_needed": []}


def _degraded_plan_without_llm(description: str) -> dict[str, Any]:
    """Build a minimal executable plan without planner LLM calls."""
    text = " ".join(str(description or "").split()).strip()
    if not text:
        return {"steps": [], "edges": [], "connectors_needed": []}

    lowered = text.lower()
    recipient = _extract_email(text)
    send_requested = bool(recipient) or any(
        marker in lowered for marker in ("send", "email", "mail", "deliver")
    )
    research_requested = any(
        marker in lowered
        for marker in ("research", "sources", "evidence", "search", "investigate")
    )
    write_requested = any(
        marker in lowered
        for marker in ("write", "rewrite", "draft", "report", "summary")
    )

    steps: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    connectors_needed: list[dict[str, str]] = []

    if research_requested:
        steps.append(
            {
                "step_id": "step_1",
                "agent_role": "researcher",
                "description": text,
                "tools_needed": ["research"],
            }
        )
    else:
        steps.append(
            {
                "step_id": "step_1",
                "agent_role": "operator",
                "description": text,
                "tools_needed": [],
            }
        )

    if write_requested and len(steps) == 1:
        steps.append(
            {
                "step_id": "step_2",
                "agent_role": "writer",
                "description": "Synthesize the findings into a clear response for the user.",
                "tools_needed": ["report"],
            }
        )
        edges.append({"from_step": "step_1", "to_step": "step_2"})

    if send_requested:
        deliverer_step_id = f"step_{len(steps) + 1}"
        delivery_target = recipient or "the requested recipient"
        steps.append(
            {
                "step_id": deliverer_step_id,
                "agent_role": "deliverer",
                "description": f"Send the final response by email to {delivery_target}.",
                "tools_needed": ["email"],
            }
        )
        if len(steps) > 1:
            previous_step_id = steps[-2]["step_id"]
            edges.append({"from_step": previous_step_id, "to_step": deliverer_step_id})
        connectors_needed.append(
            {
                "connector_id": "gmail",
                "reason": "to deliver the requested email",
            }
        )

    return {
        "steps": steps,
        "edges": edges,
        "connectors_needed": connectors_needed,
    }


def _infer_fallback_plan_via_llm(description: str, tenant_id: str = "") -> dict[str, Any]:
    """Infer a compact fallback workflow plan via LLM without fixed role templates."""
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
        "Rules:\n"
        "- Do not force generic role templates.\n"
        "- Roles must come from request context.\n"
        "- Include delivery/sending only if explicitly requested.\n"
        "- If the user says not to browse/search, do not include browser/search connectors.\n"
        "- Keep it minimal and executable.\n\n"
        f"Request:\n{description[:1200]}"
    )

    parsed, _reason = _request_json_from_llm(
        system_prompt="You are a strict JSON planner. Return JSON only.",
        user_prompt=prompt,
        timeout_seconds=_fallback_intent_timeout_seconds(),
        max_tokens=900,
    )
    return parsed if isinstance(parsed, dict) else {}


def _generate_role_prompts_via_llm(
    *,
    roles: list[str],
    request_description: str,
    role_tasks: dict[str, str],
    tenant_id: str,
) -> dict[str, str]:
    """Generate system prompts for missing role agents using LLM context, not templates."""
    if not roles or not tenant_id:
        return {}
    role_payload = [
        {
            "role": role,
            "task_focus": str(role_tasks.get(role, "")).strip()[:500],
        }
        for role in roles
    ]
    prompt = (
        "Create concise system prompts for workflow agents.\n"
        "Return valid JSON only in this schema:\n"
        '{ "roles": [ { "role": "name", "system_prompt": "prompt text" } ] }\n'
        "Rules:\n"
        "- Do not use generic templates.\n"
        "- Tailor each prompt to the user request and role task focus.\n"
        "- Include collaboration behavior: ask teammates for missing data, challenge weak claims with evidence requests, and provide clean handoffs.\n"
        "- Keep each role distinct. Supervisors decide and assign, researchers gather evidence, analysts interpret, reviewers challenge, writers polish, and delivery roles send.\n"
        "- Keep each system_prompt under 120 words.\n\n"
        f"User request:\n{request_description[:1200]}\n\n"
        f"Role catalog:\n{_ROLE_CATALOG_PROMPT}\n\n"
        f"Roles:\n{json.dumps(role_payload, ensure_ascii=False)}"
    )

    parsed, _reason = _request_json_from_llm(
        system_prompt="You write strict JSON only. Return no markdown.",
        user_prompt=prompt,
        timeout_seconds=min(max(_fallback_intent_timeout_seconds() + 2.0, 5.0), 20.0),
        max_tokens=900,
    )
    if not isinstance(parsed, dict):
        return {}
    rows = parsed.get("roles")
    if not isinstance(rows, list):
        return {}
    prompts: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        role = str(row.get("role") or "").strip()
        system_prompt = str(row.get("system_prompt") or "").strip()
        if role and system_prompt:
            prompts[role] = system_prompt
            prompts[role.lower()] = system_prompt
    for role in roles:
        normalized = str(role or "").strip()
        if not normalized:
            continue
        fallback_prompt = fallback_system_prompt_for_role(
            normalized,
            request_description=request_description,
            task_focus=str(role_tasks.get(normalized, "")).strip(),
        )
        prompts.setdefault(normalized, fallback_prompt)
        prompts.setdefault(normalized.lower(), prompts[normalized])
    return prompts


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start) if "```" in text[start:] else len(text)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start) if "```" in text[start:] else len(text)
        text = text[start:end].strip()

    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass

    for i in range(len(text)):
        if text[i] != "{":
            continue
        for j in range(len(text) - 1, i, -1):
            if text[j] != "}":
                continue
            try:
                parsed = json.loads(text[i : j + 1])
                return parsed if isinstance(parsed, dict) else None
            except Exception:
                continue
    return None


def _normalize_step_tool_ids(*, step: dict[str, Any], request_description: str) -> list[str]:
    """Normalize planner tool hints into concrete tool IDs for step-level allowlists."""
    tool_hints = step.get("tools_needed")
    hints = tool_hints if isinstance(tool_hints, list) else []
    normalized: list[str] = []

    role_text = " ".join(str(step.get("agent_role") or "").split()).strip().lower()
    description_text = " ".join(str(step.get("description") or "").split()).strip().lower()
    text = " ".join([role_text, description_text]).strip()
    full_request = str(request_description or "").lower()
    hint_tokens = {str(raw or "").strip().lower() for raw in hints if str(raw or "").strip()}
    has_explicit_url = bool(re.search(r"https?://", text) or re.search(r"https?://", full_request))
    no_web_requested = any(
        marker in full_request
        for marker in (
            "do not browse",
            "don't browse",
            "no browsing",
            "do not search",
            "don't search",
            "no online search",
            "without web search",
            "no web search",
            "without browsing",
            "offline only",
            "no internet",
        )
    )
    delivery_pattern = re.compile(r"\b(?:send|deliver|recipient|dispatch|outbox|email)\b")
    explicit_send_pattern = re.compile(r"\b(?:send|deliver|dispatch|outbox)\b(?![- ]ready)")
    negated_send_pattern = re.compile(r"\b(?:do not|don't|do n't|not)\s+(?:send|deliver|dispatch|outbox)\b")
    writing_patterns = (
        r"\brewrite\b",
        r"\bwrite\b",
        r"\bsummar(?:y|ize|ized|izing|isation|ization)\b",
        r"\bredraft\b",
        r"\bdraft\b",
        r"\bcompose\b",
        r"\breport(?:\s+(?:draft|email|summary|brief|memo|document))\b",
    )
    research_patterns = (
        r"\bresearch\b",
        r"\bsearch\b",
        r"\bsource\b",
        r"\bsources\b",
        r"\bevidence\b",
        r"\binvestigat(?:e|ion)\b",
        r"\blook up\b",
        r"\bweb\b",
        r"\bonline\b",
        r"\bfact[- ]check\b",
    )
    explicit_web_pattern = re.compile(
        r"\b(?:browse|browser|web|search|extract|inspect|open url|open page|visit)\b"
    )
    visual_browser_pattern = re.compile(
        r"\b(?:browse|browser|inspect|open url|open page|visit|navigate|scroll|click|website)\b"
    )

    is_writing_step = any(re.search(pattern, text) for pattern in writing_patterns)
    is_research_step = any(re.search(pattern, text) for pattern in research_patterns)
    research_needs_synthesis = bool(
        is_research_step
        and any(
            marker in text
            for marker in (
                "brief",
                "summary",
                "executive",
                "citations section",
                "evidence citations",
            )
        )
    )
    request_wants_research = any(re.search(pattern, full_request) for pattern in research_patterns)
    has_delivery_signal = bool(delivery_pattern.search(text))
    explicit_send_requested = bool(explicit_send_pattern.search(text)) and not bool(negated_send_pattern.search(text))
    role_implies_delivery = any(
        marker in role_text
        for marker in ("deliver", "delivery", "mailer", "sender", "dispatch")
    )
    role_implies_writing = any(
        marker in role_text
        for marker in ("writer", "author", "editor", "content", "email specialist", "drafter")
    )
    role_implies_research = any(
        marker in role_text
        for marker in ("research", "analyst", "reviewer", "browser", "document", "fact checker")
    )
    hint_has_delivery = bool(
        hint_tokens & {"send", "delivery", "deliver", "dispatch", "mailer"}
    )
    hint_has_writing = bool(
        hint_tokens & {"report", "writer", "writing", "summary", "summarization", "rewrite", "draft", "email", "mail", "gmail"}
    )
    hint_has_research = bool(
        hint_tokens & {"browser", "web", "search", "research", "sources", "evidence", "scrape", "scraping"}
    )
    research_priority = role_implies_research or hint_has_research or is_research_step
    writing_priority = (
        role_implies_writing
        or hint_has_writing
        or (is_writing_step and not role_implies_research and not hint_has_research)
    )
    delivery_priority = (
        role_implies_delivery
        or hint_has_delivery
        or (has_delivery_signal and not research_priority and not writing_priority)
    )
    is_delivery_step = has_delivery_signal and (delivery_priority or not research_priority)
    delivery_only_writing = (
        is_delivery_step and delivery_priority and not bool(explicit_web_pattern.search(text))
    )
    explicit_send_delivery = bool(
        explicit_send_requested
        or role_implies_delivery
        or hint_has_delivery
    )
    visual_browser_requested = bool(
        visual_browser_pattern.search(text) or visual_browser_pattern.search(full_request)
    )

    def _add(tool_id: str) -> None:
        value = str(tool_id or "").strip()
        if value and value not in normalized:
            normalized.append(value)

    for raw in hints:
        token = str(raw or "").strip().lower()
        if not token:
            continue
        if "." in token:
            _add(token)
            continue
        if token in {"gmail", "email", "mail"}:
            if explicit_send_delivery or delivery_priority:
                _add("gmail.draft")
            continue
        if token in {"send", "delivery", "deliver", "dispatch", "mailer"}:
            _add("gmail.draft")
            _add("gmail.send")
            _add("mailer.report_send")
            continue
        if token in {"report", "writer", "writing", "summary", "summarization", "rewrite", "draft"}:
            if not delivery_only_writing:
                _add("report.generate")
            continue
        if token in {"browser", "web", "search", "research", "sources", "evidence", "scrape", "scraping"}:
            if not delivery_only_writing and not no_web_requested:
                _add("marketing.web_research")
                _add("web.extract.structured")
                if has_explicit_url or visual_browser_requested:
                    _add("browser.playwright.inspect")
            continue

    if writing_priority and not delivery_only_writing:
        _add("report.generate")
    if research_needs_synthesis and not delivery_only_writing:
        _add("report.generate")
    if (is_research_step or research_priority) and not no_web_requested and not delivery_only_writing:
        _add("marketing.web_research")
        _add("web.extract.structured")
        if has_explicit_url or visual_browser_requested:
            _add("browser.playwright.inspect")
    if explicit_send_delivery:
        _add("gmail.draft")
        _add("gmail.send")
        _add("mailer.report_send")

    if not normalized:
        if is_delivery_step:
            _add("gmail.draft")
            _add("gmail.send")
            _add("mailer.report_send")
        if is_research_step and not no_web_requested and not delivery_only_writing:
            _add("marketing.web_research")
            _add("web.extract.structured")
            if has_explicit_url or visual_browser_requested:
                _add("browser.playwright.inspect")
        if is_writing_step and not delivery_only_writing:
            _add("report.generate")

    # Guardrail: if the request clearly asks for research and this isn't a
    # delivery-only step, force at least one real research tool path.
    has_research_tool = any(
        tool_id in normalized
        for tool_id in ("marketing.web_research", "web.extract.structured", "browser.playwright.inspect")
    )
    if (
        request_wants_research
        and not delivery_only_writing
        and not no_web_requested
        and not has_research_tool
        and not role_implies_writing
        and not role_implies_delivery
    ):
        _add("marketing.web_research")
        _add("web.extract.structured")
        if has_explicit_url or visual_browser_requested:
            _add("browser.playwright.inspect")

    if (is_research_step or research_priority) and not delivery_priority:
        blocked_delivery_tools = (
            {"gmail.send", "mailer.report_send"}
            if role_implies_writing or writing_priority
            else {"gmail.draft", "gmail.send", "mailer.report_send"}
        )
        normalized = [
            tool_id
            for tool_id in normalized
            if tool_id not in blocked_delivery_tools
        ]
    if explicit_send_delivery and not research_priority:
        normalized = [
            tool_id
            for tool_id in normalized
            if tool_id not in {"marketing.web_research", "web.extract.structured", "browser.playwright.inspect"}
        ]
    if role_implies_writing and not role_implies_research and not visual_browser_requested and not has_explicit_url:
        normalized = [
            tool_id
            for tool_id in normalized
            if tool_id not in {"marketing.web_research", "web.extract.structured", "browser.playwright.inspect"}
        ]
    if delivery_only_writing and explicit_send_delivery and not role_implies_writing and "report.generate" in normalized:
        normalized = [tool_id for tool_id in normalized if tool_id != "report.generate"]
    if not writing_priority and not research_needs_synthesis and "report.generate" in normalized:
        normalized = [tool_id for tool_id in normalized if tool_id != "report.generate"]

    if no_web_requested:
        blocked = {
            "marketing.web_research",
            "browser.playwright.inspect",
            "web.extract.structured",
            "web.dataset.adapter",
            "browser.contact_form.send",
        }
        normalized = [tool_id for tool_id in normalized if tool_id not in blocked]

    return normalized


def _sanitize_plan(plan: dict[str, Any], *, description: str) -> dict[str, Any]:
    """Normalize planner output into executable worker steps."""
    raw_steps = plan.get("steps")
    raw_edges = plan.get("edges")
    raw_connectors = plan.get("connectors_needed")

    steps: list[dict[str, Any]] = []
    seen_step_ids: set[str] = set()
    for index, candidate in enumerate(raw_steps if isinstance(raw_steps, list) else [], start=1):
        if not isinstance(candidate, dict):
            continue

        step_id = str(candidate.get("step_id") or "").strip() or f"step_{index}"
        if not re.fullmatch(r"step_\d+", step_id):
            step_id = f"step_{index}"
        while step_id in seen_step_ids:
            step_id = f"step_{len(seen_step_ids) + 1}"
        seen_step_ids.add(step_id)

        description_value = str(candidate.get("description") or "").strip() or f"Handle workflow step {index}."
        role = _sanitize_agent_role(
            raw_role=str(candidate.get("agent_role") or "").strip(),
            step_description=description_value,
            index=index,
        )
        tools = candidate.get("tools_needed")
        tool_ids = [
            str(tool_id).strip()
            for tool_id in (tools if isinstance(tools, list) else [])
            if str(tool_id).strip()
        ]
        steps.append(
            {
                "step_id": step_id,
                "agent_role": role,
                "description": description_value,
                "tools_needed": tool_ids[:12],
            }
        )

    if not steps:
        return {"steps": [], "edges": [], "connectors_needed": []}

    valid_step_ids = {str(step["step_id"]) for step in steps}
    edges: list[dict[str, str]] = []
    seen_edges: set[tuple[str, str]] = set()
    for candidate in raw_edges if isinstance(raw_edges, list) else []:
        if not isinstance(candidate, dict):
            continue
        from_step = str(candidate.get("from_step") or "").strip()
        to_step = str(candidate.get("to_step") or "").strip()
        if from_step not in valid_step_ids or to_step not in valid_step_ids or from_step == to_step:
            continue
        edge = (from_step, to_step)
        if edge in seen_edges:
            continue
        seen_edges.add(edge)
        edges.append({"from_step": from_step, "to_step": to_step})

    if not edges and len(steps) > 1:
        edges = [
            {"from_step": steps[idx]["step_id"], "to_step": steps[idx + 1]["step_id"]}
            for idx in range(len(steps) - 1)
        ]

    connectors: list[dict[str, str]] = []
    for candidate in raw_connectors if isinstance(raw_connectors, list) else []:
        if not isinstance(candidate, dict):
            continue
        connector_id = str(candidate.get("connector_id") or "").strip()
        reason = str(candidate.get("reason") or "").strip()
        if not connector_id:
            continue
        connectors.append({"connector_id": connector_id, "reason": reason})

    steps = _rescope_step_descriptions(
        steps=steps,
        request_description=description,
    )

    return {"steps": steps, "edges": edges, "connectors_needed": connectors}


def _expand_thin_team_via_llm(
    *,
    plan: dict[str, Any],
    description: str,
    tenant_id: str = "",
) -> dict[str, Any]:
    steps = plan.get("steps")
    if not isinstance(steps, list) or len(steps) < 2:
        return plan
    unique_roles = {
        _normalize_role_key(str(step.get("agent_role") or ""))
        for step in steps
        if isinstance(step, dict) and str(step.get("agent_role") or "").strip()
    }
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
        "Rules:\n"
        "- Preserve the user request exactly.\n"
        "- Keep the workflow minimal.\n"
        "- Only enrich the team if more role diversity will materially improve evidence quality, review quality, or delivery quality.\n"
        "- Prefer adding roles such as supervisor, analyst, reviewer, browser specialist, document reader, email specialist, or delivery specialist when justified.\n"
        "- Do not add filler steps.\n"
        "- Maximum 6 steps.\n\n"
        f"User request:\n{description[:1200]}\n\n"
        f"Role catalog:\n{_ROLE_CATALOG_PROMPT}\n\n"
        f"Current plan:\n{json.dumps(plan, ensure_ascii=False)}"
    )
    revised, _reason = _request_json_from_llm(
        system_prompt="You improve workflow team composition. Return JSON only.",
        user_prompt=prompt,
        timeout_seconds=min(max(_fallback_intent_timeout_seconds() + 2.0, 5.0), 20.0),
        max_tokens=1200,
    )
    if not isinstance(revised, dict):
        return plan
    revised_plan = _sanitize_plan(revised, description=description)
    revised_steps = revised_plan.get("steps")
    if not isinstance(revised_steps, list) or not revised_steps:
        return plan
    revised_roles = {
        _normalize_role_key(str(step.get("agent_role") or ""))
        for step in revised_steps
        if isinstance(step, dict) and str(step.get("agent_role") or "").strip()
    }
    if len(revised_roles) <= len(unique_roles):
        return plan
    return revised_plan


def _promote_supervisor_presence_via_llm(
    *,
    plan: dict[str, Any],
    description: str,
    tenant_id: str = "",
) -> dict[str, Any]:
    steps = plan.get("steps")
    if not isinstance(steps, list) or len(steps) < 4:
        return plan
    unique_roles = {
        _normalize_role_key(str(step.get("agent_role") or ""))
        for step in steps
        if isinstance(step, dict) and str(step.get("agent_role") or "").strip()
    }
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
        "Rules:\n"
        "- Keep the workflow minimal and executable.\n"
        "- Add a supervisor role only if it materially improves coordination, evidence review, or delivery readiness.\n"
        "- If you add a supervisor, give that role a real coordination or review task instead of filler narration.\n"
        "- Preserve the existing specialist work.\n"
        "- Maximum 6 steps.\n\n"
        f"User request:\n{description[:1200]}\n\n"
        f"Role catalog:\n{_ROLE_CATALOG_PROMPT}\n\n"
        f"Current plan:\n{json.dumps(plan, ensure_ascii=False)}"
    )
    revised, _reason = _request_json_from_llm(
        system_prompt="You improve workflow team composition for complex collaborative work. Return JSON only.",
        user_prompt=prompt,
        timeout_seconds=min(max(_fallback_intent_timeout_seconds() + 2.0, 5.0), 20.0),
        max_tokens=1200,
    )
    if not isinstance(revised, dict):
        return plan
    revised_plan = _sanitize_plan(revised, description=description)
    revised_steps = revised_plan.get("steps")
    if not isinstance(revised_steps, list) or not revised_steps:
        return plan
    revised_roles = {
        _normalize_role_key(str(step.get("agent_role") or ""))
        for step in revised_steps
        if isinstance(step, dict) and str(step.get("agent_role") or "").strip()
    }
    if not any("supervisor" in role or role in {"team lead", "lead"} for role in revised_roles):
        return plan
    return revised_plan


def _sanitize_agent_role(*, raw_role: str, step_description: str, index: int) -> str:
    role = " ".join(str(raw_role or "").strip().split())
    if role and not _is_reserved_orchestrator_role(role) and not _looks_like_tool_identifier(role):
        return role[:80]
    return _derive_role_from_description(step_description=step_description, index=index)


def _is_reserved_orchestrator_role(role: str) -> bool:
    normalized = _normalize_role_key(role).replace("_", " ")
    return normalized in _RESERVED_ORCHESTRATOR_ROLES


def _looks_like_tool_identifier(value: str) -> bool:
    raw = str(value or "").strip().lower()
    if not raw:
        return False
    if "." in raw or "/" in raw or ":" in raw:
        return True
    tokens = [token for token in re.split(r"[\s._:/-]+", raw) if token]
    toolish_markers = {"playwright", "browser", "tool", "connector", "provider"}
    return any(token in toolish_markers for token in tokens)


def _derive_role_from_description(*, step_description: str, index: int) -> str:
    return infer_fallback_role(step_description, index=index)


def _is_brain_agent_identifier(value: str) -> bool:
    normalized = _normalize_role_key(value).replace("_", " ")
    return normalized == "brain" or normalized.startswith("brain ") or normalized.endswith(" brain")


def _planner_runtime_available() -> tuple[bool, str]:
    """Return whether a direct JSON planner runtime is configured."""
    try:
        from api.services.agent.llm_runtime import has_openai_credentials
        if has_openai_credentials():
            return True, "openai"
    except Exception:
        pass
    try:
        has_anthropic = bool(str(os.getenv("ANTHROPIC_API_KEY", "")).strip())
        if has_anthropic:
            return True, "anthropic"
    except Exception:
        pass
    return False, "none"


def _request_json_from_llm(
    *,
    system_prompt: str,
    user_prompt: str,
    timeout_seconds: float,
    max_tokens: int,
) -> tuple[dict[str, Any] | None, str]:
    """Request strict JSON from the configured planner runtime."""
    last_reason = "no runtime attempted"
    try:
        from api.services.agent.llm_runtime import call_json_response, has_openai_credentials
        if has_openai_credentials():
            payload = call_json_response(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.0,
                timeout_seconds=max(5, int(timeout_seconds)),
                max_tokens=max_tokens,
                enable_thinking=True,
                use_fallback_models=True,
            )
            if isinstance(payload, dict):
                return payload, "openai"
            diagnosis = _diagnose_openai_runtime_issue(timeout_seconds=max(5.0, float(timeout_seconds)))
            last_reason = diagnosis or "openai returned empty payload"
        else:
            last_reason = "openai credentials missing"
    except Exception as exc:
        logger.debug("OpenAI JSON planner call failed: %s", exc)
        last_reason = f"openai error: {str(exc)[:160]}"
    try:
        anthropic_key = str(os.getenv("ANTHROPIC_API_KEY", "")).strip()
        if anthropic_key:
            from api.services.agents.llm_utils import call_llm_json
            payload = call_llm_json(
                (
                    f"{system_prompt}\n\n"
                    "Return valid JSON only.\n\n"
                    f"{user_prompt}"
                ),
                temperature=0.0,
                max_tokens=max(300, min(2000, int(max_tokens))),
            )
            if isinstance(payload, dict):
                return payload, "anthropic"
            last_reason = "anthropic returned non-dict payload"
        else:
            if "missing" in last_reason:
                last_reason = "openai credentials missing; anthropic credentials missing"
    except Exception as exc:
        logger.debug("Anthropic JSON planner call failed: %s", exc)
        last_reason = f"anthropic error: {str(exc)[:160]}"
    return None, last_reason


def _diagnose_openai_runtime_issue(*, timeout_seconds: float) -> str:
    """Best-effort diagnosis for empty OpenAI planner responses."""
    try:
        from api.services.agent.llm_runtime import openai_api_key
        key = str(openai_api_key() or "").strip()
        if not key:
            return "openai credentials missing"
        base = str(os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")).strip().rstrip("/")
        model = str(os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")).strip() or "gpt-4o-mini"
        request_obj = Request(
            f"{base}/chat/completions",
            method="POST",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            data=json.dumps(
                {
                    "model": model,
                    "temperature": 0.0,
                    "max_tokens": 32,
                    "messages": [{"role": "user", "content": "Return JSON: {\"ok\":true}"}],
                }
            ).encode("utf-8"),
        )
        with urlopen(request_obj, timeout=max(8, int(timeout_seconds))):
            return ""
    except HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="ignore")
        except Exception:
            body = ""
        code = f"http_{int(getattr(exc, 'code', 0) or 0)}"
        marker = ""
        if "insufficient_quota" in body:
            marker = "insufficient_quota"
        elif "invalid_api_key" in body:
            marker = "invalid_api_key"
        elif "rate_limit" in body or "429" in body:
            marker = "rate_limited"
        detail = marker or code
        return f"openai unavailable: {detail}"
    except Exception as exc:
        return f"openai unavailable: {type(exc).__name__}"


def _assembly_timeout_seconds() -> float:
    raw = str(os.getenv("MAIA_ASSEMBLY_LLM_TIMEOUT_SEC", "25")).strip()
    try:
        parsed = float(raw)
    except Exception:
        return 25.0
    return max(5.0, min(parsed, 120.0))


def _fallback_intent_timeout_seconds() -> float:
    raw = str(os.getenv("MAIA_FALLBACK_INTENT_TIMEOUT_SEC", "8")).strip()
    try:
        parsed = float(raw)
    except Exception:
        return 8.0
    return max(3.0, min(parsed, 30.0))


def _emit(on_event: Optional[Callable], run_id: str, event: dict[str, Any]) -> None:
    event.setdefault("status", "info")
    event.setdefault("data", {})
    event["data"]["run_id"] = run_id
    if on_event:
        try:
            on_event(event)
        except Exception:
            pass
    try:
        from api.services.agent.live_events import get_live_event_broker
        get_live_event_broker().publish(user_id="", run_id=run_id, event=event)
    except Exception:
        pass


