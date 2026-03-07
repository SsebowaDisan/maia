from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from api.services.agent.llm_runtime import call_json_response, env_bool

URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
STOPWORDS = {
    "about",
    "after",
    "also",
    "been",
    "being",
    "from",
    "have",
    "into",
    "more",
    "most",
    "that",
    "their",
    "there",
    "these",
    "this",
    "those",
    "using",
    "with",
}
ACTION_TOOL_IDS = {
    "send_email": {"gmail.send", "email.send", "mailer.report_send"},
    "submit_contact_form": {"browser.contact_form.send"},
    "post_message": {"slack.post_message", "browser.contact_form.send"},
    "create_document": {"docs.create", "workspace.docs.fill_template", "workspace.docs.research_notes"},
    "update_sheet": {"workspace.sheets.append", "workspace.sheets.track_step"},
}


def _clean_text_list(raw: Any, *, limit: int, max_item_len: int = 220) -> list[str]:
    if not isinstance(raw, list):
        return []
    rows: list[str] = []
    for item in raw:
        text = " ".join(str(item or "").split()).strip()
        if not text:
            continue
        key = text.lower()
        if key in {value.lower() for value in rows}:
            continue
        rows.append(text[:max_item_len])
        if len(rows) >= max(1, int(limit)):
            break
    return rows


def _extract_first_url(*chunks: str) -> str:
    joined = " ".join(str(chunk or "").strip() for chunk in chunks if str(chunk or "").strip())
    match = URL_RE.search(joined)
    return match.group(0).strip().rstrip(".,;)") if match else ""


def _host_from_url(url: str) -> str:
    try:
        host = str(urlparse(str(url or "").strip()).hostname or "").strip().lower()
    except Exception:
        host = ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _tokenize(text: str) -> set[str]:
    return {
        match.group(0).lower()
        for match in WORD_RE.finditer(str(text or ""))
        if len(match.group(0)) >= 4 and match.group(0).lower() not in STOPWORDS
    }


def _collect_evidence_texts(
    *,
    request_message: str,
    executed_steps: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    report_body: str,
    sources: list[dict[str, Any]],
) -> list[str]:
    rows: list[str] = []
    if str(report_body or "").strip():
        rows.append(str(report_body).strip()[:2200])
    rows.append(" ".join(str(request_message or "").split()).strip()[:500])
    for step in executed_steps[-24:]:
        if str(step.get("status") or "").strip().lower() != "success":
            continue
        title = " ".join(str(step.get("title") or "").split()).strip()
        summary = " ".join(str(step.get("summary") or "").split()).strip()
        joined = ". ".join([item for item in [title, summary] if item]).strip()
        if joined:
            rows.append(joined[:700])
    for action in actions[-24:]:
        if str(action.get("status") or "").strip().lower() != "success":
            continue
        summary = " ".join(str(action.get("summary") or "").split()).strip()
        if summary:
            rows.append(summary[:700])
    for source in sources[:24]:
        label = " ".join(str(source.get("label") or "").split()).strip()
        url = " ".join(str(source.get("url") or "").split()).strip()
        metadata = source.get("metadata")
        excerpt = ""
        if isinstance(metadata, dict):
            for key in ("excerpt", "snippet", "text_excerpt", "description"):
                value = metadata.get(key)
                if isinstance(value, str) and value.strip():
                    excerpt = value.strip()
                    break
        joined = " ".join(item for item in [label, url, excerpt] if item).strip()
        if joined:
            rows.append(joined[:900])
    deduped: list[str] = []
    seen: set[str] = set()
    for row in rows:
        text = " ".join(str(row or "").split()).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped[:64]


def _filter_required_facts_for_coverage(
    *,
    required_facts: list[str],
    required_actions: list[str],
    delivery_target: str,
    request_message: str,
) -> list[str]:
    rows = _clean_text_list(required_facts, limit=6)
    if not rows:
        return []

    action_set = {
        str(item).strip().lower()
        for item in required_actions
        if str(item).strip()
    }
    normalized_delivery = " ".join(str(delivery_target or "").split()).strip().lower()

    def _fallback() -> list[str]:
        filtered: list[str] = []
        for row in rows:
            normalized_row = " ".join(str(row or "").split()).strip().lower()
            if not normalized_row:
                continue
            if normalized_delivery and normalized_delivery in normalized_row:
                continue
            if "send_email" in action_set and EMAIL_RE.search(row):
                continue
            filtered.append(row)
            if len(filtered) >= 6:
                break
        return filtered

    if not env_bool("MAIA_AGENT_LLM_FACT_SLOT_FILTER_ENABLED", default=True):
        return _fallback()
    payload = {
        "required_facts": rows,
        "required_actions": _clean_text_list(required_actions, limit=6, max_item_len=64),
        "delivery_target": " ".join(str(delivery_target or "").split()).strip()[:180],
        "request_message": " ".join(str(request_message or "").split()).strip()[:420],
    }
    try:
        response = call_json_response(
            system_prompt=(
                "You classify required-fact rows for contract coverage checks. "
                "Return strict JSON only."
            ),
            user_prompt=(
                "Return JSON only:\n"
                '{ "keep_indexes":[0,1], "reason":"..." }\n'
                "Rules:\n"
                "- Keep only rows that are evidence-bearing factual outcomes.\n"
                "- Remove rows that are delivery/routing/action-precondition slots.\n"
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


def _fact_missing(*, fact: str, evidence_rows: list[str]) -> bool:
    fact_tokens = _tokenize(fact)
    if not fact_tokens:
        return True
    threshold = 2 if len(fact_tokens) >= 3 else 1
    for row in evidence_rows:
        overlap = len(fact_tokens.intersection(_tokenize(row)))
        if overlap >= threshold:
            return False
    return True


def _semantic_missing_required_facts(
    *,
    required_facts: list[str],
    evidence_rows: list[str],
) -> list[str] | None:
    if not required_facts:
        return []
    if not env_bool("MAIA_AGENT_LLM_FACT_COVERAGE_CHECK_ENABLED", default=True):
        return None
    payload = {
        "required_facts": required_facts[:8],
        "evidence_rows": evidence_rows[:32],
    }
    try:
        response = call_json_response(
            system_prompt=(
                "You verify whether required facts are covered by available execution evidence. "
                "Return strict JSON only."
            ),
            user_prompt=(
                "Return JSON only:\n"
                '{ "missing_fact_indexes":[0,1], "reason":"..." }\n'
                "Rules:\n"
                "- Use semantic reasoning across all evidence rows.\n"
                "- Never rely on hardcoded keyword matching.\n"
                "- Keep only indexes from required_facts that are still missing.\n"
                "- Do not invent new facts.\n\n"
                f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
            ),
            temperature=0.0,
            timeout_seconds=10,
            max_tokens=320,
        )
    except Exception:
        return None
    if not isinstance(response, dict):
        return None
    raw_indexes = response.get("missing_fact_indexes")
    if not isinstance(raw_indexes, list):
        return None
    missing: list[str] = []
    for raw in raw_indexes[:12]:
        try:
            index = int(raw)
        except Exception:
            continue
        if index < 0 or index >= len(required_facts):
            continue
        fact = required_facts[index]
        if fact in missing:
            continue
        missing.append(fact)
        if len(missing) >= 8:
            break
    return missing


def _successful_action_tool_ids(actions: list[dict[str, Any]]) -> set[str]:
    successful: set[str] = set()
    for action in actions[-30:]:
        if str(action.get("status") or "").strip().lower() != "success":
            continue
        tool_id = str(action.get("tool_id") or "").strip()
        if tool_id:
            successful.add(tool_id)
    return successful


def _normalize_side_effect_status(value: Any) -> str:
    cleaned = " ".join(str(value or "").split()).strip().lower()
    if cleaned in {"success", "completed", "sent"}:
        return "completed"
    if cleaned in {"pending", "started", "in_progress"}:
        return "pending"
    if cleaned in {"failed", "blocked", "skipped"}:
        return cleaned
    return cleaned


def _append_remediation(
    *,
    target: list[dict[str, Any]],
    tool_id: str,
    title: str,
    params: dict[str, Any] | None = None,
    allowed_tool_ids: set[str],
    max_rows: int = 4,
) -> None:
    if tool_id not in allowed_tool_ids:
        return
    payload = {
        "tool_id": tool_id,
        "title": " ".join(str(title or tool_id).split()).strip()[:120] or tool_id,
        "params": dict(params or {}),
    }
    try:
        signature = f"{payload['tool_id']}:{json.dumps(payload['params'], sort_keys=True, ensure_ascii=True)}"
    except Exception:
        signature = f"{payload['tool_id']}:{str(payload['params'])}"
    existing = {
        (
            item.get("tool_id"),
            json.dumps(item.get("params") or {}, sort_keys=True, ensure_ascii=True),
        )
        for item in target
        if isinstance(item, dict)
    }
    if (payload["tool_id"], json.dumps(payload["params"], sort_keys=True, ensure_ascii=True)) in existing:
        return
    target.append(payload)
    del signature  # keep lint quiet for local tooling parity
    if len(target) > max_rows:
        del target[max_rows:]


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
    required_actions = _clean_text_list(contract.get("required_actions"), limit=6, max_item_len=64)
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
    required_facts = _filter_required_facts_for_coverage(
        required_facts=_clean_text_list(contract.get("required_facts"), limit=6),
        required_actions=required_actions,
        delivery_target=delivery_target,
        request_message=request_message,
    )
    target_url = _extract_first_url(
        request_message,
        " ".join(str(source.get("url") or "").strip() for source in sources[:8]),
    )
    target_host = _host_from_url(target_url)
    allowed_set = {str(item).strip() for item in allowed_tool_ids if str(item).strip()}
    missing_items: list[str] = []
    reason_parts: list[str] = []
    remediation: list[dict[str, Any]] = []
    external_action_keys = ("send_email", "submit_contact_form", "post_message")
    pending_external_action = any(
        action_key in required_actions and clean_pending_action_tool_id in ACTION_TOOL_IDS.get(action_key, set())
        for action_key in external_action_keys
    )
    evidence_rows = _collect_evidence_texts(
        request_message=request_message,
        executed_steps=executed_steps,
        actions=actions,
        report_body=report_body,
        sources=sources,
    )

    semantic_missing_facts = _semantic_missing_required_facts(
        required_facts=required_facts,
        evidence_rows=evidence_rows,
    )
    lexical_missing_facts = [
        fact
        for fact in required_facts
        if _fact_missing(fact=fact, evidence_rows=evidence_rows)
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
                _append_remediation(
                    target=remediation,
                    tool_id="browser.playwright.inspect",
                    title="Inspect target website for missing required facts",
                    params={"url": target_url},
                    allowed_tool_ids=allowed_set,
                )
            _append_remediation(
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

    successful_tools = _successful_action_tool_ids(actions)
    for action in required_actions:
        action_key = str(action).strip()
        if not action_key:
            continue
        mapped_tools = ACTION_TOOL_IDS.get(action_key, set())
        side_effect_row = side_effect_rows.get(action_key, {})
        side_effect_state = _normalize_side_effect_status(side_effect_row.get("status"))
        if action_key == "send_email" and not delivery_target:
            missing_items.append("Missing delivery target for required action: send_email")
            reason_parts.append("Email delivery is requested but recipient is missing.")
            # Avoid drafting/sending remediation without an explicit recipient target.
            continue
        if clean_pending_action_tool_id and clean_pending_action_tool_id in mapped_tools:
            # When checking contract readiness right before executing this action,
            # avoid self-blocking on "required action not completed".
            continue
        if side_effect_state == "completed":
            continue
        if side_effect_state in {"failed", "blocked", "skipped"}:
            missing_items.append(f"External action failed: {action_key} ({side_effect_state})")
            reason_parts.append(
                f"Required external action '{action_key}' ended with status {side_effect_state}."
            )
            if action_key == "send_email":
                _append_remediation(
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
                _append_remediation(
                    target=remediation,
                    tool_id="gmail.draft",
                    title="Draft email delivery content",
                    params={"to": delivery_target} if delivery_target else {},
                    allowed_tool_ids=allowed_set,
                )
            if action_key == "submit_contact_form" and target_url:
                _append_remediation(
                    target=remediation,
                    tool_id="browser.playwright.inspect",
                    title="Open target website to locate contact form",
                    params={"url": target_url},
                    allowed_tool_ids=allowed_set,
                )

    missing_items = _clean_text_list(missing_items, limit=8, max_item_len=220)
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
        "missing_items": _clean_text_list(response.get("missing_items"), limit=8),
        "reason": " ".join(str(response.get("reason") or "").split()).strip()[:320],
        "recommended_remediation": remediation_rows,
    }


def merge_contract_checks(*, deterministic: dict[str, Any], llm: dict[str, Any]) -> dict[str, Any]:
    merged_missing = _clean_text_list(
        [*(deterministic.get("missing_items") or []), *(llm.get("missing_items") or [])],
        limit=8,
    )
    merged_reason_parts = [
        " ".join(str(deterministic.get("reason") or "").split()).strip(),
        " ".join(str(llm.get("reason") or "").split()).strip(),
    ]
    merged_reason = " ".join([item for item in merged_reason_parts if item])[:320]
    remediation_rows: list[dict[str, Any]] = []
    for row in [*(deterministic.get("recommended_remediation") or []), *(llm.get("recommended_remediation") or [])]:
        if not isinstance(row, dict):
            continue
        tool_id = str(row.get("tool_id") or "").strip()
        if not tool_id:
            continue
        params = row.get("params")
        title = " ".join(str(row.get("title") or tool_id).split()).strip()[:120]
        _append_remediation(
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
