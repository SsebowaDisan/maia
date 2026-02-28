from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from api.context import ApiContext


def get_index(context: ApiContext, index_id: int | None):
    try:
        return context.get_index(index_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def normalize_ids(values: list[str]) -> list[str]:
    cleaned = [value.strip() for value in values if isinstance(value, str) and value.strip()]
    return list(dict.fromkeys(cleaned))


def normalize_upload_scope(scope: str | None) -> str:
    value = str(scope or "persistent").strip().lower()
    return "chat_temp" if value == "chat_temp" else "persistent"


def serialize_group_record(group: Any) -> dict[str, Any]:
    data = group.data or {}
    file_ids = data.get("files") or []
    return {
        "id": str(group.id),
        "name": str(group.name or ""),
        "file_ids": [str(file_id) for file_id in file_ids if str(file_id).strip()],
        "date_created": group.date_created,
    }
