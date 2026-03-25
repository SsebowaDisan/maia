from __future__ import annotations

from copy import deepcopy
import re
import threading
from time import monotonic
from typing import Any
from urllib.parse import urlparse

from sqlmodel import Session, select

from api.context import ApiContext
from api.schemas import ChatRequest, IndexSelection

from ktem.db.models import engine

from .constants import logger

_HTTP_URL_RE = re.compile(r"https?://[^\s\])>\"']+", flags=re.IGNORECASE)
_AUTO_URL_INDEX_MARKER = "__auto_url_indexed"
_AUTO_URL_CACHE_LOCK = threading.Lock()
_AUTO_URL_INDEX_CACHE: dict[str, tuple[float, list[str]]] = {}


def _normalize_http_url(raw_value: Any) -> str:
    value = " ".join(str(raw_value or "").split()).strip()
    if not value:
        return ""
    try:
        parsed = urlparse(value)
    except Exception:
        return ""
    if parsed.scheme not in {"http", "https"}:
        return ""
    if not str(parsed.netloc or "").strip():
        return ""
    normalized_path = str(parsed.path or "").rstrip("/") or "/"
    return parsed._replace(
        scheme=str(parsed.scheme or "").lower(),
        netloc=str(parsed.netloc or "").lower(),
        path=normalized_path,
        fragment="",
    ).geturl()


def _normalize_request_attachments(request: ChatRequest) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in list(getattr(request, "attachments", []) or []):
        name_raw = str(getattr(item, "name", "") or "").strip()
        file_id_raw = str(getattr(item, "file_id", "") or "").strip()
        if not name_raw and not file_id_raw:
            continue
        name = " ".join(name_raw.split())[:220]
        file_id = " ".join(file_id_raw.split())[:160]
        dedupe_key = (file_id, name.lower())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        payload = {"name": name or file_id or "Uploaded file"}
        if file_id:
            payload["file_id"] = file_id
        normalized.append(payload)
    return normalized


def _request_with_command(request: ChatRequest, command: str) -> ChatRequest:
    try:
        return request.model_copy(update={"command": command})
    except Exception:
        payload = request.model_dump()
        payload["command"] = command
        return ChatRequest(**payload)


def _request_with_updates(request: ChatRequest, updates: dict[str, Any]) -> ChatRequest:
    try:
        return request.model_copy(update=updates)
    except Exception:
        payload = request.model_dump()
        payload.update(updates)
        return ChatRequest(**payload)


def _extract_message_urls(message: str, *, max_urls: int = 8) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for match in _HTTP_URL_RE.finditer(str(message or "")):
        normalized = _normalize_http_url(str(match.group(0) or "").rstrip(".,;:!?"))
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        urls.append(normalized)
        if len(urls) >= max(1, int(max_urls)):
            break
    return urls


def _first_available_index_id(context: ApiContext) -> int | None:
    try:
        indices = list(getattr(context.app.index_manager, "indices", []) or [])
    except Exception:
        return None
    if not indices:
        return None
    try:
        return int(getattr(indices[0], "id"))
    except Exception:
        return None


def _pick_target_index_id(
    request: ChatRequest,
    context: ApiContext,
) -> int | None:
    selection = request.index_selection if isinstance(request.index_selection, dict) else {}
    for raw_key, selected in selection.items():
        mode = str(getattr(selected, "mode", "") or "").strip().lower()
        if mode == "disabled":
            continue
        try:
            return int(str(raw_key))
        except Exception:
            continue
    return _first_available_index_id(context)


def _merge_request_index_selection(
    request: ChatRequest,
    *,
    index_id: int,
    file_ids: list[str],
) -> dict[str, IndexSelection]:
    merged: dict[str, IndexSelection] = {}
    existing_selection = request.index_selection if isinstance(request.index_selection, dict) else {}
    for key, selected in existing_selection.items():
        mode = str(getattr(selected, "mode", "all") or "all").strip().lower() or "all"
        selected_ids_raw = getattr(selected, "file_ids", [])
        selected_ids = [
            str(item).strip()
            for item in (selected_ids_raw if isinstance(selected_ids_raw, list) else [])
            if str(item).strip()
        ]
        merged[str(key)] = IndexSelection(mode=mode, file_ids=selected_ids)

    key = str(index_id)
    existing = merged.get(key)
    existing_mode = str(getattr(existing, "mode", "") or "").strip().lower() if existing else ""
    existing_ids = (
        [str(item).strip() for item in getattr(existing, "file_ids", []) if str(item).strip()]
        if existing
        else []
    )
    file_pool = existing_ids if existing_mode == "select" else []
    seen_ids = {item for item in file_pool}
    for file_id in file_ids:
        normalized = str(file_id or "").strip()
        if not normalized or normalized in seen_ids:
            continue
        seen_ids.add(normalized)
        file_pool.append(normalized)
    merged[key] = IndexSelection(mode="select", file_ids=file_pool)
    return merged


def _errors_indicate_already_indexed(errors: list[str]) -> bool:
    for row in errors:
        normalized = " ".join(str(row or "").split()).strip().lower()
        if "already indexed" in normalized:
            return True
    return False


def _resolve_existing_url_source_ids(
    *,
    context: ApiContext,
    user_id: str,
    index_id: int,
    urls: list[str],
) -> list[str]:
    try:
        index = context.get_index(index_id)
    except Exception:
        return []

    Source = index._resources["Source"]
    candidate_names: set[str] = set()
    for raw_url in urls:
        normalized = _normalize_http_url(raw_url)
        if not normalized:
            continue
        candidate_names.add(normalized)
        if normalized.endswith("/"):
            candidate_names.add(normalized.rstrip("/"))
        else:
            candidate_names.add(f"{normalized}/")
    if not candidate_names:
        return []

    with Session(engine) as session:
        statement = select(Source.id, Source.name).where(Source.name.in_(list(candidate_names)))
        if index.config.get("private", False):
            statement = statement.where(Source.user == user_id)
        rows = session.execute(statement).all()

    source_ids = [str(row[0]).strip() for row in rows if str(row[0]).strip()]
    return list(dict.fromkeys(source_ids))


def _source_ids_have_document_relations(
    *,
    context: ApiContext,
    index_id: int,
    source_ids: list[str],
) -> bool:
    cleaned_ids = [str(item).strip() for item in source_ids if str(item).strip()]
    if not cleaned_ids:
        return False
    try:
        index = context.get_index(index_id)
    except Exception:
        return False
    IndexTable = index._resources["Index"]
    with Session(engine) as session:
        row = session.execute(
            select(IndexTable.target_id)
            .where(
                IndexTable.source_id.in_(cleaned_ids),
                IndexTable.relation_type == "document",
            )
            .limit(1)
        ).first()
    return bool(row)


def _override_request_index_selection(
    request: ChatRequest,
    *,
    index_id: int,
    mode: str,
    file_ids: list[str] | None = None,
) -> dict[str, IndexSelection]:
    merged: dict[str, IndexSelection] = {}
    existing_selection = request.index_selection if isinstance(request.index_selection, dict) else {}
    for key, selected in existing_selection.items():
        selected_mode = str(getattr(selected, "mode", "all") or "all").strip().lower() or "all"
        selected_ids_raw = getattr(selected, "file_ids", [])
        selected_ids = [
            str(item).strip()
            for item in (selected_ids_raw if isinstance(selected_ids_raw, list) else [])
            if str(item).strip()
        ]
        merged[str(key)] = IndexSelection(mode=selected_mode, file_ids=selected_ids)
    normalized_mode = str(mode or "all").strip().lower()
    if normalized_mode not in {"all", "select", "disabled"}:
        normalized_mode = "all"
    normalized_ids = [
        str(item).strip()
        for item in (file_ids if isinstance(file_ids, list) else [])
        if str(item).strip()
    ]
    merged[str(index_id)] = IndexSelection(mode=normalized_mode, file_ids=normalized_ids)
    return merged


def _apply_url_grounded_index_selection(
    request: ChatRequest,
    *,
    index_id: int,
    file_ids: list[str],
    strict_url_grounding: bool,
) -> dict[str, IndexSelection]:
    cleaned_ids = [
        str(item).strip()
        for item in (file_ids if isinstance(file_ids, list) else [])
        if str(item).strip()
    ]
    if strict_url_grounding:
        # Keep the URL-scoped source set authoritative for this index so follow-up
        # questions stay grounded to the same website context.
        return _override_request_index_selection(
            request,
            index_id=index_id,
            mode="select",
            file_ids=cleaned_ids,
        )
    return _merge_request_index_selection(
        request,
        index_id=index_id,
        file_ids=cleaned_ids,
    )


def _auto_url_cache_key(
    *,
    user_id: str,
    index_id: int,
    urls: list[str],
) -> str:
    normalized_urls = [item for item in urls if item]
    normalized_urls = sorted(dict.fromkeys(normalized_urls))
    return f"{str(user_id or '').strip()}::{int(index_id)}::{'|'.join(normalized_urls)}"


def _auto_url_cache_get(
    *,
    user_id: str,
    index_id: int,
    urls: list[str],
    ttl_seconds: int,
) -> list[str] | None:
    if ttl_seconds <= 0:
        return None
    key = _auto_url_cache_key(user_id=user_id, index_id=index_id, urls=urls)
    now_ts = monotonic()
    with _AUTO_URL_CACHE_LOCK:
        cached = _AUTO_URL_INDEX_CACHE.get(key)
        if not cached:
            return None
        expires_at, file_ids = cached
        if now_ts >= float(expires_at):
            _AUTO_URL_INDEX_CACHE.pop(key, None)
            return None
        return [str(item).strip() for item in list(file_ids or []) if str(item).strip()]


def _auto_url_cache_put(
    *,
    user_id: str,
    index_id: int,
    urls: list[str],
    file_ids: list[str],
    ttl_seconds: int,
    max_entries: int,
) -> None:
    if ttl_seconds <= 0:
        return
    key = _auto_url_cache_key(user_id=user_id, index_id=index_id, urls=urls)
    cleaned_ids = [str(item).strip() for item in file_ids if str(item).strip()]
    if not cleaned_ids:
        return
    now_ts = monotonic()
    expires_at = now_ts + float(ttl_seconds)
    with _AUTO_URL_CACHE_LOCK:
        _AUTO_URL_INDEX_CACHE[key] = (expires_at, cleaned_ids)
        if len(_AUTO_URL_INDEX_CACHE) <= max_entries:
            return
        expired_keys = [
            cache_key
            for cache_key, (entry_expires_at, _entry_file_ids) in _AUTO_URL_INDEX_CACHE.items()
            if now_ts >= float(entry_expires_at)
        ]
        for cache_key in expired_keys:
            _AUTO_URL_INDEX_CACHE.pop(cache_key, None)
        overflow = len(_AUTO_URL_INDEX_CACHE) - max_entries
        if overflow <= 0:
            return
        for cache_key in list(_AUTO_URL_INDEX_CACHE.keys())[:overflow]:
            _AUTO_URL_INDEX_CACHE.pop(cache_key, None)


def _normalized_request_selection(request: ChatRequest) -> dict[str, IndexSelection]:
    normalized: dict[str, IndexSelection] = {}
    existing_selection = request.index_selection if isinstance(request.index_selection, dict) else {}
    for key, selected in existing_selection.items():
        mode = str(getattr(selected, "mode", "all") or "all").strip().lower() or "all"
        if mode not in {"all", "select", "disabled"}:
            mode = "all"
        selected_ids_raw = getattr(selected, "file_ids", [])
        selected_ids = [
            str(item).strip()
            for item in (selected_ids_raw if isinstance(selected_ids_raw, list) else [])
            if str(item).strip()
        ]
        normalized[str(key)] = IndexSelection(mode=mode, file_ids=selected_ids)
    return normalized


def _selected_index_ids_for_deep_search(
    *,
    request: ChatRequest,
    context: ApiContext,
) -> list[int]:
    selected_ids: list[int] = []
    for raw_key, selection in _normalized_request_selection(request).items():
        mode = str(getattr(selection, "mode", "all") or "all").strip().lower()
        if mode == "disabled":
            continue
        try:
            selected_ids.append(int(str(raw_key)))
        except Exception:
            continue
    if selected_ids:
        return list(dict.fromkeys(selected_ids))
    fallback_index = _first_available_index_id(context)
    return [fallback_index] if fallback_index is not None else []


def _apply_attachment_index_selection(
    *,
    context: ApiContext,
    request: ChatRequest,
) -> ChatRequest:
    attachments = _normalize_request_attachments(request)
    file_ids = [
        str(item.get("file_id") or "").strip()
        for item in attachments
        if isinstance(item, dict)
    ]
    file_ids = [item for item in file_ids if item]
    if not file_ids:
        return request

    index_id = _pick_target_index_id(request, context)
    if index_id is None:
        return request

    merged_selection = _merge_request_index_selection(
        request,
        index_id=index_id,
        file_ids=file_ids,
    )
    return _request_with_updates(request, {"index_selection": merged_selection})


def _list_index_source_ids(
    *,
    context: ApiContext,
    user_id: str,
    index_id: int,
    limit: int,
) -> list[str]:
    try:
        index = context.get_index(index_id)
    except Exception:
        return []
    Source = index._resources["Source"]
    bounded_limit = max(1, min(int(limit or 1), 1500))
    with Session(engine) as session:
        statement = select(Source.id).limit(bounded_limit)
        if index.config.get("private", False):
            statement = statement.where(Source.user == user_id)
        rows = session.execute(statement).all()
    source_ids = [str(row[0]).strip() for row in rows if str(row[0]).strip()]
    return list(dict.fromkeys(source_ids))
