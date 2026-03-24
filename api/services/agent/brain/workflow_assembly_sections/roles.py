from __future__ import annotations

import json
import re
from typing import Any, Optional

from api.services.agent.brain.team_role_catalog import infer_fallback_role

from .common import _RESERVED_ORCHESTRATOR_ROLES, _ROLE_CATALOG_PROMPT, _extract_email, _normalize_role_key


def _to_agent_slug(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-_")
    if not text:
        text = "agent"
    if len(text) < 3:
        text = f"{text}-agent"
    text = text[:64].strip("-_")
    if not text:
        text = "agent"
    if not text[0].isalnum():
        text = f"a{text}"
    if not text[-1].isalnum():
        text = f"{text}a"
    return text[:64]


def _resolve_agent_roles(
    roles: list[str],
    tenant_id: str,
    request_description: str = "",
    role_tasks: Optional[dict[str, str]] = None,
    ops: Any | None = None,
) -> dict[str, str]:
    if not tenant_id:
        return {r: r for r in roles}
    mapping: dict[str, str] = {}
    role_tasks = role_tasks or {}
    llm_prompts = ops._generate_role_prompts_via_llm(
        roles=sorted({str(r or "").strip() for r in roles if str(r or "").strip()}),
        request_description=request_description,
        role_tasks=role_tasks,
        tenant_id=tenant_id,
    )
    try:
        from api.services.agents.definition_store import create_agent, list_agents
        from api.schemas.agent_definition.schema import AgentDefinitionSchema

        existing = list_agents(tenant_id)
        existing_by_name = {str(a.name or "").strip().lower(): str(a.agent_id or a.id) for a in existing}
        existing_by_id = {str(a.agent_id or a.id).strip().lower(): str(a.agent_id or a.id) for a in existing}
        for role in set(roles):
            role_lower = role.strip().lower()
            role_slug = _to_agent_slug(role_lower)
            for candidate in (existing_by_id.get(role_lower), existing_by_id.get(role_slug), existing_by_name.get(role_lower)):
                if candidate and not _is_brain_agent_identifier(candidate):
                    mapping[role] = candidate
                    break
            if role in mapping:
                continue
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
            try:
                task_focus = str(role_tasks.get(role, "")).strip()
                agent_prompt = (
                    str(llm_prompts.get(role, "")).strip()
                    or str(llm_prompts.get(role_lower, "")).strip()
                    or f"You are responsible for the role '{role}'. Execute only your assigned step with evidence and clear handoff."
                )
                if task_focus:
                    agent_prompt = f"{agent_prompt}\n\nCurrent step focus: {task_focus[:500]}"
                chosen_id = role_slug
                suffix = 1
                while chosen_id in existing_by_id:
                    suffix += 1
                    chosen_id = f"{role_slug}-{suffix}"[:64].rstrip("-_")
                new_agent = create_agent(tenant_id, tenant_id, AgentDefinitionSchema(id=chosen_id, name=role.title(), system_prompt=agent_prompt))
                created_id = str(getattr(new_agent, "agent_id", None) or getattr(new_agent, "id", chosen_id))
                existing_by_id[created_id.lower()] = created_id
                existing_by_name[role_lower] = created_id
                mapping[role] = created_id
            except Exception:
                fallback = existing_by_name.get(role_lower) or existing_by_id.get(role_slug)
                if not fallback and existing_by_id:
                    fallback = next((candidate for candidate in existing_by_id.values() if not _is_brain_agent_identifier(candidate)), None)
                mapping[role] = str(fallback or "agent")
    except Exception:
        return {r: r for r in roles}
    return mapping


def _resolve_agent_id_for_step(*, role_to_agent_id: dict[str, str], normalized_role_map: dict[str, str], step: dict[str, Any]) -> str:
    raw_role = str(step.get("agent_role", "agent") or "agent")
    role = raw_role.strip() or "agent"
    return role_to_agent_id.get(raw_role) or role_to_agent_id.get(role) or normalized_role_map.get(_normalize_role_key(role)) or role


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
    return any(token in {"playwright", "browser", "tool", "connector", "provider"} for token in tokens)


def _derive_role_from_description(*, step_description: str, index: int) -> str:
    return infer_fallback_role(step_description, index=index)


def _is_brain_agent_identifier(value: str) -> bool:
    normalized = _normalize_role_key(value).replace("_", " ")
    return normalized == "brain" or normalized.startswith("brain ") or normalized.endswith(" brain")


def _generate_role_prompts_via_llm(*, roles: list[str], request_description: str, role_tasks: dict[str, str], tenant_id: str, ops: Any | None = None) -> dict[str, str]:
    if not roles or not tenant_id:
        return {}
    role_payload = [{"role": role, "task_focus": str(role_tasks.get(role, "")).strip()[:500]} for role in roles]
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
    parsed, _reason = ops._request_json_from_llm(
        system_prompt="You write strict JSON only. Return no markdown.",
        user_prompt=prompt,
        timeout_seconds=min(max(ops._fallback_intent_timeout_seconds() + 2.0, 5.0), 20.0),
        max_tokens=900,
    )
    if not isinstance(parsed, dict) or not isinstance(parsed.get("roles"), list):
        rows = []
    else:
        rows = parsed["roles"]
    from api.services.agent.brain.team_role_catalog import fallback_system_prompt_for_role
    prompts: dict[str, str] = {}
    for row in rows:
        if isinstance(row, dict):
            role = str(row.get("role") or "").strip()
            system_prompt = str(row.get("system_prompt") or "").strip()
            if role and system_prompt:
                prompts[role] = system_prompt
                prompts[role.lower()] = system_prompt
    for role in roles:
        normalized = str(role or "").strip()
        if not normalized:
            continue
        fallback_prompt = fallback_system_prompt_for_role(normalized, request_description=request_description, task_focus=str(role_tasks.get(normalized, "")).strip())
        prompts.setdefault(normalized, fallback_prompt)
        prompts.setdefault(normalized.lower(), prompts[normalized])
    return prompts
