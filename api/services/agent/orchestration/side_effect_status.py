from __future__ import annotations

from typing import Any

from api.services.agent.models import AgentAction, utc_now


EXTERNAL_ACTION_KEYS: tuple[str, ...] = ("send_email", "submit_contact_form", "post_message")


def record_side_effect_status(
    *,
    settings: dict[str, Any],
    action_key: str,
    status: str,
    tool_id: str,
    detail: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_key = " ".join(str(action_key or "").split()).strip().lower()
    normalized_status = " ".join(str(status or "").split()).strip().lower()
    if normalized_key not in EXTERNAL_ACTION_KEYS:
        return {}
    row = {
        "action_key": normalized_key,
        "status": normalized_status or "unknown",
        "tool_id": " ".join(str(tool_id or "").split()).strip(),
        "detail": " ".join(str(detail or "").split()).strip()[:260],
        "timestamp": utc_now().isoformat(),
    }
    if isinstance(metadata, dict) and metadata:
        row["metadata"] = dict(metadata)
    status_map_raw = settings.get("__side_effect_status")
    status_map = dict(status_map_raw) if isinstance(status_map_raw, dict) else {}
    status_map[normalized_key] = row
    settings["__side_effect_status"] = status_map
    history_raw = settings.get("__side_effect_status_history")
    history = list(history_raw) if isinstance(history_raw, list) else []
    history.append(row)
    settings["__side_effect_status_history"] = history[-80:]
    return row


def side_effect_status_from_actions(*, actions: list[AgentAction]) -> dict[str, dict[str, Any]]:
    from api.services.agent.contract_verification import ACTION_TOOL_IDS  # local import to avoid circular import

    status_by_key: dict[str, dict[str, Any]] = {}
    for action in list(actions or [])[-40:]:
        tool_id = " ".join(str(action.tool_id or "").split()).strip()
        if not tool_id:
            continue
        for key, tool_ids in ACTION_TOOL_IDS.items():
            if key not in EXTERNAL_ACTION_KEYS:
                continue
            if tool_id not in set(tool_ids):
                continue
            status_by_key[key] = {
                "action_key": key,
                "status": " ".join(str(action.status or "").split()).strip().lower(),
                "tool_id": tool_id,
                "detail": " ".join(str(action.summary or "").split()).strip()[:260],
                "timestamp": str(action.ended_at or action.started_at or ""),
                "metadata": action.metadata if isinstance(action.metadata, dict) else {},
            }
    return status_by_key
