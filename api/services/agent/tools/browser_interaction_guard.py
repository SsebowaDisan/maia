from __future__ import annotations

import json
from typing import Any

from api.services.agent.llm_runtime import call_json_response


def _sanitize_action(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    action_type = str(value.get("type") or "").strip().lower()[:24]
    selector = str(value.get("selector") or "").strip()[:180]
    action_value = str(value.get("value") or "").strip()[:240]
    if action_type not in {"click", "fill"}:
        return {}
    if not selector:
        return {}
    return {
        "type": action_type,
        "selector": selector,
        "value": action_value,
    }


def assess_browser_interactions(
    *,
    prompt: str,
    url: str,
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    sanitized_actions = [
        item for item in (_sanitize_action(action) for action in actions[:8]) if item
    ]
    if not sanitized_actions:
        return {
            "allowed_actions": [],
            "blocked_actions": [],
            "policy_note": "No browser interaction actions requested.",
            "llm_used": False,
        }

    payload = {
        "task_prompt": str(prompt or "").strip()[:900],
        "url": str(url or "").strip()[:220],
        "actions": [
            {"index": idx + 1, **action}
            for idx, action in enumerate(sanitized_actions)
        ],
    }
    response = call_json_response(
        system_prompt=(
            "You are a browser interaction safety reviewer for enterprise web research tasks. "
            "Allow only actions that are required for navigation and evidence collection. "
            "Block actions that can submit data, trigger purchases, or perform account changes."
        ),
        user_prompt=(
            "Review the requested browser interaction actions.\n"
            "Return strict JSON:\n"
            "{\n"
            '  "actions":[{"index":1,"allow":true,"reason":"string","type":"click|fill","selector":"...","value":"..."}],\n'
            '  "policy_note":"string"\n'
            "}\n"
            "Rules:\n"
            "- Preserve action order.\n"
            "- Keep `selector` unchanged for allowed actions.\n"
            "- For blocked actions, keep reason short and specific.\n\n"
            f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
        ),
        temperature=0.0,
        timeout_seconds=12,
        max_tokens=420,
    )
    decisions = response.get("actions") if isinstance(response, dict) else []

    allowed_actions: list[dict[str, str]] = []
    blocked_actions: list[dict[str, str]] = []
    if isinstance(decisions, list):
        by_index: dict[int, dict[str, Any]] = {}
        for row in decisions:
            if not isinstance(row, dict):
                continue
            try:
                idx = int(row.get("index") or 0)
            except Exception:
                idx = 0
            if idx <= 0:
                continue
            by_index[idx] = row
        if not by_index:
            return {
                "allowed_actions": [dict(action) for action in sanitized_actions],
                "blocked_actions": [],
                "policy_note": "Interaction review returned no actionable decisions; defaulted to allow.",
                "llm_used": isinstance(response, dict),
            }
        for idx, action in enumerate(sanitized_actions, start=1):
            row = by_index.get(idx) or {}
            if not row:
                allowed_actions.append(dict(action))
                continue
            allow = bool(row.get("allow"))
            reason = " ".join(str(row.get("reason") or "").split()).strip()[:200]
            if allow:
                allowed_actions.append(dict(action))
            else:
                blocked_actions.append(
                    {
                        "type": action.get("type") or "",
                        "selector": action.get("selector") or "",
                        "reason": reason or "Blocked by interaction policy review.",
                    }
                )

    if not allowed_actions and not blocked_actions:
        # Fail-open fallback for availability: preserve behavior if LLM is unavailable.
        allowed_actions = [dict(action) for action in sanitized_actions]

    policy_note = (
        " ".join(str(response.get("policy_note") or "").split()).strip()[:220]
        if isinstance(response, dict)
        else ""
    )
    if not policy_note:
        if blocked_actions:
            policy_note = (
                f"Allowed {len(allowed_actions)} interaction action(s); "
                f"blocked {len(blocked_actions)} high-risk action(s)."
            )
        else:
            policy_note = f"Allowed {len(allowed_actions)} interaction action(s)."
    return {
        "allowed_actions": allowed_actions,
        "blocked_actions": blocked_actions,
        "policy_note": policy_note,
        "llm_used": isinstance(response, dict),
    }


__all__ = ["assess_browser_interactions"]
