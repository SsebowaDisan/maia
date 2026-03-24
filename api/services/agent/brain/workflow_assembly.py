"""Brain workflow assembly split into focused section modules."""
from __future__ import annotations

import json
import sys
from typing import Any, Callable, Optional

from api.services.agent.brain.workflow_assembly_sections.common import (
    _ROLE_CATALOG_PROMPT,
    _SYSTEM_PROMPT,
    _RESERVED_ORCHESTRATOR_ROLES,
    _assembly_timeout_seconds,
    _emit,
    _extract_email,
    _fallback_intent_timeout_seconds,
    _normalize_role_key,
    _parse_json_object,
    _parse_plan,
    _planner_runtime_available,
    logger,
)
from api.services.agent.brain.workflow_assembly_sections.core import (
    _build_definition as _build_definition_impl,
    _infer_step_timeout_seconds as _infer_step_timeout_seconds_impl,
)
from api.services.agent.brain.workflow_assembly_sections.llm_planning import (
    _diagnose_openai_runtime_issue,
)
from api.services.agent.brain.workflow_assembly_sections.request_shape import (
    _delivery_step_description,
    _derive_primary_search_query,
    _derive_request_focus,
    _infer_input_mapping,
    _normalize_step_tool_ids,
    _rebalance_research_email_steps,
    _request_needs_research_email_flow,
    _research_step_description,
    _rescope_step_descriptions,
    _review_step_description,
    _step_role_family,
    _writer_step_description,
)
from api.services.agent.brain.workflow_assembly_sections.roles import (
    _derive_role_from_description,
    _is_brain_agent_identifier,
    _is_reserved_orchestrator_role,
    _looks_like_tool_identifier,
    _to_agent_slug,
)


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def assemble_workflow(*, description: str, tenant_id: str = "", on_event: Optional[Callable] = None) -> dict[str, Any]:
    from api.services.agent.brain.workflow_assembly_sections import core as _core
    return _core.assemble_workflow(description=description, tenant_id=tenant_id, on_event=on_event, ops=sys.modules[__name__])


def _build_definition(description: str, steps: list[dict], edges: list[dict], tenant_id: str = "") -> dict[str, Any]:
    from api.services.agent.brain.workflow_assembly_sections import core as _core
    return _core._build_definition(description, steps, edges, tenant_id=tenant_id, ops=sys.modules[__name__])


def _infer_step_timeout_seconds(*, step: dict[str, Any], request_description: str) -> int:
    from api.services.agent.brain.workflow_assembly_sections import core as _core
    return _core._infer_step_timeout_seconds(step=step, request_description=request_description, ops=sys.modules[__name__])


def _resolve_agent_roles(roles: list[str], tenant_id: str, request_description: str = "", role_tasks: Optional[dict[str, str]] = None) -> dict[str, str]:
    from api.services.agent.brain.workflow_assembly_sections import roles as _roles
    return _roles._resolve_agent_roles(roles, tenant_id, request_description=request_description, role_tasks=role_tasks, ops=sys.modules[__name__])


def _generate_role_prompts_via_llm(*, roles: list[str], request_description: str, role_tasks: dict[str, str], tenant_id: str) -> dict[str, str]:
    from api.services.agent.brain.workflow_assembly_sections import roles as _roles
    return _roles._generate_role_prompts_via_llm(roles=roles, request_description=request_description, role_tasks=role_tasks, tenant_id=tenant_id, ops=sys.modules[__name__])


def _resolve_agent_id_for_step(*, role_to_agent_id: dict[str, str], normalized_role_map: dict[str, str], step: dict[str, Any]) -> str:
    from api.services.agent.brain.workflow_assembly_sections import roles as _roles
    return _roles._resolve_agent_id_for_step(role_to_agent_id=role_to_agent_id, normalized_role_map=normalized_role_map, step=step)


def _sanitize_agent_role(*, raw_role: str, step_description: str, index: int) -> str:
    from api.services.agent.brain.workflow_assembly_sections import roles as _roles
    return _roles._sanitize_agent_role(raw_role=raw_role, step_description=step_description, index=index)


def _fallback_plan_from_description(description: str, tenant_id: str = "") -> dict[str, Any]:
    from api.services.agent.brain.workflow_assembly_sections import llm_planning as _llm
    return _llm._fallback_plan_from_description(description, tenant_id=tenant_id, ops=sys.modules[__name__])


def _degraded_plan_without_llm(description: str) -> dict[str, Any]:
    from api.services.agent.brain.workflow_assembly_sections import llm_planning as _llm
    return _llm._degraded_plan_without_llm(description, ops=sys.modules[__name__])


def _infer_fallback_plan_via_llm(description: str, tenant_id: str = "") -> dict[str, Any]:
    from api.services.agent.brain.workflow_assembly_sections import llm_planning as _llm
    return _llm._infer_fallback_plan_via_llm(description, tenant_id=tenant_id, ops=sys.modules[__name__])


def _expand_thin_team_via_llm(*, plan: dict[str, Any], description: str, tenant_id: str = "") -> dict[str, Any]:
    from api.services.agent.brain.workflow_assembly_sections import llm_planning as _llm
    return _llm._expand_thin_team_via_llm(plan=plan, description=description, tenant_id=tenant_id, ops=sys.modules[__name__])


def _promote_supervisor_presence_via_llm(*, plan: dict[str, Any], description: str, tenant_id: str = "") -> dict[str, Any]:
    from api.services.agent.brain.workflow_assembly_sections import llm_planning as _llm
    return _llm._promote_supervisor_presence_via_llm(plan=plan, description=description, tenant_id=tenant_id, ops=sys.modules[__name__])


def _request_json_from_llm(*, system_prompt: str, user_prompt: str, timeout_seconds: float, max_tokens: int) -> tuple[dict[str, Any] | None, str]:
    from api.services.agent.brain.workflow_assembly_sections import llm_planning as _llm
    return _llm._request_json_from_llm(system_prompt=system_prompt, user_prompt=user_prompt, timeout_seconds=timeout_seconds, max_tokens=max_tokens, ops=sys.modules[__name__])


def _sanitize_plan(plan: dict[str, Any], *, description: str) -> dict[str, Any]:
    from api.services.agent.brain.workflow_assembly_sections import request_shape as _shape
    return _shape._sanitize_plan(plan, description=description, ops=sys.modules[__name__])
