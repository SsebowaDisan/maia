from __future__ import annotations

import json
from typing import Any

from api.services.agent.llm_runtime import call_json_response, env_bool

from .llm_contracts_base import (
    EMAIL_RE,
    clean_text_list,
    enforce_contract_constraints,
    normalize_for_match,
)


def classify_missing_requirements(
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

    needs_delivery_target = "send_email" in actions or (
        "email_delivery" in tags and "contact_form_submission" not in tags
    )
    has_delivery_email = bool(EMAIL_RE.search(delivery_target))
    if needs_delivery_target and not has_delivery_email:
        missing.append("Recipient email address for delivery")

    needs_target_url = "submit_contact_form" in actions or "contact_form_submission" in tags
    if needs_target_url and not target_url:
        missing.append("Target website URL")

    needs_required_facts = "location_lookup" in tags
    if needs_required_facts and not required_facts:
        missing.append("Required facts to verify in the final answer")

    needs_output_format = "create_document" in actions or "update_sheet" in actions
    has_defaultable_output = (
        "report_generation" in tags
        or "docs_write" in tags
        or "sheets_update" in tags
    )
    if needs_output_format and not required_outputs and not has_defaultable_output:
        missing.append("Preferred output format or artifact type")

    return missing[:6]


def derive_required_facts(
    *,
    message: str,
    agent_goal: str,
    rewritten_task: str,
    intent_tags: list[str],
) -> list[str]:
    _ = (message, agent_goal, rewritten_task)
    tags = {str(item).strip().lower() for item in intent_tags if str(item).strip()}
    facts: list[str] = []

    if "location_lookup" in tags:
        facts.append("Company location details (city/country and address if available)")

    return facts[:6]


def sanitize_missing_requirements(
    *,
    items: list[str],
    delivery_target: str,
    target_url: str,
    required_facts: list[str],
    context_text: str = "",
    requires_target_url: bool = False,
    output_format_optional: bool = False,
    delivery_recipient_required: bool = False,
) -> list[str]:
    cleaned = clean_text_list(items, limit=12)
    fact_rows = {
        normalize_for_match(str(item))
        for item in required_facts
        if str(item).strip()
    }
    context_rows = {
        normalize_for_match(item)
        for item in [context_text, target_url, delivery_target, *required_facts]
        if normalize_for_match(item)
    }
    normalized_context = normalize_for_match(context_text)
    filtered: list[str] = []
    for row in cleaned:
        normalized_row = normalize_for_match(row)
        if not normalized_row:
            continue
        if normalized_context and normalized_row in normalized_context:
            continue
        if normalized_row in context_rows:
            continue
        if normalized_row in fact_rows:
            continue
        if row in filtered:
            continue
        filtered.append(row)
        if len(filtered) >= 6:
            break
    _ = (requires_target_url, output_format_optional, delivery_recipient_required)
    return filtered


def prune_missing_requirements_with_llm(
    *,
    items: list[str],
    message: str,
    agent_goal: str,
    rewritten_task: str,
    target_url: str,
    delivery_target: str,
    required_actions: list[str],
    required_facts: list[str],
    requires_target_url: bool = False,
    output_format_optional: bool = False,
    delivery_recipient_required: bool = False,
) -> list[str]:
    rows = clean_text_list(items, limit=6)
    if not rows:
        return []
    if not env_bool("MAIA_AGENT_LLM_MISSING_PRUNE_ENABLED", default=True):
        return rows
    payload = {
        "message": message[:480],
        "agent_goal": agent_goal[:480],
        "rewritten_task": rewritten_task[:480],
        "target_url": target_url[:240],
        "delivery_target": delivery_target[:180],
        "required_actions": required_actions[:6],
        "required_facts": required_facts[:6],
        "missing_requirements": rows,
        "slot_requirements": {
            "requires_target_url": bool(requires_target_url),
            "output_format_optional": bool(output_format_optional),
            "delivery_recipient_required": bool(delivery_recipient_required),
        },
    }
    try:
        response = call_json_response(
            system_prompt=(
                "You validate whether candidate missing-requirement blockers are still unresolved. "
                "Return strict JSON only."
            ),
            user_prompt=(
                "Keep only missing requirements that are still unresolved blockers.\n"
                "Return JSON only:\n"
                '{ "keep_indexes":[0,1], "reason":"..." }\n'
                "Rules:\n"
                "- Use slot_requirements to determine if URL/recipient/output-format blockers are required.\n"
                "- If target_url is present and requires_target_url=false, URL blockers are resolved.\n"
                "- If delivery_recipient_required=false, recipient blockers are resolved.\n"
                "- If delivery_target contains a valid recipient email, recipient-email blockers are resolved.\n"
                "- If output_format_optional=true, generic output-format blockers are resolved.\n"
                "- Do not keep tone/length/style preference blockers unless the user explicitly requested them.\n"
                "- Do not keep blockers about another agent's handoff, verification, or internal workflow completion.\n"
                "- Do not invent new missing blockers.\n"
                "- Use only indexes from the provided missing_requirements list.\n\n"
                f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
            ),
            temperature=0.0,
            timeout_seconds=8,
            max_tokens=220,
        )
    except Exception:
        return rows
    if not isinstance(response, dict):
        return rows
    raw_indexes = response.get("keep_indexes")
    if not isinstance(raw_indexes, list):
        return rows
    kept: list[str] = []
    for raw in raw_indexes[:12]:
        try:
            idx = int(raw)
        except Exception:
            continue
        if idx < 0 or idx >= len(rows):
            continue
        value = rows[idx]
        if value in kept:
            continue
        kept.append(value)
        if len(kept) >= 6:
            break
    return kept if kept else []


def normalize_contract_for_execution(contract: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(contract, dict):
        return {
            "constraints": [enforce_contract_constraints([])[0]],
            "missing_requirements": [],
            "success_checks": [],
        }
    normalized = dict(contract)
    normalized["constraints"] = enforce_contract_constraints(contract.get("constraints"))
    normalized["missing_requirements"] = clean_text_list(contract.get("missing_requirements"), limit=6)
    normalized["success_checks"] = clean_text_list(contract.get("success_checks"), limit=8)
    return normalized
