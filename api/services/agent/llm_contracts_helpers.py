from __future__ import annotations

import json
from typing import Any

from api.services.agent.llm_runtime import call_json_response, env_bool

from .llm_contracts_base import (
    EMAIL_RE,
    clean_text_list,
    normalize_for_match,
    normalize_url_candidate,
    scope_filter_required_facts,
    tokenize_for_scope,
)


def align_missing_items_with_contract_semantics(
    *,
    missing_items: list[str],
    required_actions: list[str],
    required_facts: list[str],
) -> list[str]:
    cleaned_missing = clean_text_list(missing_items, limit=8)
    if not cleaned_missing:
        return []
    cleaned_actions = clean_text_list(required_actions, limit=8, max_item_len=64)
    cleaned_facts = clean_text_list(required_facts, limit=8)
    if not cleaned_actions and not cleaned_facts:
        return []
    normalized_required_actions = {
        normalize_for_match(item)
        for item in cleaned_actions
        if normalize_for_match(item)
    }
    normalized_required_facts = {
        normalize_for_match(item)
        for item in cleaned_facts
        if normalize_for_match(item)
    }

    def _schema_fallback_alignment() -> list[str]:
        aligned_rows: list[str] = []
        allow_generic_contact_row = "submit_contact_form" in normalized_required_actions
        for row in cleaned_missing:
            normalized_row = normalize_for_match(row)
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
        return clean_text_list(aligned_rows, limit=8)

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


def llm_block_is_actionable(*, contract: dict[str, Any], llm_check: dict[str, Any]) -> bool:
    missing_items = clean_text_list(llm_check.get("missing_items"), limit=8)
    if not missing_items:
        return False
    required_actions = clean_text_list(contract.get("required_actions"), limit=8, max_item_len=64)
    required_facts = clean_text_list(contract.get("required_facts"), limit=8)
    aligned = align_missing_items_with_contract_semantics(
        missing_items=missing_items,
        required_actions=required_actions,
        required_facts=required_facts,
    )
    return bool(aligned)


def calibrate_llm_contract_gate(
    *,
    contract: dict[str, Any],
    deterministic_check: dict[str, Any],
    llm_check: dict[str, Any],
) -> dict[str, Any]:
    deterministic_ready = bool(deterministic_check.get("ready_for_final_response")) and bool(
        deterministic_check.get("ready_for_external_actions")
    )
    llm_ready = bool(llm_check.get("ready_for_final_response")) and bool(llm_check.get("ready_for_external_actions"))
    if deterministic_ready and not llm_ready and not llm_block_is_actionable(contract=contract, llm_check=llm_check):
        return {
            "ready_for_final_response": True,
            "ready_for_external_actions": True,
            "missing_items": [],
            "reason": "",
            "recommended_remediation": [],
        }
    return llm_check


def derive_required_actions(*, intent_tags: list[str], delivery_target: str) -> list[str]:
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


def align_required_actions_with_intent(
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
            action_key = "submit_contact_form"
        if action_key == "send_email":
            email_tag_requested = "email_delivery" in tags
            contact_form_requested = "contact_form_submission" in tags
            if delivery_target or (email_tag_requested and not contact_form_requested):
                aligned.append(action_key)
            continue
        if action_key == "submit_contact_form":
            if target_url or "contact_form_submission" in tags:
                aligned.append(action_key)
            continue
        aligned.append(action_key)
    return list(dict.fromkeys(aligned))[:6]


def reconcile_required_actions_with_llm(
    *,
    message: str,
    agent_goal: str,
    rewritten_task: str,
    required_actions: list[str],
    intent_tags: list[str],
    delivery_target: str,
    target_url: str,
) -> list[str]:
    cleaned_actions = clean_text_list(required_actions, limit=6, max_item_len=64)
    if not env_bool("MAIA_AGENT_LLM_ACTION_RECONCILE_ENABLED", default=True):
        return cleaned_actions
    payload = {
        "message": message[:500],
        "agent_goal": agent_goal[:420],
        "rewritten_task": rewritten_task[:420],
        "intent_tags": clean_text_list(intent_tags, limit=8, max_item_len=64),
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
    raw_actions = clean_text_list(response.get("required_actions"), limit=6, max_item_len=64)
    allowed_actions = {"send_email", "submit_contact_form", "post_message", "create_document", "update_sheet"}
    llm_actions = [item for item in raw_actions if item in allowed_actions]
    if not llm_actions:
        return cleaned_actions
    merged = list(dict.fromkeys([*cleaned_actions, *llm_actions]))[:6]
    return merged


def filter_required_facts_for_execution(
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
    rows = clean_text_list(required_facts, limit=6)
    if not rows:
        return []
    action_set = {
        str(item).strip().lower()
        for item in required_actions
        if str(item).strip()
    }
    tag_set = {
        str(item).strip().lower()
        for item in intent_tags
        if str(item).strip()
    }
    normalized_target_url = normalize_url_candidate(target_url)
    request_scope_tokens = tokenize_for_scope(" ".join([message, agent_goal]))

    def _target_bound(candidate_rows: list[str]) -> bool:
        return bool(normalized_target_url) and bool(candidate_rows) and all(
            normalized_target_url in str(row or "")
            for row in candidate_rows
        )

    def _finalize(candidate_rows: list[str]) -> list[str]:
        scoped_rows = scope_filter_required_facts(
            rows=candidate_rows,
            message=message,
            agent_goal=agent_goal,
        )

        def _is_low_alignment_row(row: str) -> bool:
            fact_tokens = tokenize_for_scope(row)
            if not fact_tokens:
                return True
            if not request_scope_tokens:
                return True
            overlap = len(fact_tokens.intersection(request_scope_tokens))
            ratio = overlap / max(1, len(fact_tokens))
            return ratio < 0.75

        low_alignment_rows = bool(scoped_rows) and all(
            _is_low_alignment_row(str(row or ""))
            for row in scoped_rows
        )
        if (
            "report_generation" in tag_set
            and "location_lookup" not in tag_set
            and "contact_form_submission" not in tag_set
            and (
                "send_email" in action_set
                or "email_delivery" in tag_set
                or _target_bound(scoped_rows)
            )
            and len(scoped_rows) <= 2
            and low_alignment_rows
        ):
            return []
        return scoped_rows[:6]

    def _fallback() -> list[str]:
        normalized_target = normalize_for_match(delivery_target)
        filtered: list[str] = []
        for row in rows:
            normalized_row = normalize_for_match(row)
            if not normalized_row:
                continue
            if normalized_target and normalized_target in normalized_row:
                continue
            if "send_email" in action_set and EMAIL_RE.search(row):
                continue
            filtered.append(row)
            if len(filtered) >= 6:
                break
        return _finalize(filtered)

    if not allow_llm:
        return _fallback()
    if not env_bool("MAIA_AGENT_LLM_REQUIRED_FACT_FILTER_ENABLED", default=True):
        return _fallback()

    payload = {
        "message": message[:500],
        "agent_goal": agent_goal[:420],
        "rewritten_task": rewritten_task[:420],
        "required_facts": rows,
        "required_actions": clean_text_list(required_actions, limit=6, max_item_len=64),
        "intent_tags": clean_text_list(intent_tags, limit=8, max_item_len=64),
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
    return _finalize(kept)
