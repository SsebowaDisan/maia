from __future__ import annotations

import json
import os
from typing import Any, Mapping

from api.services.agent.llm_runtime import call_json_response, has_openai_credentials

CAPABILITY_ID_GOAL_PAGE_DISCOVERY = "goal_page_discovery"


def _safe_text(value: Any, *, max_len: int = 220) -> str:
    text = " ".join(str(value or "").split()).strip()
    return text[: max(1, int(max_len))]


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    token = str(value or "").strip().lower()
    if not token:
        return default
    if token in {"1", "true", "yes", "on"}:
        return True
    if token in {"0", "false", "no", "off"}:
        return False
    return default


def _list_of_text(values: Any, *, max_items: int = 16, max_len: int = 120) -> list[str]:
    if not isinstance(values, list):
        return []
    output: list[str] = []
    for item in values:
        token = _safe_text(item, max_len=max_len).lower()
        if not token or token in output:
            continue
        output.append(token)
        if len(output) >= max_items:
            break
    return output


def _role_step_tool_ids(settings: Mapping[str, Any]) -> list[str]:
    rows = settings.get("__role_owned_steps")
    if not isinstance(rows, list):
        return []
    output: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        tool_id = _safe_text(row.get("tool_id"), max_len=120).lower()
        if not tool_id or tool_id in output:
            continue
        output.append(tool_id)
        if len(output) >= 24:
            break
    return output


def _signal_bundle(settings: Mapping[str, Any]) -> dict[str, Any]:
    task_contract = settings.get("__task_contract")
    required_actions = (
        _list_of_text(task_contract.get("required_actions"), max_items=16, max_len=80)
        if isinstance(task_contract, dict)
        else []
    )
    return {
        "intent_tags": _list_of_text(settings.get("__intent_tags"), max_items=16, max_len=80),
        "required_actions": required_actions,
        "required_domains": _list_of_text(
            settings.get("__capability_required_domains"),
            max_items=12,
            max_len=80,
        ),
        "preferred_tool_ids": _list_of_text(
            settings.get("__capability_preferred_tool_ids"),
            max_items=24,
            max_len=120,
        ),
        "role_step_tool_ids": _role_step_tool_ids(settings),
    }


def _fallback_enablement(signals: dict[str, Any]) -> tuple[bool, float, str]:
    tags = {str(item).strip().lower() for item in (signals.get("intent_tags") or [])}
    actions = {str(item).strip().lower() for item in (signals.get("required_actions") or [])}
    domains = {str(item).strip().lower() for item in (signals.get("required_domains") or [])}
    preferred_tools = {
        str(item).strip().lower() for item in (signals.get("preferred_tool_ids") or [])
    }
    role_tools = {str(item).strip().lower() for item in (signals.get("role_step_tool_ids") or [])}
    has_contact_path = bool(
        "contact_form_submission" in tags
        or "submit_contact_form" in actions
        or "browser.contact_form.send" in preferred_tools
        or "browser.contact_form.send" in role_tools
        or "outreach" in domains
    )
    has_goal_navigation = bool("goal_page_navigation" in tags)
    enabled = has_contact_path or has_goal_navigation
    confidence = 0.71 if enabled else 0.55
    reason = (
        "Structured task signals require reusable goal-page navigation before specialist execution."
        if enabled
        else "No structured task signals required optional goal-page discovery."
    )
    return enabled, confidence, reason


def _llm_enablement(signals: dict[str, Any]) -> tuple[bool, float, str] | None:
    if not has_openai_credentials():
        return None
    payload = {"capability_id": CAPABILITY_ID_GOAL_PAGE_DISCOVERY, "signals": signals}
    try:
        response = call_json_response(
            system_prompt=(
                "You evaluate whether an optional agent capability should run. "
                "Use only structured workflow signals and return strict JSON."
            ),
            user_prompt=(
                "Return JSON only in this schema:\n"
                '{ "enable_capability": true, "confidence": 0.0, "reason": "..." }\n'
                "Rules:\n"
                "- Treat intent tags, required actions, capability domains, and role-step tool ownership as primary evidence.\n"
                "- Decide if optional goal-page discovery should run before specialist interaction.\n"
                "- Keep confidence in [0,1].\n\n"
                f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
            ),
            temperature=0.0,
            timeout_seconds=10,
            max_tokens=180,
        )
    except Exception:
        return None
    if not isinstance(response, dict):
        return None
    enabled = bool(response.get("enable_capability"))
    try:
        confidence = max(0.0, min(1.0, float(response.get("confidence"))))
    except Exception:
        confidence = 0.0
    reason = _safe_text(response.get("reason"), max_len=220)
    return enabled, confidence, reason or "LLM capability evaluation completed."


def resolve_goal_page_discovery_capability(
    *,
    settings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    settings_view: Mapping[str, Any] = settings or {}
    flag_enabled = _coerce_bool(
        settings_view.get("agent.capabilities.goal_page_discovery_enabled")
        or settings_view.get("MAIA_AGENT_GOAL_PAGE_DISCOVERY_ENABLED")
        or os.getenv("MAIA_AGENT_GOAL_PAGE_DISCOVERY_ENABLED"),
        default=False,
    )
    if not flag_enabled:
        return {
            "capability_id": CAPABILITY_ID_GOAL_PAGE_DISCOVERY,
            "enabled": False,
            "confidence": 1.0,
            "reason": "Capability flag disabled.",
            "source": "flag",
            "signals": {},
        }

    signals = _signal_bundle(settings_view)
    llm_result = _llm_enablement(signals)
    if llm_result is not None:
        enabled, confidence, reason = llm_result
        return {
            "capability_id": CAPABILITY_ID_GOAL_PAGE_DISCOVERY,
            "enabled": bool(enabled),
            "confidence": round(confidence, 3),
            "reason": reason,
            "source": "llm",
            "signals": signals,
        }

    enabled, confidence, reason = _fallback_enablement(signals)
    return {
        "capability_id": CAPABILITY_ID_GOAL_PAGE_DISCOVERY,
        "enabled": bool(enabled),
        "confidence": round(confidence, 3),
        "reason": reason,
        "source": "fallback",
        "signals": signals,
    }

