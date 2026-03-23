from __future__ import annotations

import json
from typing import Any

from api.services.agent import llm_contracts_helpers as _helpers_module
from api.services.agent import llm_contracts_requirements as _requirements_module
from api.services.agent.contract_verification import (
    build_deterministic_contract_check,
    merge_contract_checks,
    parse_llm_contract_check,
)
from api.services.agent.llm_runtime import call_json_response, env_bool, sanitize_json_value

from .llm_contracts_base import (
    NO_HARDCODE_WORDS_CONSTRAINT,
    clean_text_list as _clean_text_list,
    enforce_contract_constraints as _enforce_contract_constraints,
    extract_delivery_target as _extract_delivery_target,
    extract_first_url as _extract_first_url,
)
from .llm_contracts_helpers import (
    align_missing_items_with_contract_semantics as _align_missing_items_with_contract_semantics,
    align_required_actions_with_intent as _align_required_actions_with_intent,
    calibrate_llm_contract_gate as _calibrate_llm_contract_gate,
    derive_required_actions as _derive_required_actions,
    filter_required_facts_for_execution as _filter_required_facts_for_execution,
    reconcile_required_actions_with_llm as _reconcile_required_actions_with_llm,
    suppress_send_email_for_draft_only_scope as _suppress_send_email_for_draft_only_scope,
)
from .llm_contracts_requirements import (
    classify_missing_requirements as _classify_missing_requirements,
    derive_required_facts as _derive_required_facts,
    normalize_contract_for_execution as _normalize_contract_for_execution,
    prune_missing_requirements_with_llm as _prune_missing_requirements_with_llm,
    sanitize_missing_requirements as _sanitize_missing_requirements,
)


def _sync_helper_runtime_refs() -> None:
    _helpers_module.call_json_response = call_json_response
    _helpers_module.env_bool = env_bool
    _requirements_module.call_json_response = call_json_response
    _requirements_module.env_bool = env_bool


def build_task_contract(
    *,
    message: str,
    agent_goal: str | None = None,
    rewritten_task: str = "",
    deliverables: list[str] | None = None,
    constraints: list[str] | None = None,
    intent_tags: list[str] | None = None,
    conversation_summary: str = "",
) -> dict[str, Any]:
    _sync_helper_runtime_refs()
    clean_message = " ".join(str(message or "").split()).strip()
    clean_goal = " ".join(str(agent_goal or "").split()).strip()
    clean_rewrite = " ".join(str(rewritten_task or "").split()).strip()
    clean_context = " ".join(str(conversation_summary or "").split()).strip()
    clean_intent_tags = _clean_text_list(intent_tags or [], limit=8, max_item_len=64)
    clean_intent_tag_set = {str(item).strip().lower() for item in clean_intent_tags if str(item).strip()}
    delivery_target = _extract_delivery_target(clean_message, clean_goal, clean_rewrite)
    target_url = _extract_first_url(clean_message, clean_goal, clean_rewrite)

    heuristic_facts = _derive_required_facts(
        message=clean_message,
        agent_goal=clean_goal,
        rewritten_task=clean_rewrite,
        intent_tags=clean_intent_tags,
    )
    heuristic_actions = _derive_required_actions(
        intent_tags=clean_intent_tags,
        delivery_target=delivery_target,
    )
    heuristic_actions = _align_required_actions_with_intent(
        required_actions=heuristic_actions,
        intent_tags=clean_intent_tags,
        delivery_target=delivery_target,
        target_url=target_url,
    )
    heuristic_actions = _suppress_send_email_for_draft_only_scope(
        required_actions=heuristic_actions,
        message=clean_message,
        agent_goal=clean_goal,
        rewritten_task=clean_rewrite,
    )
    heuristic_facts = _filter_required_facts_for_execution(
        required_facts=heuristic_facts,
        required_actions=heuristic_actions,
        intent_tags=clean_intent_tags,
        message=clean_message,
        agent_goal=clean_goal,
        rewritten_task=clean_rewrite,
        delivery_target=delivery_target,
        target_url=target_url,
        allow_llm=False,
    )
    heuristic_action_set = {str(item).strip().lower() for item in heuristic_actions if str(item).strip()}
    heuristic_outputs = _clean_text_list(deliverables or [], limit=6)
    heuristic_missing_requirements = _classify_missing_requirements(
        required_actions=heuristic_actions,
        required_outputs=heuristic_outputs,
        required_facts=heuristic_facts[:6],
        delivery_target=delivery_target,
        target_url=target_url,
        intent_tags=clean_intent_tags,
    )
    heuristic_missing_requirements = _sanitize_missing_requirements(
        items=heuristic_missing_requirements,
        delivery_target=delivery_target,
        target_url=target_url,
        required_facts=heuristic_facts,
        context_text=" ".join([clean_message, clean_goal, clean_rewrite]),
        requires_target_url=(
            "submit_contact_form" in set(heuristic_actions)
            or "contact_form_submission" in clean_intent_tag_set
        ),
        output_format_optional=(
            "report_generation" in clean_intent_tag_set
            or "docs_write" in clean_intent_tag_set
            or "sheets_update" in clean_intent_tag_set
            or "create_document" in heuristic_action_set
            or "update_sheet" in heuristic_action_set
        ),
        delivery_recipient_required=(
            "send_email" in heuristic_action_set
            or ("email_delivery" in clean_intent_tag_set and "contact_form_submission" not in clean_intent_tag_set)
        ),
    )

    if not env_bool("MAIA_AGENT_LLM_TASK_CONTRACT_ENABLED", default=True):
        return {
            "objective": clean_rewrite or clean_message,
            "required_outputs": heuristic_outputs,
            "required_facts": heuristic_facts[:4],
            "required_actions": list(dict.fromkeys(heuristic_actions))[:6],
            "constraints": _enforce_contract_constraints(constraints or []),
            "delivery_target": delivery_target,
            "missing_requirements": heuristic_missing_requirements,
            "success_checks": [
                "All required outputs are generated.",
                "All required facts are supported by evidence.",
            ],
        }

    payload = {
        "message": clean_message,
        "agent_goal": clean_goal,
        "rewritten_task": clean_rewrite,
        "deliverables": heuristic_outputs,
        "constraints": _clean_text_list(constraints or [], limit=6),
        "intent_tags": clean_intent_tags,
        "conversation_summary": clean_context,
        "target_url_hint": target_url,
    }
    prompt = (
        "Build a strict task contract for an enterprise agent run.\n"
        "Return JSON only:\n"
        '{ "objective":"string", "required_outputs":["..."], "required_facts":["..."], '
        '"required_actions":["send_email|submit_contact_form|post_message|create_document|update_sheet"], '
        '"constraints":["..."], "delivery_target":"string", '
        '"missing_requirements":["..."], "success_checks":["..."] }\n'
        "Rules:\n"
        "- Preserve only user-requested outcomes; do not invent objectives.\n"
        "- Use message/agent_goal as the authoritative scope for required_actions.\n"
        "- conversation_summary is context-only and must not add new required_actions.\n"
        "- Do not include send_email unless email delivery is explicitly requested.\n"
        "- required_facts should include mandatory facts the final answer/action must contain.\n"
        "- constraints must include: Never use hardcoded words or keyword lists; rely on LLM semantic understanding.\n"
        "- delivery_target must be empty when unspecified.\n\n"
        "- If target_url_hint is present, do not request target URL again in missing_requirements.\n"
        "- missing_requirements must contain only non-discoverable user-provided blockers.\n"
        "- Do not ask for details that the agent can discover from website navigation, web research, or attached files.\n"
        "- For website outreach tasks, never require a contact-page URL when a site URL is already present.\n"
        "- missing_requirements should include concrete blockers such as recipient, target URL, required facts, output format, or sender identity details required for external outreach.\n\n"
        "- For email delivery tasks, do not treat tone, preferred length, or style preferences as missing requirements unless the user explicitly requested them.\n"
        "- Do not list collaborator handoff completion, another agent's verification, or internal workflow quality checks as missing requirements.\n"
        "- Missing requirements are only unresolved user-provided inputs or truly non-discoverable blockers.\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    response = call_json_response(
        system_prompt=(
            "You define machine-checkable task contracts for AI agent execution. "
            "Output strict JSON only."
        ),
        user_prompt=prompt,
        temperature=0.0,
        timeout_seconds=12,
        max_tokens=420,
    )
    if not isinstance(response, dict):
        return {
            "objective": clean_rewrite or clean_message,
            "required_outputs": heuristic_outputs,
            "required_facts": heuristic_facts[:4],
            "required_actions": list(dict.fromkeys(heuristic_actions))[:6],
            "constraints": _enforce_contract_constraints(constraints or []),
            "delivery_target": delivery_target,
            "missing_requirements": heuristic_missing_requirements,
            "success_checks": [
                "All required outputs are generated.",
                "All required facts are supported by evidence.",
            ],
        }
    allowed_actions = {"send_email", "submit_contact_form", "post_message", "create_document", "update_sheet"}
    required_actions = [
        value
        for value in _clean_text_list(response.get("required_actions"), limit=6, max_item_len=64)
        if value in allowed_actions
    ]
    required_outputs = _clean_text_list(response.get("required_outputs"), limit=6)
    required_facts = _clean_text_list(response.get("required_facts"), limit=6)
    if not required_facts:
        required_facts = heuristic_facts[:6]
    clean_target = " ".join(str(response.get("delivery_target") or "").split()).strip()
    if not clean_target:
        clean_target = delivery_target
    required_actions = _align_required_actions_with_intent(
        required_actions=required_actions,
        intent_tags=clean_intent_tags,
        delivery_target=clean_target,
        target_url=target_url,
    )
    required_actions = _reconcile_required_actions_with_llm(
        message=clean_message,
        agent_goal=clean_goal,
        rewritten_task=clean_rewrite,
        required_actions=required_actions,
        intent_tags=clean_intent_tags,
        delivery_target=clean_target,
        target_url=target_url,
    )
    required_actions = _align_required_actions_with_intent(
        required_actions=required_actions,
        intent_tags=clean_intent_tags,
        delivery_target=clean_target,
        target_url=target_url,
    )
    required_actions = _suppress_send_email_for_draft_only_scope(
        required_actions=required_actions,
        message=clean_message,
        agent_goal=clean_goal,
        rewritten_task=clean_rewrite,
    )
    required_facts = _filter_required_facts_for_execution(
        required_facts=required_facts,
        required_actions=required_actions,
        intent_tags=clean_intent_tags,
        message=clean_message,
        agent_goal=clean_goal,
        rewritten_task=clean_rewrite,
        delivery_target=clean_target,
        target_url=target_url,
        allow_llm=True,
    )
    required_action_set = {str(item).strip().lower() for item in required_actions if str(item).strip()}
    requires_target_url = (
        "submit_contact_form" in set(required_actions)
        or "contact_form_submission" in clean_intent_tag_set
    )
    output_format_optional = (
        "report_generation" in clean_intent_tag_set
        or "docs_write" in clean_intent_tag_set
        or "sheets_update" in clean_intent_tag_set
        or "create_document" in required_action_set
        or "update_sheet" in required_action_set
    )
    delivery_recipient_required = (
        "send_email" in required_action_set
        or ("email_delivery" in clean_intent_tag_set and "contact_form_submission" not in clean_intent_tag_set)
    )
    classifier_missing_requirements = _classify_missing_requirements(
        required_actions=required_actions,
        required_outputs=required_outputs,
        required_facts=required_facts,
        delivery_target=clean_target,
        target_url=target_url,
        intent_tags=clean_intent_tags,
    )
    llm_missing_requirements = _align_missing_items_with_contract_semantics(
        missing_items=_clean_text_list(response.get("missing_requirements"), limit=8),
        required_actions=required_actions,
        required_facts=required_facts,
    )
    merged_missing_requirements = list(
        dict.fromkeys([*classifier_missing_requirements, *llm_missing_requirements])
    )
    cleaned_missing_requirements = _sanitize_missing_requirements(
        items=merged_missing_requirements,
        delivery_target=clean_target,
        target_url=target_url,
        required_facts=required_facts,
        context_text=" ".join([clean_message, clean_goal, clean_rewrite]),
        requires_target_url=requires_target_url,
        output_format_optional=output_format_optional,
        delivery_recipient_required=delivery_recipient_required,
    )
    cleaned_missing_requirements = _prune_missing_requirements_with_llm(
        items=cleaned_missing_requirements,
        message=clean_message,
        agent_goal=clean_goal,
        rewritten_task=clean_rewrite,
        target_url=target_url,
        delivery_target=clean_target,
        required_actions=required_actions,
        required_facts=required_facts,
        requires_target_url=requires_target_url,
        output_format_optional=output_format_optional,
        delivery_recipient_required=delivery_recipient_required,
    )
    return {
        "objective": " ".join(str(response.get("objective") or clean_rewrite or clean_message).split()).strip()[:420],
        "required_outputs": required_outputs,
        "required_facts": required_facts,
        "required_actions": required_actions,
        "constraints": _enforce_contract_constraints(response.get("constraints")),
        "delivery_target": clean_target[:180],
        "missing_requirements": cleaned_missing_requirements,
        "success_checks": _clean_text_list(response.get("success_checks"), limit=8),
    }


def verify_task_contract_fulfillment(
    *,
    contract: dict[str, Any],
    request_message: str,
    executed_steps: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    report_body: str,
    sources: list[dict[str, Any]],
    allowed_tool_ids: list[str],
    pending_action_tool_id: str = "",
    side_effect_status: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    _sync_helper_runtime_refs()
    normalized_contract = _normalize_contract_for_execution(contract)
    deterministic_check = build_deterministic_contract_check(
        contract=normalized_contract,
        request_message=request_message,
        executed_steps=executed_steps,
        actions=actions,
        report_body=report_body,
        sources=sources,
        allowed_tool_ids=allowed_tool_ids,
        pending_action_tool_id=pending_action_tool_id,
        side_effect_status=side_effect_status,
    )
    clean_pending_action_tool_id = str(pending_action_tool_id or "").strip()
    if clean_pending_action_tool_id:
        return deterministic_check
    if not env_bool("MAIA_AGENT_LLM_DELIVERY_CHECK_ENABLED", default=True):
        return deterministic_check
    payload = {
        "contract": sanitize_json_value(normalized_contract),
        "request_message": " ".join(str(request_message or "").split()).strip()[:480],
        "executed_steps": sanitize_json_value(executed_steps[-20:]),
        "actions": sanitize_json_value(actions[-20:]),
        "report_body": str(report_body or "").strip()[:2200],
        "sources": sanitize_json_value(sources[:20]),
        "allowed_tool_ids": list(dict.fromkeys([str(item).strip() for item in allowed_tool_ids if str(item).strip()]))[
            :40
        ],
        "pending_action_tool_id": clean_pending_action_tool_id,
    }
    prompt = (
        "Check if the run satisfies the task contract before final response or external actions.\n"
        "Return JSON only:\n"
        '{ "ready_for_final_response": true, "ready_for_external_actions": true, "missing_items": ["..."], '
        '"reason":"string", "recommended_remediation":[{"tool_id":"string","title":"string","params":{}}] }\n'
        "Rules:\n"
        "- Use only allowed_tool_ids in recommended_remediation.\n"
        "- Enforce mandatory execution constraint: "
        "Never use hardcoded words or keyword lists; rely on LLM semantic understanding.\n"
        "- If mandatory facts are missing, set both readiness flags to false.\n"
        "- If this mandatory execution constraint is violated, set both readiness flags to false.\n"
        "- Keep reason concise and factual.\n"
        "- If no remediation is needed, return an empty list.\n\n"
        "- If pending_action_tool_id is set, do not mark its mapped required action as missing.\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    response = call_json_response(
        system_prompt=(
            "You are a strict QA gate for enterprise agent delivery. "
            "Output strict JSON only."
        ),
        user_prompt=prompt,
        temperature=0.0,
        timeout_seconds=12,
        max_tokens=520,
    )
    if not isinstance(response, dict):
        return deterministic_check
    llm_check = parse_llm_contract_check(response=response, allowed_tool_ids=allowed_tool_ids)
    llm_check["missing_items"] = _align_missing_items_with_contract_semantics(
        missing_items=_clean_text_list(llm_check.get("missing_items"), limit=8),
        required_actions=_clean_text_list(normalized_contract.get("required_actions"), limit=8, max_item_len=64),
        required_facts=_clean_text_list(normalized_contract.get("required_facts"), limit=8),
    )
    llm_check = _calibrate_llm_contract_gate(
        contract=normalized_contract,
        deterministic_check=deterministic_check,
        llm_check=llm_check,
    )
    return merge_contract_checks(deterministic=deterministic_check, llm=llm_check)


def propose_fact_probe_steps(
    *,
    contract: dict[str, Any],
    request_message: str,
    target_url: str,
    existing_steps: list[dict[str, Any]],
    allowed_tool_ids: list[str],
    max_steps: int = 4,
) -> list[dict[str, Any]]:
    """Use LLM to suggest additional fact-gathering steps for arbitrary user queries."""
    _sync_helper_runtime_refs()
    if not env_bool("MAIA_AGENT_LLM_FACT_PROBE_ENABLED", default=True):
        return []

    allowed = [str(item).strip() for item in allowed_tool_ids if str(item).strip()]
    if not allowed:
        return []

    payload = {
        "contract": sanitize_json_value(contract or {}),
        "request_message": " ".join(str(request_message or "").split()).strip()[:500],
        "target_url": " ".join(str(target_url or "").split()).strip()[:300],
        "existing_steps": sanitize_json_value(existing_steps[:20]),
        "allowed_tool_ids": allowed[:40],
        "max_steps": max(1, min(int(max_steps or 4), 6)),
    }
    prompt = (
        "Suggest additional fact-probing steps to satisfy required facts in this task contract.\n"
        "Return JSON only:\n"
        '{ "steps":[{"tool_id":"string","title":"string","params":{}}] }\n'
        "Rules:\n"
        "- Use ONLY tool_ids from allowed_tool_ids.\n"
        "- Add only missing fact-gathering steps (read/draft), not final delivery actions.\n"
        "- Keep steps concrete and executable.\n"
        "- Include URL params only when strongly implied by target_url or existing evidence.\n"
        "- Return at most max_steps.\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    response = call_json_response(
        system_prompt=(
            "You are an execution planner that improves fact coverage without hardcoded rules. "
            "Output strict JSON only."
        ),
        user_prompt=prompt,
        temperature=0.0,
        timeout_seconds=12,
        max_tokens=520,
    )
    if not isinstance(response, dict):
        return []

    rows = response.get("steps")
    if not isinstance(rows, list):
        return []

    allowed_set = set(allowed)
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        tool_id = str(row.get("tool_id") or "").strip()
        if not tool_id or tool_id not in allowed_set:
            continue
        title = " ".join(str(row.get("title") or tool_id).split()).strip()[:140]
        params = row.get("params")
        params_dict = dict(params) if isinstance(params, dict) else {}
        signature = f"{tool_id}:{json.dumps(sanitize_json_value(params_dict), ensure_ascii=True, sort_keys=True)}"
        if signature in seen:
            continue
        seen.add(signature)
        cleaned.append(
            {
                "tool_id": tool_id,
                "title": title or tool_id,
                "params": params_dict,
            }
        )
        if len(cleaned) >= max(1, min(int(max_steps or 4), 6)):
            break
    return cleaned
