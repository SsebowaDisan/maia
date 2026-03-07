from __future__ import annotations

from typing import Any

ZOOM_ACTIONS: set[str] = {"zoom_in", "zoom_out", "zoom_reset", "zoom_to_region"}


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalized_text(value: Any) -> str:
    return _clean_text(value).lower()


def _as_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return None
    if parsed != parsed:
        return None
    return parsed


def _string_list(value: Any, *, limit: int = 24) -> list[str]:
    if isinstance(value, list):
        rows = [_clean_text(item) for item in value]
    elif value in (None, ""):
        rows = []
    else:
        rows = [_clean_text(value)]
    cleaned = [item for item in rows if item]
    return list(dict.fromkeys(cleaned))[: max(1, int(limit or 1))]


def is_zoom_action(*, event_type: str, data: dict[str, Any] | None = None) -> bool:
    payload = dict(data or {})
    action = _normalized_text(payload.get("action"))
    if action in ZOOM_ACTIONS:
        return True
    normalized_event = _normalized_text(event_type).replace("-", "_")
    if "zoom_to_region" in normalized_event:
        return True
    if "zoom_in" in normalized_event:
        return True
    if "zoom_out" in normalized_event:
        return True
    if "zoom_reset" in normalized_event:
        return True
    return False


def collect_reference_lists(
    *,
    data: dict[str, Any],
    event_id: str = "",
    graph_node_id: str = "",
    scene_ref: str = "",
) -> tuple[list[str], list[str], list[str]]:
    graph_node_ids = _string_list(data.get("graph_node_ids"))
    if not graph_node_ids:
        graph_node_ids = _string_list(data.get("graph_node_id"))
    if not graph_node_ids and _clean_text(graph_node_id):
        graph_node_ids = [_clean_text(graph_node_id)]

    scene_refs = _string_list(data.get("scene_refs"))
    if not scene_refs:
        scene_refs = _string_list(data.get("scene_ref"))
    if not scene_refs and _clean_text(scene_ref):
        scene_refs = [_clean_text(scene_ref)]

    event_refs = _string_list(data.get("event_refs"))
    if not event_refs and _clean_text(event_id):
        event_refs = [_clean_text(event_id)]
    elif _clean_text(event_id):
        event_refs = list(dict.fromkeys([*event_refs, _clean_text(event_id)]))

    return graph_node_ids, scene_refs, event_refs


def _target_region(data: dict[str, Any]) -> dict[str, float] | None:
    region = data.get("target_region")
    if isinstance(region, dict):
        x = _as_float(region.get("x"))
        y = _as_float(region.get("y"))
        width = _as_float(region.get("width"))
        height = _as_float(region.get("height"))
    else:
        x = _as_float(data.get("region_x"))
        y = _as_float(data.get("region_y"))
        width = _as_float(data.get("region_width"))
        height = _as_float(data.get("region_height"))
    if x is None or y is None or width is None or height is None:
        return None
    return {
        "x": round(float(x), 3),
        "y": round(float(y), 3),
        "width": round(float(width), 3),
        "height": round(float(height), 3),
    }


def build_zoom_event_entry(
    *,
    event_id: str,
    event_type: str,
    event_index: int | None,
    timestamp: str | None,
    data: dict[str, Any],
    graph_node_id: str = "",
    scene_ref: str = "",
) -> dict[str, Any] | None:
    if not is_zoom_action(event_type=event_type, data=data):
        return None
    action = _normalized_text(data.get("action"))
    if action not in ZOOM_ACTIONS:
        normalized_event = _normalized_text(event_type)
        if "zoom_to_region" in normalized_event:
            action = "zoom_to_region"
        elif "zoom_in" in normalized_event:
            action = "zoom_in"
        elif "zoom_out" in normalized_event:
            action = "zoom_out"
        elif "zoom_reset" in normalized_event:
            action = "zoom_reset"
        else:
            action = "zoom_in"
    zoom_level = _as_float(data.get("zoom_level"))
    if zoom_level is None:
        zoom_level = _as_float(data.get("zoom_to"))
    zoom_reason = _clean_text(data.get("zoom_reason") or data.get("reason"))
    zoom_policy_triggers = _string_list(data.get("zoom_policy_triggers"), limit=8)
    entry: dict[str, Any] = {
        "event_ref": _clean_text(event_id),
        "event_type": _clean_text(event_type),
        "action": action,
        "scene_surface": _clean_text(data.get("scene_surface")),
        "scene_ref": _clean_text(scene_ref or data.get("scene_ref")),
        "graph_node_id": _clean_text(graph_node_id or data.get("graph_node_id")),
        "event_index": int(event_index or 0) if int(event_index or 0) > 0 else None,
        "timestamp": _clean_text(timestamp),
        "zoom_reason": zoom_reason,
        "zoom_policy_triggers": zoom_policy_triggers,
        "zoom_policy_version": _clean_text(data.get("zoom_policy_version")),
    }
    if zoom_level is not None:
        entry["zoom_level"] = round(float(zoom_level), 3)
    region = _target_region(data)
    if region:
        entry["target_region"] = region
    return {key: value for key, value in entry.items() if value not in (None, "", [])}


def _merged_zoom_history(
    *,
    existing: Any,
    new_entry: dict[str, Any] | None,
    limit: int = 24,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(existing, list):
        for item in existing:
            if not isinstance(item, dict):
                continue
            normalized = {
                key: value
                for key, value in dict(item).items()
                if value not in (None, "", [])
            }
            if normalized:
                rows.append(normalized)
    if new_entry:
        entry_ref = _clean_text(new_entry.get("event_ref"))
        replaced = False
        if entry_ref:
            for index, row in enumerate(rows):
                row_ref = _clean_text(row.get("event_ref"))
                if row_ref and row_ref == entry_ref:
                    rows[index] = dict(new_entry)
                    replaced = True
                    break
        if not replaced:
            rows.append(dict(new_entry))
    if len(rows) > max(1, int(limit or 1)):
        rows = rows[-max(1, int(limit or 1)) :]
    return rows


def enrich_event_data_with_zoom(
    *,
    data: dict[str, Any] | None,
    event_type: str,
    event_id: str = "",
    event_index: int | None = None,
    timestamp: str | None = None,
    graph_node_id: str = "",
    scene_ref: str = "",
) -> dict[str, Any]:
    payload = dict(data or {})
    graph_node_ids, scene_refs, event_refs = collect_reference_lists(
        data=payload,
        event_id=event_id,
        graph_node_id=graph_node_id,
        scene_ref=scene_ref,
    )
    if graph_node_ids:
        payload["graph_node_ids"] = graph_node_ids
    if scene_refs:
        payload["scene_refs"] = scene_refs
    if event_refs:
        payload["event_refs"] = event_refs

    zoom_entry = build_zoom_event_entry(
        event_id=event_id,
        event_type=event_type,
        event_index=event_index,
        timestamp=timestamp,
        data=payload,
        graph_node_id=graph_node_id,
        scene_ref=scene_ref,
    )
    if zoom_entry:
        payload["zoom_event"] = zoom_entry
        payload["zoom_history"] = _merged_zoom_history(existing=payload.get("zoom_history"), new_entry=zoom_entry)
        if not _clean_text(payload.get("zoom_reason")) and _clean_text(zoom_entry.get("zoom_reason")):
            payload["zoom_reason"] = _clean_text(zoom_entry.get("zoom_reason"))
        if payload.get("zoom_level") in (None, "") and zoom_entry.get("zoom_level") is not None:
            payload["zoom_level"] = zoom_entry.get("zoom_level")

    return payload


__all__ = [
    "ZOOM_ACTIONS",
    "build_zoom_event_entry",
    "collect_reference_lists",
    "enrich_event_data_with_zoom",
    "is_zoom_action",
]
