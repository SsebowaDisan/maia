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
DELIVERY_TARGET_HINT_RE = re.compile(
    r"(?:recipient(?:\s+for\s+(?:the\s+)?)?(?:findings|research report|report)?\s*[:=]\s*([^\n.;]+))",
    re.IGNORECASE,
)
DELIVERY_TARGET_ALT_RE = re.compile(
    r"(?:delivery\s+target\s*[:=]\s*([^\n.;]+))",
    re.IGNORECASE,
)
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


def _normalize_for_match(text: str) -> str:
    return " ".join(str(text or "").lower().split()).strip()


def _align_missing_items_with_contract_semantics(
    *,
    missing_items: list[str],
    required_actions: list[str],
    required_facts: list[str],
) -> list[str]:
    cleaned_missing = _clean_text_list(missing_items, limit=8)
    if not cleaned_missing:
        return []
    cleaned_actions = _clean_text_list(required_actions, limit=8, max_item_len=64)
    cleaned_facts = _clean_text_list(required_facts, limit=8)
    if not cleaned_actions and not cleaned_facts:
        return []
    normalized_required_actions = {
        _normalize_for_match(item)
        for item in cleaned_actions
        if _normalize_for_match(item)
    }
    normalized_required_facts = {
        _normalize_for_match(item)
        for item in cleaned_facts
        if _normalize_for_match(item)
    }

    def _schema_fallback_alignment() -> list[str]:
        aligned_rows: list[str] = []
        allow_generic_contact_row = "submit_contact_form" in normalized_required_actions
        for row in cleaned_missing:
            normalized_row = _normalize_for_match(row)
            if not normalized_row:
                continue
            if any(action in normalized_row for action in normalized_required_actions):
                aligned_rows.append(row)
                continue
            if any(fact in normalized_row for fact in normalized_required_facts):
                aligned_rows.append(row)
                continue
            if allow_generic_contact_row:
                aligned_rows.append(row)
        return _clean_text_list(aligned_rows, limit=8)

    if not env_bool("MAIA_AGENT_LLM_MISSING_ALIGNMENT_ENABLED", default=True):
        return _schema_fallback_alignment()

    payload = {
        "missing_items": cleaned_missing,
        "required_actions": cleaned_actions,
        "required_facts": cleaned_facts,
    }
    try:
        response = call_json_response(
            system_prompt=(
                "You determine whether missing contract items are semantically aligned to required actions/facts. "
                "Return strict JSON only."
            ),
            user_prompt=(
                "Return JSON only:\n"
                '{ "keep_indexes":[0,1], "reason":"..." }\n'
                "Rules:\n"
                "- Keep an item only if it semantically maps to at least one required action or required fact.\n"
                "- Never use hardcoded keyword matching.\n"
                "- Do not invent new items.\n"
                "- Use only indexes from missing_items.\n\n"
                f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
            ),
            temperature=0.0,
            timeout_seconds=8,
            max_tokens=220,
        )
    except Exception:
        return _schema_fallback_alignment()
    if not isinstance(response, dict):
        return _schema_fallback_alignment()
    raw_indexes = response.get("keep_indexes")
    if not isinstance(raw_indexes, list):
        return _schema_fallback_alignment()
    kept: list[str] = []
    for raw in raw_indexes[:12]:
        try:
            idx = int(raw)
        except Exception:
            continue
        if idx < 0 or idx >= len(cleaned_missing):
            continue
        value = cleaned_missing[idx]
        if value in kept:
            continue
        kept.append(value)
        if len(kept) >= 8:
            break
    return kept if kept else _schema_fallback_alignment()


def _llm_block_is_actionable(*, contract: dict[str, Any], llm_check: dict[str, Any]) -> bool:
    missing_items = _clean_text_list(llm_check.get("missing_items"), limit=8)
    if not missing_items:
        return False
    required_actions = _clean_text_list(contract.get("required_actions"), limit=8, max_item_len=64)
    required_facts = _clean_text_list(contract.get("required_facts"), limit=8)
    aligned = _align_missing_items_with_contract_semantics(
        missing_items=missing_items,
        required_actions=required_actions,
        required_facts=required_facts,
    )
    return bool(aligned)


def _calibrate_llm_contract_gate(
    *,
    contract: dict[str, Any],
    deterministic_check: dict[str, Any],
    llm_check: dict[str, Any],
) -> dict[str, Any]:
    deterministic_ready = bool(deterministic_check.get("ready_for_final_response")) and bool(
        deterministic_check.get("ready_for_external_actions")
    )
    llm_ready = bool(llm_check.get("ready_for_final_response")) and bool(llm_check.get("ready_for_external_actions"))
    if deterministic_ready and not llm_ready and not _llm_block_is_actionable(contract=contract, llm_check=llm_check):
        return {
            "ready_for_final_response": True,
            "ready_for_external_actions": True,
            "missing_items": [],
            "reason": "",
            "recommended_remediation": [],
        }
    return llm_check


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


def _extract_delivery_target(*chunks: str) -> str:
    joined = "\n".join(str(chunk or "").strip() for chunk in chunks if str(chunk or "").strip())
    if not joined:
        return ""

    match = EMAIL_RE.search(joined)
    if match:
        return match.group(1).strip()

    for pattern in (DELIVERY_TARGET_HINT_RE, DELIVERY_TARGET_ALT_RE):
        hint_match = pattern.search(joined)
        if not hint_match:
            continue
        candidate = " ".join(str(hint_match.group(1) or "").split()).strip(" .,;:")
        if candidate:
            return candidate[:180]
    return ""


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
        if action_key == "post_message" and "contact_form_submission" in tags:
            # Normalize generic "post message" into the concrete website outreach
            # action when contact-form intent is active.
            action_key = "submit_contact_form"
        if action_key == "send_email":
            email_tag_requested = "email_delivery" in tags
            contact_form_requested = "contact_form_submission" in tags
            if (
                delivery_target
                or (email_tag_requested and not contact_form_requested)
            ):
                aligned.append(action_key)
            continue
        if action_key == "submit_contact_form":
            if target_url or "contact_form_submission" in tags:
                aligned.append(action_key)
            continue
        aligned.append(action_key)
    return list(dict.fromkeys(aligned))[:6]


def _reconcile_required_actions_with_llm(
    *,
    message: str,
    agent_goal: str,
    rewritten_task: str,
    required_actions: list[str],
    intent_tags: list[str],
    delivery_target: str,
    target_url: str,
) -> list[str]:
    cleaned_actions = _clean_text_list(required_actions, limit=6, max_item_len=64)
    if not env_bool("MAIA_AGENT_LLM_ACTION_RECONCILE_ENABLED", default=True):
        return cleaned_actions
    payload = {
        "message": message[:500],
        "agent_goal": agent_goal[:420],
        "rewritten_task": rewritten_task[:420],
        "intent_tags": _clean_text_list(intent_tags, limit=8, max_item_len=64),
        "delivery_target": delivery_target[:180],
        "target_url": target_url[:260],
        "current_required_actions": cleaned_actions,
        "allowed_actions": [
            "send_email",
            "submit_contact_form",
            "post_message",
            "create_document",
            "update_sheet",
        ],
    }
    try:
        response = call_json_response(
            system_prompt=(
                "You validate required execution actions for an AI agent task contract. "
                "Return strict JSON only."
            ),
            user_prompt=(
                "Return JSON only:\n"
                '{ "required_actions":["send_email|submit_contact_form|post_message|create_document|update_sheet"], '
                '"reason":"..." }\n'
                "Rules:\n"
                "- Keep only actions explicitly required by the user request.\n"
                "- For website outreach via on-site interaction, use submit_contact_form.\n"
                "- Do not invent delivery channels not requested by the user.\n"
                "- Never rely on hardcoded keyword matching.\n\n"
                f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
            ),
            temperature=0.0,
            timeout_seconds=8,
            max_tokens=220,
        )
    except Exception:
        return cleaned_actions
    if not isinstance(response, dict):
        return cleaned_actions
    raw_actions = _clean_text_list(response.get("required_actions"), limit=6, max_item_len=64)
    allowed_actions = {"send_email", "submit_contact_form", "post_message", "create_document", "update_sheet"}
    llm_actions = [item for item in raw_actions if item in allowed_actions]
    if not llm_actions:
        return cleaned_actions
    merged = list(dict.fromkeys([*cleaned_actions, *llm_actions]))[:6]
    return merged


def _filter_required_facts_for_execution(
    *,
    required_facts: list[str],
    required_actions: list[str],
    intent_tags: list[str],
    message: str,
    agent_goal: str,
    rewritten_task: str,
    delivery_target: str,
    target_url: str,
    allow_llm: bool = True,
) -> list[str]:
    rows = _clean_text_list(required_facts, limit=6)
    if not rows:
        return []

    def _fallback() -> list[str]:
        action_set = {
            str(item).strip().lower()
            for item in required_actions
            if str(item).strip()
        }
        normalized_target = _normalize_for_match(delivery_target)
        filtered: list[str] = []
        for row in rows:
            normalized_row = _normalize_for_match(row)
            if not normalized_row:
                continue
            if normalized_target and normalized_target in normalized_row:
                continue
            if "send_email" in action_set and EMAIL_RE.search(row):
                continue
            filtered.append(row)
            if len(filtered) >= 6:
                break
        return filtered

    if not allow_llm:
        return _fallback()
    if not env_bool("MAIA_AGENT_LLM_REQUIRED_FACT_FILTER_ENABLED", default=True):
        return _fallback()

    payload = {
        "message": message[:500],
        "agent_goal": agent_goal[:420],
        "rewritten_task": rewritten_task[:420],
        "required_facts": rows,
        "required_actions": _clean_text_list(required_actions, limit=6, max_item_len=64),
        "intent_tags": _clean_text_list(intent_tags, limit=8, max_item_len=64),
        "delivery_target": delivery_target[:180],
        "target_url": target_url[:260],
    }
    try:
        response = call_json_response(
            system_prompt=(
                "You filter task-contract required facts to keep only evidence-bearing facts. "
                "Return strict JSON only."
            ),
            user_prompt=(
                "Return JSON only:\n"
                '{ "keep_indexes":[0,1], "reason":"..." }\n'
                "Rules:\n"
                "- Keep only facts that must be verified from execution evidence.\n"
                "- Remove delivery identity, routing target, and action precondition slots.\n"
                "- Never rely on hardcoded keyword matching.\n"
                "- Use only indexes from required_facts.\n\n"
                f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
            ),
            temperature=0.0,
            timeout_seconds=8,
            max_tokens=220,
        )
    except Exception:
        return _fallback()
    if not isinstance(response, dict):
        return _fallback()
    raw_indexes = response.get("keep_indexes")
    if not isinstance(raw_indexes, list):
        return _fallback()
    kept: list[str] = []
    for raw in raw_indexes[:12]:
        try:
            index = int(raw)
        except Exception:
            continue
        if index < 0 or index >= len(rows):
            continue
        value = rows[index]
        if value in kept:
            continue
        kept.append(value)
        if len(kept) >= 6:
            break
    return kept


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

    needs_delivery_target = "send_email" in actions or (
        "email_delivery" in tags and "contact_form_submission" not in tags
    )
    has_delivery_email = bool(EMAIL_RE.search(delivery_target))
    if needs_delivery_target and not has_delivery_email:
        missing.append("Recipient email address for delivery")

    needs_target_url = (
        "submit_contact_form" in actions
        or "contact_form_submission" in tags
    )
    if needs_target_url and not target_url:
        missing.append("Target website URL")

    needs_required_facts = bool(required_outputs) or "report_generation" in tags or "location_lookup" in tags
    if needs_required_facts and not required_facts:
        missing.append("Required facts to verify in the final answer")

    needs_output_format = (
        "create_document" in actions
        or "update_sheet" in actions
    )
    # For report/docs/sheets intents we can safely default to existing templates
    # and tracker formats, so output format is optional by default.
    has_defaultable_output = (
        "report_generation" in tags
        or "docs_write" in tags
        or "sheets_update" in tags
    )
    if needs_output_format and not required_outputs and not has_defaultable_output:
        missing.append("Preferred output format or artifact type")

    return missing[:6]


def _derive_required_facts(
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

    if "report_generation" in tags and not facts:
        facts.append("Core factual findings required for the requested report")

    return facts[:6]


def _sanitize_missing_requirements(
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
    cleaned = _clean_text_list(items, limit=12)
    fact_rows = {
        _normalize_for_match(str(item))
        for item in required_facts
        if str(item).strip()
    }
    context_rows = {
        _normalize_for_match(item)
        for item in [context_text, target_url, delivery_target, *required_facts]
        if _normalize_for_match(item)
    }
    normalized_context = _normalize_for_match(context_text)
    filtered: list[str] = []
    for row in cleaned:
        normalized_row = _normalize_for_match(row)
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
    _ = (
        requires_target_url,
        output_format_optional,
        delivery_recipient_required,
    )
    return filtered


def _prune_missing_requirements_with_llm(
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
    rows = _clean_text_list(items, limit=6)
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
