from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from api.services.agent.contract_verification import (
    build_deterministic_contract_check,
    merge_contract_checks,
    parse_llm_contract_check,
)
from api.services.agent.llm_runtime import call_json_response, env_bool, sanitize_json_value

EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
MARKDOWN_LINK_URL_RE = re.compile(r"\[[^\]]+\]\((https?://[^)\s]+)\)", re.IGNORECASE)
NO_HARDCODE_WORDS_CONSTRAINT = (
    "Never use hardcoded words or keyword lists; rely on LLM semantic understanding."
)


def _clean_text_list(raw: Any, *, limit: int, max_item_len: int = 220) -> list[str]:
    if not isinstance(raw, list):
        return []
    rows: list[str] = []
    for item in raw:
        text = " ".join(str(item or "").split()).strip()
        if not text or text in rows:
            continue
        rows.append(text[:max_item_len])
        if len(rows) >= max(1, int(limit)):
            break
    return rows


def _enforce_contract_constraints(raw: Any) -> list[str]:
    rows = _clean_text_list(raw, limit=6)
    if NO_HARDCODE_WORDS_CONSTRAINT in rows:
        return rows[:6]
    return [NO_HARDCODE_WORDS_CONSTRAINT, *rows][:6]


def _extract_first_url(*chunks: str) -> str:
    joined = " ".join(str(chunk or "").strip() for chunk in chunks if str(chunk or "").strip())
    markdown_match = MARKDOWN_LINK_URL_RE.search(joined)
    if markdown_match:
        clean_markdown_url = _normalize_url_candidate(markdown_match.group(1))
        if clean_markdown_url:
            return clean_markdown_url
    match = URL_RE.search(joined)
    if not match:
        return ""
    return _normalize_url_candidate(match.group(0))


def _normalize_url_candidate(raw_url: str) -> str:
    text = str(raw_url or "").strip()
    if not text:
        return ""

    if "](" in text:
        parts = [part.strip() for part in text.split("](") if part.strip()]
        for part in parts:
            normalized_part = _normalize_url_candidate(part)
            if normalized_part:
                return normalized_part
        return ""

    text = text.strip("<>[]()\"'")
    text = text.rstrip(".,;)")
    text = text.rstrip("]")
    if not text.startswith(("http://", "https://")):
        return ""
    parsed = urlparse(text)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return text


def _merge_text_rows(*rows: list[str], limit: int) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for row_list in rows:
        for item in row_list:
            text = " ".join(str(item or "").split()).strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(text)
            if len(merged) >= max(1, int(limit)):
                return merged
    return merged


def _derive_required_actions(*, intent_tags: list[str], delivery_target: str) -> list[str]:
    action_map = {
        "email_delivery": "send_email",
        "contact_form_submission": "submit_contact_form",
        "docs_write": "create_document",
        "sheets_update": "update_sheet",
    }
    actions: list[str] = []
    for tag in intent_tags:
        mapped = action_map.get(str(tag or "").strip().lower())
        if mapped and mapped not in actions:
            actions.append(mapped)
    if delivery_target and "send_email" not in actions:
        actions.append("send_email")
    return actions[:6]


def _align_required_actions_with_intent(
    *,
    required_actions: list[str],
    intent_tags: list[str],
    delivery_target: str,
    target_url: str,
) -> list[str]:
    tags = {
        str(item).strip().lower()
        for item in intent_tags
        if str(item).strip()
    }
    aligned: list[str] = []
    for action in required_actions:
        action_key = str(action).strip().lower()
        if not action_key:
            continue
        if action_key == "send_email":
            if delivery_target or "email_delivery" in tags:
                aligned.append(action_key)
            continue
        if action_key == "submit_contact_form":
            if target_url or "contact_form_submission" in tags:
                aligned.append(action_key)
            continue
        aligned.append(action_key)
    return list(dict.fromkeys(aligned))[:6]


def _classify_missing_requirements(
    *,
    required_actions: list[str],
    required_outputs: list[str],
    required_facts: list[str],
    delivery_target: str,
    target_url: str,
    intent_tags: list[str],
) -> list[str]:
    actions = {str(item).strip() for item in required_actions if str(item).strip()}
    tags = {str(item).strip().lower() for item in intent_tags if str(item).strip()}
    missing: list[str] = []

    needs_delivery_target = "send_email" in actions or "email_delivery" in tags
    if needs_delivery_target and not delivery_target:
        missing.append("Recipient email address for delivery")

    needs_target_url = (
        "submit_contact_form" in actions
        or "contact_form_submission" in tags
        or "web_research" in tags
        or "location_lookup" in tags
    )
    if needs_target_url and not target_url:
        missing.append("Target website URL")

    needs_required_facts = (
        needs_target_url
        or bool(required_outputs)
        or "report_generation" in tags
        or "location_lookup" in tags
    )
    if needs_required_facts and not required_facts:
        missing.append("Required facts to verify in the final answer")

    needs_output_format = (
        "create_document" in actions
        or "update_sheet" in actions
        or "report_generation" in tags
        or "docs_write" in tags
        or "sheets_update" in tags
    )
    if needs_output_format and not required_outputs:
        missing.append("Preferred output format or artifact type")

    return missing[:6]


def _derive_required_facts(
    *,
    message: str,
    agent_goal: str,
    rewritten_task: str,
    intent_tags: list[str],
) -> list[str]:
    joined = " ".join([message, agent_goal, rewritten_task]).lower()
    tags = {str(item).strip().lower() for item in intent_tags if str(item).strip()}
    facts: list[str] = []

    location_hint = (
        "location_lookup" in tags
        or "location" in joined
        or "located" in joined
        or "where is" in joined
        or "headquarter" in joined
        or "headquarters" in joined
        or "address" in joined
    )
    if location_hint:
        facts.append("Company location details (city/country and address if available)")

    if ("web_research" in tags or "report_generation" in tags) and not facts:
        facts.append("Core factual findings required for the requested report")

    return facts[:6]


def _sanitize_missing_requirements(
    *,
    items: list[str],
    delivery_target: str,
    target_url: str,
    required_facts: list[str],
) -> list[str]:
    cleaned = _clean_text_list(items, limit=12)
    fact_rows = [str(item).strip().lower() for item in required_facts if str(item).strip()]
    filtered: list[str] = []
    for row in cleaned:
        lowered = row.lower()
        if delivery_target and ("recipient" in lowered and "email" in lowered):
            continue
        if target_url and (
            "target website url" in lowered
            or "target url" in lowered
            or "website url" in lowered
        ):
            continue
        if fact_rows and ("from analysis" in lowered or "from the analysis" in lowered):
            continue
        if fact_rows and any(fact and (fact in lowered or lowered in fact) for fact in fact_rows):
            continue
        if row in filtered:
            continue
        filtered.append(row)
        if len(filtered) >= 6:
            break
    return filtered


def _normalize_contract_for_execution(contract: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(contract, dict):
        return {
            "constraints": [NO_HARDCODE_WORDS_CONSTRAINT],
            "missing_requirements": [],
            "success_checks": [],
        }
    normalized = dict(contract)
    normalized["constraints"] = _enforce_contract_constraints(contract.get("constraints"))
    normalized["missing_requirements"] = _clean_text_list(contract.get("missing_requirements"), limit=6)
    normalized["success_checks"] = _clean_text_list(contract.get("success_checks"), limit=8)
    return normalized


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
    clean_message = " ".join(str(message or "").split()).strip()
    clean_goal = " ".join(str(agent_goal or "").split()).strip()
    clean_rewrite = " ".join(str(rewritten_task or "").split()).strip()
    clean_context = " ".join(str(conversation_summary or "").split()).strip()
    clean_intent_tags = _clean_text_list(intent_tags or [], limit=8, max_item_len=64)
    delivery_target = ""
    match = EMAIL_RE.search(" ".join([clean_message, clean_goal]))
    if match:
        delivery_target = match.group(1).strip()
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
        "- missing_requirements should include concrete blockers such as recipient, target URL, required facts, or output format.\n\n"
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
    response_missing_requirements = _clean_text_list(response.get("missing_requirements"), limit=6)
    classifier_missing_requirements = _classify_missing_requirements(
        required_actions=required_actions,
        required_outputs=required_outputs,
        required_facts=required_facts,
        delivery_target=clean_target,
        target_url=target_url,
        intent_tags=clean_intent_tags,
    )
    merged_missing_requirements = _merge_text_rows(
        response_missing_requirements,
        classifier_missing_requirements,
        limit=6,
    )
    cleaned_missing_requirements = _sanitize_missing_requirements(
        items=merged_missing_requirements,
        delivery_target=clean_target,
        target_url=target_url,
        required_facts=required_facts,
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
) -> dict[str, Any]:
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
