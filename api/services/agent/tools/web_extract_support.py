from __future__ import annotations

import hashlib
import json
from typing import Any

from api.services.agent.tools.base import ToolTraceEvent

SCENE_SURFACE_PREVIEW = "preview"


def snippet(text: str, max_len: int = 220) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= max_len:
        return compact
    return f"{compact[: max_len - 1].rstrip()}..."


def event(
    *,
    tool_id: str,
    event_type: str,
    title: str,
    detail: str = "",
    data: dict[str, Any] | None = None,
) -> ToolTraceEvent:
    payload = {"tool_id": tool_id, "scene_surface": SCENE_SURFACE_PREVIEW}
    if isinstance(data, dict):
        payload.update(data)
    return ToolTraceEvent(event_type=event_type, title=title, detail=detail, data=payload)


def normalize_field_schema(value: Any) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    if isinstance(value, dict):
        for raw_name, raw_type in list(value.items())[:20]:
            name = str(raw_name or "").strip()[:80]
            field_type = str(raw_type or "string").strip().lower()[:32] or "string"
            if not name:
                continue
            normalized.append({"name": name, "type": field_type, "description": ""})
    elif isinstance(value, list):
        for item in value[:20]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("field") or "").strip()[:80]
            if not name:
                continue
            field_type = str(item.get("type") or "string").strip().lower()[:32] or "string"
            description = str(item.get("description") or "").strip()[:160]
            normalized.append({"name": name, "type": field_type, "description": description})
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in normalized:
        key = str(row.get("name") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def parse_boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"true", "yes", "1", "y"}:
        return True
    if text in {"false", "no", "0", "n"}:
        return False
    return None


def coerce_field_value(field_type: str, value: Any) -> Any:
    normalized_type = str(field_type or "string").strip().lower()
    if normalized_type in {"number", "float"}:
        try:
            return float(str(value).replace(",", "").strip())
        except Exception:
            return None
    if normalized_type in {"integer", "int"}:
        try:
            return int(float(str(value).replace(",", "").strip()))
        except Exception:
            return None
    if normalized_type in {"bool", "boolean"}:
        return parse_boolean(value)
    if normalized_type in {"array", "list"}:
        if isinstance(value, list):
            cleaned = [str(item).strip()[:160] for item in value if str(item).strip()]
            return cleaned[:12]
        text = str(value or "").strip()
        if not text:
            return []
        return [text[:160]]
    text = str(value or "").strip()
    return text[:360]


def sanitize_values(values: Any, field_schema: list[dict[str, str]]) -> dict[str, Any]:
    rows = values if isinstance(values, dict) else {}
    if field_schema:
        output: dict[str, Any] = {}
        for field in field_schema:
            name = str(field.get("name") or "").strip()
            if not name:
                continue
            output[name] = coerce_field_value(str(field.get("type") or "string"), rows.get(name))
        return output
    fallback: dict[str, Any] = {}
    for raw_key, raw_value in list(rows.items())[:12]:
        key = str(raw_key or "").strip()[:80]
        if not key:
            continue
        if isinstance(raw_value, (int, float, bool)):
            fallback[key] = raw_value
            continue
        if isinstance(raw_value, list):
            cleaned = [str(item).strip()[:160] for item in raw_value if str(item).strip()]
            fallback[key] = cleaned[:10]
            continue
        text = str(raw_value or "").strip()
        fallback[key] = text[:360]
    return fallback


def sanitize_evidence(payload: Any, *, url: str) -> list[dict[str, Any]]:
    rows = payload if isinstance(payload, list) else []
    output: list[dict[str, Any]] = []
    for row in rows[:12]:
        if not isinstance(row, dict):
            continue
        field_name = str(row.get("field") or "").strip()[:80]
        quote = str(row.get("quote") or row.get("excerpt") or "").strip()[:320]
        if not quote:
            continue
        confidence_raw = row.get("confidence")
        try:
            confidence = max(0.0, min(1.0, float(confidence_raw)))
        except Exception:
            confidence = None
        output.append(
            {
                "field": field_name,
                "quote": quote,
                "confidence": confidence,
                "url": url,
            }
        )
    return output


def schema_signature(field_schema: list[dict[str, str]]) -> str:
    ordered = [
        {
            "name": str(item.get("name") or "").strip(),
            "type": str(item.get("type") or "").strip().lower(),
        }
        for item in field_schema
    ]
    raw = json.dumps(ordered, ensure_ascii=True, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def extraction_fingerprint(*, url: str, goal: str, page_text: str, schema_signature: str) -> str:
    payload = {
        "url": str(url or "").strip().lower(),
        "goal": " ".join(str(goal or "").split()).strip().lower(),
        "content_hash": hashlib.sha256(str(page_text or "").encode("utf-8")).hexdigest(),
        "schema_signature": schema_signature,
    }
    raw = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def schema_coverage(field_schema: list[dict[str, str]], values: dict[str, Any]) -> float:
    if not field_schema:
        return 1.0 if values else 0.0
    populated = 0
    for field in field_schema:
        name = str(field.get("name") or "").strip()
        if not name:
            continue
        value = values.get(name)
        if value is None:
            continue
        if isinstance(value, str):
            if value.strip():
                populated += 1
            continue
        if isinstance(value, list):
            if value:
                populated += 1
            continue
        populated += 1
    expected = max(1, len([row for row in field_schema if str(row.get("name") or "").strip()]))
    return round(max(0.0, min(1.0, float(populated) / float(expected))), 4)
