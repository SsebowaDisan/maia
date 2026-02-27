from __future__ import annotations

import json
import re
from typing import Any

from api.services.agent.llm_runtime import call_json_response, env_bool, sanitize_json_value

EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
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
    delivery_target = ""
    match = EMAIL_RE.search(" ".join([clean_message, clean_goal]))
    if match:
        delivery_target = match.group(1).strip()

    heuristic_facts: list[str] = []
    heuristic_actions: list[str] = ["send_email"] if delivery_target else []

    if not env_bool("MAIA_AGENT_LLM_TASK_CONTRACT_ENABLED", default=True):
        return {
            "objective": clean_rewrite or clean_message,
            "required_outputs": _clean_text_list(deliverables or [], limit=6),
            "required_facts": heuristic_facts[:4],
            "required_actions": list(dict.fromkeys(heuristic_actions))[:6],
            "constraints": _enforce_contract_constraints(constraints or []),
            "delivery_target": delivery_target,
            "missing_requirements": [],
            "success_checks": [
                "All required outputs are generated.",
                "All required facts are supported by evidence.",
            ],
        }

    payload = {
        "message": clean_message,
        "agent_goal": clean_goal,
        "rewritten_task": clean_rewrite,
        "deliverables": _clean_text_list(deliverables or [], limit=6),
        "constraints": _clean_text_list(constraints or [], limit=6),
        "intent_tags": _clean_text_list(intent_tags or [], limit=8, max_item_len=64),
        "conversation_summary": clean_context,
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
        "- required_facts should include mandatory facts the final answer/action must contain.\n"
        "- constraints must include: Never use hardcoded words or keyword lists; rely on LLM semantic understanding.\n"
        "- delivery_target must be empty when unspecified.\n\n"
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
            "required_outputs": _clean_text_list(deliverables or [], limit=6),
            "required_facts": heuristic_facts[:4],
            "required_actions": list(dict.fromkeys(heuristic_actions))[:6],
            "constraints": _enforce_contract_constraints(constraints or []),
            "delivery_target": delivery_target,
            "missing_requirements": [],
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
    clean_target = " ".join(str(response.get("delivery_target") or "").split()).strip()
    if not clean_target:
        clean_target = delivery_target
    return {
        "objective": " ".join(str(response.get("objective") or clean_rewrite or clean_message).split()).strip()[:420],
        "required_outputs": _clean_text_list(response.get("required_outputs"), limit=6),
        "required_facts": _clean_text_list(response.get("required_facts"), limit=6),
        "required_actions": required_actions,
        "constraints": _enforce_contract_constraints(response.get("constraints")),
        "delivery_target": clean_target[:180],
        "missing_requirements": _clean_text_list(response.get("missing_requirements"), limit=6),
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
) -> dict[str, Any]:
    if not env_bool("MAIA_AGENT_LLM_DELIVERY_CHECK_ENABLED", default=True):
        return {
            "ready_for_final_response": True,
            "ready_for_external_actions": True,
            "missing_items": [],
            "reason": "",
            "recommended_remediation": [],
        }
    normalized_contract = _normalize_contract_for_execution(contract)
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
        return {
            "ready_for_final_response": True,
            "ready_for_external_actions": True,
            "missing_items": [],
            "reason": "",
            "recommended_remediation": [],
        }

    def _as_bool(raw: Any, default: bool) -> bool:
        if isinstance(raw, bool):
            return raw
        text = str(raw or "").strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
        return default

    allowed = {str(item).strip() for item in allowed_tool_ids if str(item).strip()}
    remediation_rows: list[dict[str, Any]] = []
    raw_remediation = response.get("recommended_remediation")
    if isinstance(raw_remediation, list):
        for row in raw_remediation:
            if not isinstance(row, dict):
                continue
            tool_id = str(row.get("tool_id") or "").strip()
            if not tool_id or tool_id not in allowed:
                continue
            title = " ".join(str(row.get("title") or tool_id).split()).strip()[:120]
            params = row.get("params")
            remediation_rows.append(
                {
                    "tool_id": tool_id,
                    "title": title or tool_id,
                    "params": dict(params) if isinstance(params, dict) else {},
                }
            )
            if len(remediation_rows) >= 4:
                break
    return {
        "ready_for_final_response": _as_bool(response.get("ready_for_final_response"), True),
        "ready_for_external_actions": _as_bool(response.get("ready_for_external_actions"), True),
        "missing_items": _clean_text_list(response.get("missing_items"), limit=8),
        "reason": " ".join(str(response.get("reason") or "").split()).strip()[:320],
        "recommended_remediation": remediation_rows,
    }


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
