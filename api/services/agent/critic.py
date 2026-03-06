from __future__ import annotations

import json
import re
from typing import Any

from api.services.agent.llm_runtime import call_text_response, env_bool

EXTERNAL_ACTION_TOOL_IDS = {
    "gmail.send",
    "email.send",
    "mailer.report_send",
    "browser.contact_form.send",
    "slack.post_message",
}
ACTION_GAP_HINT_RE = re.compile(
    r"(lack of action|missing action|not completed|not sent|no .*requested|not delivered|not executed|failed action execution)",
    re.IGNORECASE,
)
ACTION_ATTEMPT_CONTRADICTION_RE = re.compile(
    r"(contradict|implies an attempt|tool .*used|attempt was made|claim of (a )?failed action)",
    re.IGNORECASE,
)
INCOMPLETE_ACK_RE = re.compile(
    r"(not completed|failed|could not|was not sent|not sent|unable to|did not submit)",
    re.IGNORECASE,
)


def _normalize_actions(raw: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, str]] = []
    for item in raw[-30:]:
        if not isinstance(item, dict):
            continue
        tool_id = " ".join(str(item.get("tool_id") or "").split()).strip()
        status = " ".join(str(item.get("status") or "").split()).strip().lower()
        action_class = " ".join(str(item.get("action_class") or "").split()).strip().lower()
        summary = " ".join(str(item.get("summary") or "").split()).strip()[:240]
        if not tool_id:
            continue
        rows.append(
            {
                "tool_id": tool_id,
                "status": status,
                "action_class": action_class,
                "summary": summary,
            }
        )
    return rows


def _build_action_evidence(raw_actions: list[dict[str, Any]] | None) -> dict[str, Any]:
    actions = _normalize_actions(raw_actions)
    successful = [row for row in actions if row.get("status") == "success"]
    attempted_external = [
        row for row in actions if row.get("tool_id") in EXTERNAL_ACTION_TOOL_IDS
    ]
    external_success = [
        row for row in successful if row.get("tool_id") in EXTERNAL_ACTION_TOOL_IDS
    ]
    return {
        "total_actions": len(actions),
        "successful_actions": len(successful),
        "attempted_external_actions": [
            {
                "tool_id": row.get("tool_id"),
                "status": row.get("status"),
                "summary": row.get("summary"),
            }
            for row in attempted_external[-6:]
        ],
        "successful_external_actions": [
            {
                "tool_id": row.get("tool_id"),
                "summary": row.get("summary"),
            }
            for row in external_success[-4:]
        ],
    }


def _normalize_contract_gate(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    missing_items = [
        " ".join(str(item or "").split()).strip()
        for item in (raw.get("missing_items") if isinstance(raw.get("missing_items"), list) else [])
        if " ".join(str(item or "").split()).strip()
    ][:8]
    return {
        "ready_for_final_response": bool(raw.get("ready_for_final_response")),
        "ready_for_external_actions": bool(raw.get("ready_for_external_actions")),
        "missing_items": missing_items,
    }


def _is_ok_verdict(clean_verdict: str) -> bool:
    normalized = clean_verdict.lower().strip(". ")
    ok_values = {"ok", "no issues", "safe", "looks good"}
    return normalized in ok_values or normalized.startswith("ok ")


def _should_suppress_action_gap_flag(
    *,
    critic_note: str,
    answer_text: str,
    action_evidence: dict[str, Any],
    contract_gate: dict[str, Any],
) -> bool:
    if not critic_note or not ACTION_GAP_HINT_RE.search(critic_note):
        return False
    successful_external_actions = (
        action_evidence.get("successful_external_actions")
        if isinstance(action_evidence.get("successful_external_actions"), list)
        else []
    )
    attempted_external_actions = (
        action_evidence.get("attempted_external_actions")
        if isinstance(action_evidence.get("attempted_external_actions"), list)
        else []
    )
    missing_items = (
        contract_gate.get("missing_items")
        if isinstance(contract_gate.get("missing_items"), list)
        else []
    )
    missing_required_action = any(
        "required action not completed" in str(item).lower()
        for item in missing_items
    )
    answer_acknowledges_incomplete = bool(
        INCOMPLETE_ACK_RE.search(" ".join(str(answer_text or "").split()))
    )
    if attempted_external_actions and missing_required_action and answer_acknowledges_incomplete:
        return True
    if attempted_external_actions and ACTION_ATTEMPT_CONTRADICTION_RE.search(critic_note):
        return True
    if not successful_external_actions:
        return False
    if missing_required_action:
        return False
    if bool(contract_gate.get("ready_for_external_actions")):
        return True
    return False


def review_final_answer(
    *,
    request_message: str,
    answer_text: str,
    source_urls: list[str],
    actions: list[dict[str, Any]] | None = None,
    contract_check: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not env_bool("MAIA_AGENT_CRITIC_ENABLED", default=True):
        return {"needs_human_review": False, "critic_note": ""}

    action_evidence = _build_action_evidence(actions)
    contract_gate = _normalize_contract_gate(contract_check)
    payload = {
        "request_message": " ".join(str(request_message or "").split()).strip()[:600],
        "answer": str(answer_text or "").strip()[:5000],
        "source_urls": [
            str(item).strip()
            for item in (source_urls or [])
            if str(item).strip()
        ][:12],
        "action_evidence": action_evidence,
        "contract_gate": contract_gate,
    }
    verdict = call_text_response(
        system_prompt=(
            "Review the following answer for factual correctness and safety. "
            "Use execution evidence to avoid false lack-of-action claims. "
            "If successful external actions are present and contract gate allows actions, "
            "do not claim missing action execution. "
            "Return 'OK' when no issues are found, or explain concrete issues."
        ),
        user_prompt=f"Input:\n{json.dumps(payload, ensure_ascii=True)}",
        temperature=0.0,
        timeout_seconds=12,
        max_tokens=220,
    )
    clean_verdict = " ".join(str(verdict or "").split()).strip()
    if not clean_verdict:
        return {"needs_human_review": False, "critic_note": ""}

    if _is_ok_verdict(clean_verdict):
        return {"needs_human_review": False, "critic_note": ""}
    if _should_suppress_action_gap_flag(
        critic_note=clean_verdict,
        answer_text=answer_text,
        action_evidence=action_evidence,
        contract_gate=contract_gate,
    ):
        return {"needs_human_review": False, "critic_note": ""}
    return {
        "needs_human_review": True,
        "critic_note": clean_verdict[:420],
    }
