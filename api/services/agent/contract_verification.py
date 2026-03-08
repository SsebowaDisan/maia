from __future__ import annotations

import json
from typing import Any

from api.services.agent.llm_runtime import call_json_response

from .contract_verification_support import (
    ACTION_TOOL_IDS,
    append_remediation,
    clean_text_list,
    collect_evidence_texts,
    extract_first_url,
    fact_missing,
    filter_required_facts_for_coverage,
    host_from_url,
    normalize_side_effect_status,
    semantic_missing_required_facts,
    successful_action_tool_ids,
)


def build_deterministic_contract_check(
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
    required_actions = clean_text_list(contract.get("required_actions"), limit=6, max_item_len=64)
    clean_pending_action_tool_id = str(pending_action_tool_id or "").strip()
    side_effect_rows = (
        {
            " ".join(str(key or "").split()).strip().lower(): dict(value)
            for key, value in side_effect_status.items()
            if isinstance(value, dict) and " ".join(str(key or "").split()).strip()
        }
        if isinstance(side_effect_status, dict)
        else {}
    )
    delivery_target = " ".join(str(contract.get("delivery_target") or "").split()).strip()
    required_facts = filter_required_facts_for_coverage(
        required_facts=clean_text_list(contract.get("required_facts"), limit=6),
        required_actions=required_actions,
        delivery_target=delivery_target,
        request_message=request_message,
        call_json_response_fn=call_json_response,
    )
    target_url = extract_first_url(
        request_message,
        " ".join(str(source.get("url") or "").strip() for source in sources[:8]),
    )
    target_host = host_from_url(target_url)
    allowed_set = {str(item).strip() for item in allowed_tool_ids if str(item).strip()}
    missing_items: list[str] = []
    reason_parts: list[str] = []
    remediation: list[dict[str, Any]] = []
    external_action_keys = ("send_email", "submit_contact_form", "post_message")
    pending_external_action = any(
        action_key in required_actions and clean_pending_action_tool_id in ACTION_TOOL_IDS.get(action_key, set())
        for action_key in external_action_keys
    )
    evidence_rows = collect_evidence_texts(
        request_message=request_message,
        executed_steps=executed_steps,
        actions=actions,
        report_body=report_body,
        sources=sources,
    )

    semantic_missing_facts = semantic_missing_required_facts(
        required_facts=required_facts,
        evidence_rows=evidence_rows,
        call_json_response_fn=call_json_response,
    )
    lexical_missing_facts = [
        fact
        for fact in required_facts
        if fact_missing(fact=fact, evidence_rows=evidence_rows)
    ]
    missing_facts: list[str]
    if isinstance(semantic_missing_facts, list):
        semantic_set = {str(item).strip() for item in semantic_missing_facts if str(item).strip()}
        if semantic_set:
            missing_facts = [fact for fact in lexical_missing_facts if fact in semantic_set][:6]
        else:
            missing_facts = lexical_missing_facts[:6]
    else:
        missing_facts = lexical_missing_facts[:6]
    if not pending_external_action:
        for fact in missing_facts[:6]:
            missing_items.append(f"Unverified required fact: {fact}")
        if missing_facts:
            reason_parts.append("Required facts are not yet verified with evidence.")
            if target_url:
                append_remediation(
                    target=remediation,
                    tool_id="browser.playwright.inspect",
                    title="Inspect target website for missing required facts",
                    params={"url": target_url},
                    allowed_tool_ids=allowed_set,
                )
            append_remediation(
                target=remediation,
                tool_id="marketing.web_research",
                title="Research missing required facts",
                params={
                    "query": (
                        f"site:{target_host} " + ("; ".join(missing_facts[:3]) or request_message)
                        if target_host
                        else ("; ".join(missing_facts[:3]) or request_message)
                    ),
                    "domain_scope": [target_host] if target_host else [],
                    "domain_scope_mode": "strict" if target_host else "off",
                    "target_url": target_url,
                },
                allowed_tool_ids=allowed_set,
            )

    successful_tools = successful_action_tool_ids(actions)
    for action in required_actions:
        action_key = str(action).strip()
        if not action_key:
            continue
        mapped_tools = ACTION_TOOL_IDS.get(action_key, set())
        side_effect_row = side_effect_rows.get(action_key, {})
        side_effect_state = normalize_side_effect_status(side_effect_row.get("status"))
        if action_key == "send_email" and not delivery_target:
            missing_items.append("Missing delivery target for required action: send_email")
            reason_parts.append("Email delivery is requested but recipient is missing.")
            continue
        if clean_pending_action_tool_id and clean_pending_action_tool_id in mapped_tools:
            continue
        if side_effect_state == "completed":
            continue
        if side_effect_state in {"failed", "blocked", "skipped"}:
            missing_items.append(f"External action failed: {action_key} ({side_effect_state})")
            reason_parts.append(
                f"Required external action '{action_key}' ended with status {side_effect_state}."
            )
            if action_key == "send_email":
                append_remediation(
                    target=remediation,
                    tool_id="gmail.draft",
                    title="Prepare email retry draft after failed delivery",
                    params={"to": delivery_target} if delivery_target else {},
                    allowed_tool_ids=allowed_set,
                )
            continue
        if mapped_tools and successful_tools.intersection(mapped_tools):
            continue
        if action_key in {"send_email", "submit_contact_form", "post_message"}:
            missing_items.append(f"Required action not completed: {action_key}")
            reason_parts.append(f"Required external action '{action_key}' is not completed.")
            if action_key == "send_email":
                append_remediation(
                    target=remediation,
                    tool_id="gmail.draft",
                    title="Draft email delivery content",
                    params={"to": delivery_target} if delivery_target else {},
                    allowed_tool_ids=allowed_set,
                )
            if action_key == "submit_contact_form" and target_url:
                append_remediation(
                    target=remediation,
                    tool_id="browser.playwright.inspect",
                    title="Open target website to locate contact form",
                    params={"url": target_url},
                    allowed_tool_ids=allowed_set,
                )

    missing_items = clean_text_list(missing_items, limit=8, max_item_len=220)
    reason = " ".join(reason_parts).strip()[:320]
    is_ready = not missing_items
    return {
        "ready_for_final_response": is_ready,
        "ready_for_external_actions": is_ready,
        "missing_items": missing_items,
        "reason": reason,
        "recommended_remediation": remediation[:4],
    }


def parse_llm_contract_check(
    *,
    response: dict[str, Any],
    allowed_tool_ids: list[str],
) -> dict[str, Any]:
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
        "missing_items": clean_text_list(response.get("missing_items"), limit=8),
        "reason": " ".join(str(response.get("reason") or "").split()).strip()[:320],
        "recommended_remediation": remediation_rows,
    }


def merge_contract_checks(*, deterministic: dict[str, Any], llm: dict[str, Any]) -> dict[str, Any]:
    merged_missing = clean_text_list(
        [*(deterministic.get("missing_items") or []), *(llm.get("missing_items") or [])],
        limit=8,
    )
    merged_reason_parts = [
        " ".join(str(deterministic.get("reason") or "").split()).strip(),
        " ".join(str(llm.get("reason") or "").split()).strip(),
    ]
    merged_reason = " ".join([item for item in merged_reason_parts if item])[:320]
    remediation_rows: list[dict[str, Any]] = []
    for row in [
        *(deterministic.get("recommended_remediation") or []),
        *(llm.get("recommended_remediation") or []),
    ]:
        if not isinstance(row, dict):
            continue
        tool_id = str(row.get("tool_id") or "").strip()
        if not tool_id:
            continue
        params = row.get("params")
        title = " ".join(str(row.get("title") or tool_id).split()).strip()[:120]
        append_remediation(
            target=remediation_rows,
            tool_id=tool_id,
            title=title or tool_id,
            params=dict(params) if isinstance(params, dict) else {},
            allowed_tool_ids={tool_id},
        )
        if len(remediation_rows) >= 4:
            break
    return {
        "ready_for_final_response": bool(deterministic.get("ready_for_final_response")) and bool(
            llm.get("ready_for_final_response")
        ),
        "ready_for_external_actions": bool(deterministic.get("ready_for_external_actions")) and bool(
            llm.get("ready_for_external_actions")
        ),
        "missing_items": merged_missing,
        "reason": merged_reason,
        "recommended_remediation": remediation_rows,
    }
