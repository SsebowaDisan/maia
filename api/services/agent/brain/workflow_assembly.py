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

logger = logging.getLogger(__name__)

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
- Keep it minimal — do not add steps that are not required by the request.
- Do not default to generic role chains (for example researcher→analyst→writer→deliverer) unless the request truly needs them.
- Use one step when one step is enough.
- Connect steps based on dependency logic, not fixed phase assumptions.
- Identify which connectors (gmail, google_analytics, slack, etc.) are needed.
- If the user provides a concrete recipient/target, preserve it in the relevant delivery step description.
- If the request says not to browse/search, do not add browser/search connectors or steps.
- Maximum 6 steps.
- step_id format: step_1, step_2, etc."""


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

    _emit(on_event, run_id, {
        "event_type": "assembly_brain_thinking",
        "title": "Brain is planning the team",
        "detail": "Analysing your request and figuring out what we need...",
        "data": {"from_agent": "brain"},
    })

    planner_available, planner_label = _planner_runtime_available()
    if not planner_available:
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
    assembly_payload, planner_reason = _request_json_from_llm(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=f"Build a workflow for this task:\n\n{description[:1200]}",
        timeout_seconds=_assembly_timeout_seconds(),
        max_tokens=1200,
    )
    plan = assembly_payload if isinstance(assembly_payload, dict) else {"steps": [], "edges": [], "connectors_needed": []}
    if not plan.get("steps"):
        fallback_reason = f"primary planner returned no valid steps ({planner_reason})"
        plan = _fallback_plan_from_description(description, tenant_id=tenant_id)
        if plan.get("steps"):
            _emit(on_event, run_id, {
                "event_type": "assembly_narration",
                "title": "Brain fallback planner",
                "detail": f"Using secondary LLM planning path because: {fallback_reason}",
                "data": {"from_agent": "brain", "narration": True, "fallback_reason": fallback_reason},
            })
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
        # Brain narration
        _emit(on_event, run_id, {
            "event_type": "assembly_narration",
            "title": f"Brain: Step {i + 1}",
            "detail": f"I'm adding a {step.get('agent_role', 'agent')} to {step.get('description', 'handle this step')}",
            "data": {"from_agent": "brain", "narration": True},
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
                    "tool_ids": _normalize_step_tool_ids(
                        step=s,
                        request_description=description,
                    ),
                },
                "output_key": f"output_{s['step_id']}",
                "input_mapping": _infer_input_mapping(s, steps, edges),
            }
            for s in steps
        ],
        "edges": [
            {"from_step": e["from_step"], "to_step": e["to_step"]}
            for e in edges
        ],
    }


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
                mapping[role] = existing_by_id[role_lower]
                continue
            if role_slug in existing_by_id:
                mapping[role] = existing_by_id[role_slug]
                continue
            # Try match by name
            if role_lower in existing_by_name:
                mapping[role] = existing_by_name[role_lower]
                continue
            # Try fuzzy match
            matched = False
            for name, aid in existing_by_name.items():
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
                    fallback = next(iter(existing_by_id.values()))
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
    return str(match.group(1)).strip() if match else ""


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


def _infer_input_mapping(step: dict, all_steps: list[dict], edges: list[dict]) -> dict[str, str]:
    """Infer input mapping from predecessor steps."""
    predecessors = [e["from_step"] for e in edges if e["to_step"] == step["step_id"]]
    mapping: dict[str, str] = {}
    if not predecessors:
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
        "- Keep each system_prompt under 120 words.\n\n"
        f"User request:\n{request_description[:1200]}\n\n"
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
        if token in {"gmail", "email"}:
            _add("gmail.draft")
            _add("gmail.send")
            continue
        if token in {"report", "writer", "writing"}:
            _add("report.generate")
            continue
        if token in {"browser", "web", "search"}:
            _add("marketing.web_research")
            _add("browser.playwright.inspect")
            continue

    text = " ".join(
        [
            str(step.get("agent_role") or ""),
            str(step.get("description") or ""),
        ]
    ).strip().lower()
    if not normalized:
        if any(marker in text for marker in ("rewrite", "write", "summar", "report", "redraft")):
            _add("report.generate")
        elif any(marker in text for marker in ("send", "deliver", "recipient", "dispatch", "outbox")):
            _add("gmail.draft")
            _add("gmail.send")

    full_request = str(request_description or "").lower()
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
        )
    )
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

