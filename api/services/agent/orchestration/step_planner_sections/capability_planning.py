from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.llm_runtime import call_json_response, env_bool
from api.services.agent.policy import AgentToolCapability, get_capability_matrix

from ..models import TaskPreparation

_INTENT_TAG_DOMAIN_MAP: dict[str, tuple[str, ...]] = {
    "web_research": ("marketing_research",),
    "location_lookup": ("marketing_research",),
    "report_generation": ("reporting",),
    "docs_write": ("document_ops",),
    "sheets_update": ("document_ops",),
    "highlight_extract": ("document_ops",),
    "email_delivery": ("email_ops",),
    "contact_form_submission": ("outreach",),
}

_CONTRACT_ACTION_DOMAIN_MAP: dict[str, tuple[str, ...]] = {
    "send_email": ("email_ops",),
    "create_document": ("document_ops", "reporting"),
    "update_sheet": ("document_ops",),
    "send_invoice": ("invoice",),
    "create_invoice": ("invoice",),
}

_DOMAIN_PRIORITY: dict[str, int] = {
    "marketing_research": 10,
    "analytics": 20,
    "ads_analysis": 25,
    "data_analysis": 30,
    "business_workflow": 35,
    "reporting": 40,
    "document_ops": 50,
    "email_ops": 60,
    "invoice": 70,
    "outreach": 80,
    "scheduling": 90,
    "workplace": 100,
}

_ACTION_PRIORITY: dict[str, int] = {
    "read": 10,
    "draft": 20,
    "execute": 30,
}

@dataclass(frozen=True)
class CapabilityPlanningAnalysis:
    required_domains: list[str]
    preferred_tool_ids: list[str]
    matched_signals: list[str]
    rationale: list[str]


def _domain_sort_key(domain: str) -> tuple[int, str]:
    return (_DOMAIN_PRIORITY.get(domain, 999), domain)


def _extract_available_tool_ids(registry: Any) -> set[str]:
    try:
        rows = registry.list_tools()
    except Exception:
        return set()
    output: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        tool_id = str(row.get("tool_id") or "").strip()
        if tool_id:
            output.add(tool_id)
    return output


def _capabilities_for_available_tools(available_tool_ids: set[str]) -> list[AgentToolCapability]:
    if not available_tool_ids:
        return []
    return [
        capability
        for capability in get_capability_matrix()
        if capability.tool_id in available_tool_ids
    ]


def _append_domains(
    *,
    domains: set[str],
    matched_signals: list[str],
    reason: str,
    candidate_domains: tuple[str, ...],
) -> None:
    added = False
    for domain in candidate_domains:
        if domain not in domains:
            domains.add(domain)
            added = True
    if added:
        matched_signals.append(reason)


def _build_preferred_tools(
    *,
    domains: list[str],
    capabilities: list[AgentToolCapability],
) -> list[str]:
    domain_map: dict[str, list[AgentToolCapability]] = {}
    for capability in capabilities:
        domain_map.setdefault(capability.domain, []).append(capability)

    preferred: list[str] = []
    for domain in domains:
        rows = sorted(
            domain_map.get(domain, []),
            key=lambda item: (
                _ACTION_PRIORITY.get(item.action_class, 999),
                item.tool_id,
            ),
        )
        for capability in rows[:4]:
            preferred.append(capability.tool_id)

    return list(dict.fromkeys(preferred))


def _infer_domains_with_llm(
    *,
    request: ChatRequest,
    task_prep: TaskPreparation,
    available_domains: list[str],
) -> list[str]:
    if not available_domains:
        return []
    if not env_bool("MAIA_AGENT_LLM_CAPABILITY_ROUTING_ENABLED", default=True):
        return []

    payload = {
        "message": str(request.message or "").strip(),
        "agent_goal": str(request.agent_goal or "").strip(),
        "rewritten_task": str(task_prep.rewritten_task or "").strip(),
        "contract_objective": str(task_prep.contract_objective or "").strip(),
        "contract_outputs": list(task_prep.contract_outputs[:8]),
        "contract_facts": list(task_prep.contract_facts[:8]),
        "contract_actions": list(task_prep.contract_actions[:8]),
        "intent_tags": [str(tag).strip() for tag in task_prep.task_intelligence.intent_tags[:8]],
        "available_domains": available_domains,
    }
    prompt = (
        "Select capability domains for planning based on the task brief.\n"
        "Return JSON only in this schema:\n"
        '{ "required_domains": ["domain_a", "domain_b"] }\n'
        "Rules:\n"
        "- Use only available_domains.\n"
        "- Pick 1-6 domains.\n"
        "- User does not need to name APIs; infer required domains from business intent.\n"
        "- Favor non-technical workflow domains when they can satisfy the request.\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    response = call_json_response(
        system_prompt=(
            "You route enterprise agent tasks to capability domains. "
            "Return strict JSON only."
        ),
        user_prompt=prompt,
        temperature=0.0,
        timeout_seconds=12,
        max_tokens=180,
    )
    if not isinstance(response, dict):
        return []
    raw = response.get("required_domains")
    if not isinstance(raw, list):
        return []
    selected: list[str] = []
    allowed = set(available_domains)
    for item in raw:
        value = str(item).strip()
        if not value or value not in allowed or value in selected:
            continue
        selected.append(value)
        if len(selected) >= 6:
            break
    return selected


def analyze_capability_plan(
    *,
    request: ChatRequest,
    task_prep: TaskPreparation,
    registry: Any,
) -> CapabilityPlanningAnalysis:
    available_tool_ids = _extract_available_tool_ids(registry)
    capabilities = _capabilities_for_available_tools(available_tool_ids)
    available_domains = sorted(
        {capability.domain for capability in capabilities if str(capability.domain).strip()},
        key=_domain_sort_key,
    )
    domains: set[str] = set()
    matched_signals: list[str] = []

    intent_tags = {
        str(tag).strip().lower()
        for tag in task_prep.task_intelligence.intent_tags
        if str(tag).strip()
    }
    for tag in sorted(intent_tags):
        mapped = _INTENT_TAG_DOMAIN_MAP.get(tag)
        if mapped:
            _append_domains(
                domains=domains,
                matched_signals=matched_signals,
                reason=f"intent_tag:{tag}",
                candidate_domains=mapped,
            )

    for action in task_prep.contract_actions:
        action_text = str(action).strip().lower()
        mapped = _CONTRACT_ACTION_DOMAIN_MAP.get(action_text)
        if mapped:
            _append_domains(
                domains=domains,
                matched_signals=matched_signals,
                reason=f"contract_action:{action_text}",
                candidate_domains=mapped,
            )

    raw_text = " ".join(
        [
            str(request.message or "").strip().lower(),
            str(request.agent_goal or "").strip().lower(),
            str(task_prep.contract_objective or "").strip().lower(),
        ]
    ).strip()
    llm_domains = _infer_domains_with_llm(
        request=request,
        task_prep=task_prep,
        available_domains=available_domains,
    )
    for domain in llm_domains:
        _append_domains(
            domains=domains,
            matched_signals=matched_signals,
            reason=f"llm_domain:{domain}",
            candidate_domains=(domain,),
        )
        llm_signal = f"llm_domain:{domain}"
        if llm_signal not in matched_signals:
            matched_signals.append(llm_signal)

    if not domains:
        domains.update(("marketing_research", "reporting"))
        matched_signals.append("fallback:default_domains")

    ordered_domains = sorted(domains, key=_domain_sort_key)
    preferred_tool_ids = _build_preferred_tools(
        domains=ordered_domains,
        capabilities=capabilities,
    )
    preferred_tool_ids = [tool_id for tool_id in preferred_tool_ids if tool_id in available_tool_ids]
    preferred_tool_ids = list(dict.fromkeys(preferred_tool_ids))

    rationale = [
        f"Selected {len(ordered_domains)} capability domain(s) from {len(matched_signals)} signal(s).",
        "Planner should prioritize preferred tools while keeping execution policy constraints.",
    ]
    rationale.append(
        "Workspace tools are included only when task intent or contract actions require Docs/Sheets artifacts."
    )

    return CapabilityPlanningAnalysis(
        required_domains=ordered_domains,
        preferred_tool_ids=preferred_tool_ids[:20],
        matched_signals=matched_signals[:24],
        rationale=rationale[:6],
    )
