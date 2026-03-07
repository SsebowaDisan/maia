from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.llm_runtime import call_json_response, env_bool
from api.services.agent.policy import AgentToolCapability, get_capability_matrix

from ..models import TaskPreparation

_INTENT_TAG_DOMAIN_MAP: dict[str, tuple[str, ...]] = {
    "web_research": ("marketing_research",),
    "location_lookup": ("marketing_research",),
    "goal_page_navigation": ("marketing_research",),
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

_DOMAIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")

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


def _tokenize_domain_scope(text: str) -> set[str]:
    def _canonical(raw: str) -> str:
        token = str(raw or "").strip().lower()
        for suffix in ("ization", "ation", "ments", "ment", "ities", "ity", "ing", "ed", "s"):
            if token.endswith(suffix) and (len(token) - len(suffix)) >= 4:
                token = token[: -len(suffix)]
                break
        return token

    return {
        _canonical(match.group(0))
        for match in _DOMAIN_TOKEN_RE.finditer(str(text or ""))
        if len(match.group(0)) >= 4 or any(ch.isdigit() for ch in match.group(0))
    }


def _build_domain_scope_vocab(
    capabilities: list[AgentToolCapability],
) -> tuple[dict[str, set[str]], dict[str, int]]:
    domain_vocab: dict[str, set[str]] = {}
    for capability in capabilities:
        domain = str(capability.domain or "").strip()
        if not domain:
            continue
        tokens = _tokenize_domain_scope(
            " ".join(
                [
                    domain,
                    str(capability.tool_id or "").replace(".", " "),
                    str(capability.description or ""),
                ]
            )
        )
        if not tokens:
            continue
        domain_vocab.setdefault(domain, set()).update(tokens)

    token_domain_counts: dict[str, int] = {}
    for tokens in domain_vocab.values():
        for token in tokens:
            token_domain_counts[token] = token_domain_counts.get(token, 0) + 1
    return domain_vocab, token_domain_counts


def _filter_llm_domains_by_request_scope(
    *,
    proposed_domains: list[str],
    request_text: str,
    baseline_domains: set[str],
    domain_vocab: dict[str, set[str]],
    token_domain_counts: dict[str, int],
) -> list[str]:
    request_tokens = _tokenize_domain_scope(request_text)
    if not request_tokens:
        return proposed_domains[:6]

    kept: list[str] = []
    for domain in proposed_domains:
        if domain in kept:
            continue
        if domain in baseline_domains:
            kept.append(domain)
            continue
        vocab = domain_vocab.get(domain, set())
        if not vocab:
            continue
        discriminative = {
            token
            for token in vocab
            if token_domain_counts.get(token, 0) <= 1
        }
        overlap_discriminative = request_tokens.intersection(discriminative)
        overlap_all = request_tokens.intersection(vocab)
        # Keep only semantically grounded domain proposals: either at least one
        # domain-specific signal token or enough direct overlap with domain vocabulary.
        if overlap_discriminative or len(overlap_all) >= 2:
            kept.append(domain)
        if len(kept) >= 6:
            break
    return kept


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
        "intent_tags": [str(tag).strip() for tag in task_prep.task_intelligence.intent_tags[:8]],
        "contract_actions": list(task_prep.contract_actions[:8]),
        "available_domains": available_domains,
    }
    prompt = (
        "Select capability domains for planning based on the task brief.\n"
        "Return JSON only in this schema:\n"
        '{ "required_domains": ["domain_a", "domain_b"] }\n'
        "Rules:\n"
        "- Use only available_domains.\n"
        "- Pick 1-6 domains.\n"
        "- Use message + agent_goal + intent_tags as the authoritative scope.\n"
        "- contract_actions can add delivery/workspace domains but must not widen topical scope.\n"
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
    domain_vocab, token_domain_counts = _build_domain_scope_vocab(capabilities)
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

    request_scope_text = " ".join(
        [
            str(request.message or "").strip().lower(),
            str(request.agent_goal or "").strip().lower(),
        ]
    ).strip()
    llm_domains = _infer_domains_with_llm(
        request=request,
        task_prep=task_prep,
        available_domains=available_domains,
    )
    llm_domains = _filter_llm_domains_by_request_scope(
        proposed_domains=llm_domains,
        request_text=request_scope_text,
        baseline_domains=set(domains),
        domain_vocab=domain_vocab,
        token_domain_counts=token_domain_counts,
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
