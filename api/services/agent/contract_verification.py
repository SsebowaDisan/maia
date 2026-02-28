from __future__ import annotations

import json
import re
from typing import Any

URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
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
    "post_message": {"slack.post_message"},
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


def _successful_action_tool_ids(actions: list[dict[str, Any]]) -> set[str]:
    successful: set[str] = set()
    for action in actions[-30:]:
        if str(action.get("status") or "").strip().lower() != "success":
            continue
        tool_id = str(action.get("tool_id") or "").strip()
        if tool_id:
            successful.add(tool_id)
    return successful


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
) -> dict[str, Any]:
    required_facts = _clean_text_list(contract.get("required_facts"), limit=6)
    required_actions = _clean_text_list(contract.get("required_actions"), limit=6, max_item_len=64)
    delivery_target = " ".join(str(contract.get("delivery_target") or "").split()).strip()
    target_url = _extract_first_url(
        request_message,
        " ".join(str(source.get("url") or "").strip() for source in sources[:8]),
    )
    allowed_set = {str(item).strip() for item in allowed_tool_ids if str(item).strip()}
    missing_items: list[str] = []
    reason_parts: list[str] = []
    remediation: list[dict[str, Any]] = []
    evidence_rows = _collect_evidence_texts(
        request_message=request_message,
        executed_steps=executed_steps,
        actions=actions,
        report_body=report_body,
        sources=sources,
    )

    missing_facts: list[str] = []
    for fact in required_facts:
        if _fact_missing(fact=fact, evidence_rows=evidence_rows):
            missing_facts.append(fact)
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
            params={"query": "; ".join(missing_facts[:3]) or request_message},
            allowed_tool_ids=allowed_set,
        )

    successful_tools = _successful_action_tool_ids(actions)
    clean_pending_action_tool_id = str(pending_action_tool_id or "").strip()
    for action in required_actions:
        action_key = str(action).strip()
        if not action_key:
            continue
        mapped_tools = ACTION_TOOL_IDS.get(action_key, set())
        if action_key == "send_email" and not delivery_target:
            missing_items.append("Missing delivery target for required action: send_email")
        if clean_pending_action_tool_id and clean_pending_action_tool_id in mapped_tools:
            # When checking contract readiness right before executing this action,
            # avoid self-blocking on "required action not completed".
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
