from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from api.context import ApiContext


def get_index(context: ApiContext, index_id: int | None):
    resolved_index_id: int | None = index_id
    if isinstance(resolved_index_id, int) and resolved_index_id <= 0:
        resolved_index_id = None
    try:
        return context.get_index(resolved_index_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def normalize_ids(values: list[str]) -> list[str]:
    cleaned = [value.strip() for value in values if isinstance(value, str) and value.strip()]
    return list(dict.fromkeys(cleaned))


def normalize_upload_scope(scope: str | None) -> str:
    """Normalise the upload scope string to one of two canonical values.

    Returns:
        "user_temp"  — composer / transient upload, allowed for any user.
                       Accepts: "chat_temp", "user_temp"
        "library"    — persistent file-library write, admin-only.
                       Accepts: "library", "persistent", or anything else.
    """
    value = str(scope or "library").strip().lower()
    if value in {"chat_temp", "user_temp"}:
        return "user_temp"
    return "library"


def serialize_group_record(group: Any) -> dict[str, Any]:
    data = group.data or {}
    file_ids = data.get("files") or []
    return {
        "id": str(group.id),
        "name": str(group.name or ""),
        "file_ids": [str(file_id) for file_id in file_ids if str(file_id).strip()],
        "date_created": group.date_created,
    }
