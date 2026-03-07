from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from copy import deepcopy
from datetime import datetime
import re
import threading
from time import monotonic
from typing import Any, Generator
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlmodel import Session, select
from theflow.settings import settings as flowsettings
from tzlocal import get_localzone

from maia.base import Document

from ktem.db.models import engine
from ktem.pages.chat.common import STATE
from ktem.llms.manager import llms
from ktem.utils.commands import WEB_SEARCH_COMMAND

from api.context import ApiContext
from api.schemas import ChatRequest, IndexSelection
from api.services import mindmap_service
from api.services.agent.orchestrator import get_orchestrator
from api.services.agent.llm_runtime import call_json_response, env_bool
from api.services.settings_service import load_user_settings
from api.services.upload_service import index_urls

from .constants import API_CHAT_FAST_PATH, DEFAULT_SETTING, logger
from .citations import (
    append_required_citation_suffix,
    enforce_required_citations,
    normalize_info_evidence_html,
)
from .conversation_store import (
    build_selected_payload,
    get_or_create_conversation,
    maybe_autoname_conversation,
    persist_conversation,
)
from .fallbacks import build_extractive_timeout_answer, fallback_answer_from_exception
from .fast_qa import run_fast_chat_turn
from .info_panel_copy import build_info_panel_copy
from .pipeline import create_pipeline
from .streaming import (
    build_agent_context_window,
    chunk_text_for_stream,
    make_activity_stream_event,
)

_HTTP_URL_RE = re.compile(r"https?://[^\s\])>\"']+", flags=re.IGNORECASE)
_AUTO_URL_INDEX_MARKER = "__auto_url_indexed"
_AUTO_URL_CACHE_LOCK = threading.Lock()
_AUTO_URL_INDEX_CACHE: dict[str, tuple[float, list[str]]] = {}
_DEEP_SEARCH_MODE = "deep_search"
_ORCHESTRATOR_MODES = {"company_agent", _DEEP_SEARCH_MODE}
_DEEP_SEARCH_DEFAULT_WEB_SEARCH_BUDGET = 100
_DEEP_SEARCH_DEFAULT_SOURCE_LIMIT = 350
_DEEP_SEARCH_NORMAL_WEB_BUDGET = 100
_DEEP_SEARCH_COMPLEX_WEB_BUDGET = 180
_DEEP_SEARCH_NORMAL_MAX_QUERY_VARIANTS = 12
_DEEP_SEARCH_COMPLEX_MAX_QUERY_VARIANTS = 18
_DEEP_SEARCH_NORMAL_RESULTS_PER_QUERY = 10
_DEEP_SEARCH_COMPLEX_RESULTS_PER_QUERY = 12
_DEEP_SEARCH_NORMAL_MIN_UNIQUE_SOURCES = 50
_DEEP_SEARCH_COMPLEX_MIN_UNIQUE_SOURCES = 80
_DEEP_SEARCH_COMPLEXITY_VALUES = {"normal", "complex"}


def _default_model_looks_local_ollama() -> bool:
    try:
        default_name = str(llms.get_default_name() or "").strip()
    except Exception:
        return False
    if default_name.startswith("ollama::"):
        return True
    try:
        info = llms.info().get(default_name, {})
    except Exception:
        return False
    spec = info.get("spec", {}) if isinstance(info, dict) else {}
    if not isinstance(spec, dict):
        return False
    return str(spec.get("api_key") or "").strip().lower() == "ollama"


def _float_or_default(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        return float(default)
    if parsed != parsed:
        return float(default)
    return float(parsed)


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _is_orchestrator_mode(mode: str) -> bool:
    return str(mode or "").strip().lower() in _ORCHESTRATOR_MODES


def _truthy_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def _normalize_scope_phrase(value: Any) -> str:
    compact = " ".join(str(value or "").split()).strip().lower()
    if not compact:
        return ""
    normalized = re.sub(r"[^a-z0-9]+", " ", compact).strip()
    return normalized


def _prompt_mentions_phrase(prompt: str, phrase: str) -> bool:
    prompt_norm = _normalize_scope_phrase(prompt)
    phrase_norm = _normalize_scope_phrase(phrase)
    if not prompt_norm or not phrase_norm:
        return False
    if len(phrase_norm) < 3:
        return False
    if prompt_norm == phrase_norm:
        return True
    return f" {phrase_norm} " in f" {prompt_norm} "


def _source_row_looks_pdf(*, name: str, path: str, note: dict[str, Any]) -> bool:
    name_text = str(name or "").strip().lower()
    path_text = str(path or "").strip().lower()
    if name_text.endswith(".pdf") or path_text.endswith(".pdf"):
        return True
    loader = " ".join(str(note.get("loader") or "").split()).strip().lower()
    mime_type = " ".join(str(note.get("mime_type") or "").split()).strip().lower()
    return "pdf" in loader or mime_type == "application/pdf"


def _list_index_pdf_source_ids(
    *,
    context: ApiContext,
    user_id: str,
    index_id: int,
    limit: int,
    candidate_ids: list[str] | None = None,
) -> list[str]:
    try:
        index = context.get_index(index_id)
    except Exception:
        return []
    Source = index._resources.get("Source")
    if Source is None:
        return []
    bounded_limit = max(1, min(int(limit or 1), 1500))
    filtered_candidates = (
        list(dict.fromkeys([str(item).strip() for item in candidate_ids if str(item).strip()]))
        if isinstance(candidate_ids, list)
        else []
    )
    with Session(engine) as session:
        statement = select(Source)
        if filtered_candidates:
            statement = statement.where(Source.id.in_(filtered_candidates))
        if index.config.get("private", False):
            statement = statement.where(Source.user == user_id)
        rows = session.execute(statement).all()
    pdf_ids: list[str] = []
    for row in rows:
        source = row[0]
        source_id = str(getattr(source, "id", "") or "").strip()
        if not source_id:
            continue
        if not _source_row_looks_pdf(
            name=str(getattr(source, "name", "") or ""),
            path=str(getattr(source, "path", "") or ""),
            note=(getattr(source, "note", {}) if isinstance(getattr(source, "note", {}), dict) else {}),
        ):
            continue
        pdf_ids.append(source_id)
        if len(pdf_ids) >= bounded_limit:
            break
    return list(dict.fromkeys(pdf_ids))


def _list_named_group_file_ids(
    *,
    context: ApiContext,
    user_id: str,
    index_id: int,
    prompt: str,
    limit: int,
) -> tuple[bool, list[str]]:
    try:
        index = context.get_index(index_id)
    except Exception:
        return False, []
    FileGroup = index._resources.get("FileGroup")
    if FileGroup is None:
        return False, []
    bounded_limit = max(1, min(int(limit or 1), 1500))
    with Session(engine) as session:
        rows = session.execute(select(FileGroup).where(FileGroup.user == user_id)).all()
    matched_ids: list[str] = []
    matched_any_group = False
    for row in rows:
        group = row[0]
        group_name = str(getattr(group, "name", "") or "").strip()
        if not _prompt_mentions_phrase(prompt, group_name):
            continue
        matched_any_group = True
        group_data = getattr(group, "data", {})
        group_payload = group_data if isinstance(group_data, dict) else {}
        group_file_ids = [
            str(item).strip()
            for item in (group_payload.get("files") if isinstance(group_payload.get("files"), list) else [])
            if str(item).strip()
        ]
        for file_id in group_file_ids:
            matched_ids.append(file_id)
            if len(matched_ids) >= bounded_limit:
                break
        if len(matched_ids) >= bounded_limit:
            break
    return matched_any_group, list(dict.fromkeys(matched_ids))


def _mentioned_index_ids_in_prompt(
    *,
    context: ApiContext,
    prompt: str,
) -> list[int]:
    mentioned: list[int] = []
    indices = getattr(getattr(context, "app", None), "index_manager", None)
    raw_indices = getattr(indices, "indices", []) if indices is not None else []
    for index in raw_indices:
        index_id_raw = getattr(index, "id", None)
        try:
            index_id = int(index_id_raw)
        except Exception:
            continue
        candidates = [
            str(getattr(index, "name", "") or "").strip(),
            str((getattr(index, "config", {}) or {}).get("name") or "").strip(),
        ]
        if any(_prompt_mentions_phrase(prompt, candidate) for candidate in candidates if candidate):
            mentioned.append(index_id)
    return list(dict.fromkeys(mentioned))


def _resolve_prompt_scoped_pdf_ids(
    *,
    context: ApiContext,
    user_id: str,
    request: ChatRequest,
    limit: int,
) -> dict[int, list[str]]:
    prompt = str(request.message or "").strip()
    if not prompt:
        return {}
    selected_index_ids = _selected_index_ids_for_deep_search(request=request, context=context)
    mentioned_index_ids = _mentioned_index_ids_in_prompt(context=context, prompt=prompt)
    index_manager = getattr(getattr(context, "app", None), "index_manager", None)
    all_index_ids: list[int] = []
    for index in (getattr(index_manager, "indices", []) if index_manager is not None else []):
        try:
            all_index_ids.append(int(getattr(index, "id", 0)))
        except Exception:
            continue
    candidate_index_ids = list(
        dict.fromkeys(
            [
                *all_index_ids,
                *selected_index_ids,
                *mentioned_index_ids,
            ]
        )
    )
    scoped_ids: dict[int, list[str]] = {}
    for index_id in candidate_index_ids:
        matched_group, group_file_ids = _list_named_group_file_ids(
            context=context,
            user_id=user_id,
            index_id=index_id,
            prompt=prompt,
            limit=limit,
        )
        if matched_group:
            pdf_ids = _list_index_pdf_source_ids(
                context=context,
                user_id=user_id,
                index_id=index_id,
                candidate_ids=group_file_ids,
                limit=limit,
            )
            scoped_ids[index_id] = pdf_ids or group_file_ids[:limit]
            continue
        if index_id in mentioned_index_ids:
            pdf_ids = _list_index_pdf_source_ids(
                context=context,
                user_id=user_id,
                index_id=index_id,
                candidate_ids=None,
                limit=limit,
            )
            if pdf_ids:
                scoped_ids[index_id] = pdf_ids
    return scoped_ids


def _classify_deep_search_complexity(message: str) -> str:
    prompt = " ".join(str(message or "").split()).strip()
    if not prompt:
        return "normal"
    response = call_json_response(
        system_prompt=(
            "Classify deep-research request complexity. "
            "Return strict JSON only."
        ),
        user_prompt=(
            "Return JSON only in this schema:\n"
            '{ "complexity": "normal|complex", "reason": "short reason" }\n'
            "Rules:\n"
            "- Use `complex` when the request likely needs broad multi-angle coverage.\n"
            "- Otherwise use `normal`.\n\n"
            f"Request:\n{prompt}"
        ),
        temperature=0.0,
        timeout_seconds=8,
        max_tokens=140,
    )
    if isinstance(response, dict):
        complexity = " ".join(str(response.get("complexity") or "").split()).strip().lower()
        if complexity in _DEEP_SEARCH_COMPLEXITY_VALUES:
            return complexity
    # Deterministic fallback when LLM classification is unavailable.
    return "complex" if len(prompt) >= 260 else "normal"


def _mode_variant_from_request(*, request: ChatRequest, requested_mode: str) -> str:
    if str(requested_mode or "").strip().lower() != _DEEP_SEARCH_MODE:
        return ""
    setting_overrides = (
        dict(request.setting_overrides)
        if isinstance(request.setting_overrides, dict)
        else {}
    )
    if _truthy_flag(setting_overrides.get("__research_web_only")):
        return "web_search"
    return ""


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


def _should_auto_web_fallback(
    *,
    message: str,
    chat_history: list[list[str]],
) -> bool:
    if not env_bool("MAIA_CHAT_AUTO_WEB_FALLBACK_ENABLED", default=True):
        return False
    # Deterministic guard: explicit URL questions should route to web when fast local retrieval failed.
    if _HTTP_URL_RE.search(str(message or "")):
        return True
    # Deterministic guard: follow-up questions after a recent URL turn should
    # keep web retrieval enabled when fast local retrieval could not answer.
    for turn in reversed(chat_history[-4:]):
        if not isinstance(turn, list) or not turn:
            continue
        if _HTTP_URL_RE.search(str(turn[0] or "")):
            return True

    history_rows: list[str] = []
    for turn in chat_history[-4:]:
        if not isinstance(turn, list) or len(turn) < 2:
            continue
        user_text = " ".join(str(turn[0] or "").split())[:220]
        assistant_text = " ".join(str(turn[1] or "").split())[:220]
        if user_text or assistant_text:
            history_rows.append(f"User: {user_text}\nAssistant: {assistant_text}")
    history_text = "\n\n".join(history_rows) if history_rows else "(none)"

    prompt = (
        "Decide whether the next answer should route to live web retrieval.\n"
        "Return one JSON object only with this shape:\n"
        '{"route":"local|web","confidence":0.0,"reason":"short string"}\n'
        "Rules:\n"
        "- Choose route=web only when answering likely needs live/external web evidence beyond indexed project files and chat history.\n"
        "- Choose route=local when indexed project files + chat history are likely sufficient.\n"
        "- If uncertain, choose route=local.\n\n"
        f"Latest user message:\n{message}\n\n"
        f"Recent conversation:\n{history_text}"
    )
    response = call_json_response(
        system_prompt=(
            "You are Maia routing guard. "
            "Return strict JSON only."
        ),
        user_prompt=prompt,
        temperature=0.0,
        timeout_seconds=8,
        max_tokens=220,
    )
    if not isinstance(response, dict):
        return False

    route = " ".join(str(response.get("route") or "").split()).strip().lower()
    confidence = _float_or_default(response.get("confidence"), 0.0)
    min_confidence = _float_or_default(
        getattr(flowsettings, "MAIA_CHAT_AUTO_WEB_FALLBACK_MIN_CONFIDENCE", 0.55),
        0.55,
    )
    if route != "web":
        return False
    if confidence < max(0.0, min(1.0, min_confidence)):
        return False
    return True


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


def _apply_deep_search_defaults(
    *,
    context: ApiContext,
    user_id: str,
    request: ChatRequest,
) -> ChatRequest:
    if str(request.agent_mode or "").strip().lower() != _DEEP_SEARCH_MODE:
        return request

    existing_overrides = (
        dict(request.setting_overrides)
        if isinstance(request.setting_overrides, dict)
        else {}
    )
    max_source_ids = max(
        40,
        min(
            _int_or_default(
                existing_overrides.get("__deep_search_max_source_ids"),
                _DEEP_SEARCH_DEFAULT_SOURCE_LIMIT,
            ),
            1200,
        ),
    )
    requested_complexity = " ".join(
        str(existing_overrides.get("__deep_search_complexity") or "").split()
    ).strip().lower()
    complexity = (
        requested_complexity
        if requested_complexity in _DEEP_SEARCH_COMPLEXITY_VALUES
        else _classify_deep_search_complexity(request.message)
    )
    normal_mode = complexity != "complex"
    budget_floor = 60 if normal_mode else 120
    budget_default = (
        _DEEP_SEARCH_NORMAL_WEB_BUDGET if normal_mode else _DEEP_SEARCH_COMPLEX_WEB_BUDGET
    )
    requested_web_budget = max(
        budget_floor,
        min(
            _int_or_default(
                existing_overrides.get("__research_web_search_budget"),
                budget_default,
            ),
            350,
        ),
    )
    existing_overrides.setdefault("__deep_search_enabled", True)
    existing_overrides.setdefault("__llm_only_keyword_generation", True)
    existing_overrides.setdefault("__llm_only_keyword_generation_strict", True)
    existing_overrides.setdefault("__deep_search_complexity", complexity)
    existing_overrides.setdefault("__deep_search_max_source_ids", max_source_ids)
    existing_overrides.setdefault("__research_depth_tier", "deep_research")
    existing_overrides.setdefault("__research_web_search_budget", requested_web_budget)
    existing_overrides.setdefault(
        "__research_max_query_variants",
        (
            _DEEP_SEARCH_NORMAL_MAX_QUERY_VARIANTS
            if normal_mode
            else _DEEP_SEARCH_COMPLEX_MAX_QUERY_VARIANTS
        ),
    )
    existing_overrides.setdefault(
        "__research_results_per_query",
        (
            _DEEP_SEARCH_NORMAL_RESULTS_PER_QUERY
            if normal_mode
            else _DEEP_SEARCH_COMPLEX_RESULTS_PER_QUERY
        ),
    )
    existing_overrides.setdefault("__research_fused_top_k", 220)
    existing_overrides.setdefault(
        "__research_min_unique_sources",
        (
            _DEEP_SEARCH_NORMAL_MIN_UNIQUE_SOURCES
            if normal_mode
            else _DEEP_SEARCH_COMPLEX_MIN_UNIQUE_SOURCES
        ),
    )
    existing_overrides.setdefault(
        "__research_source_budget_min",
        60 if normal_mode else 120,
    )
    existing_overrides.setdefault(
        "__research_source_budget_max",
        100 if normal_mode else 180,
    )
    existing_overrides.setdefault("__file_research_source_budget_min", 120)
    existing_overrides.setdefault("__file_research_source_budget_max", 220)
    existing_overrides.setdefault("__file_research_max_sources", 220)
    existing_overrides.setdefault("__file_research_max_chunks", 1800)
    existing_overrides.setdefault("__file_research_max_scan_pages", 200)

    merged_selection = _normalized_request_selection(request)
    user_selected_files = any(
        str(getattr(selection, "mode", "") or "").strip().lower() == "select"
        and any(str(item).strip() for item in (getattr(selection, "file_ids", []) or []))
        for selection in merged_selection.values()
    )
    prompt_scoped_pdf_ids = _resolve_prompt_scoped_pdf_ids(
        context=context,
        user_id=user_id,
        request=request,
        limit=max_source_ids,
    )
    existing_overrides["__deep_search_prompt_scoped_pdfs"] = bool(prompt_scoped_pdf_ids)
    existing_overrides["__deep_search_user_selected_files"] = bool(user_selected_files)
    selected_index_ids = _selected_index_ids_for_deep_search(request=request, context=context)
    selected_index_ids = list(dict.fromkeys([*selected_index_ids, *prompt_scoped_pdf_ids.keys()]))
    for index_id in selected_index_ids:
        key = str(index_id)
        existing_selection = merged_selection.get(key)
        existing_ids = (
            [
                str(item).strip()
                for item in getattr(existing_selection, "file_ids", [])
                if str(item).strip()
            ]
            if existing_selection
            else []
        )
        scoped_ids = prompt_scoped_pdf_ids.get(index_id, [])
        auto_ids = (
            [
                str(item).strip()
                for item in scoped_ids
                if str(item).strip()
            ]
            if scoped_ids
            else _list_index_source_ids(
                context=context,
                user_id=user_id,
                index_id=index_id,
                limit=max_source_ids,
            )
        )
        merged_ids: list[str] = []
        seen: set[str] = set()
        for source_id in [*existing_ids, *auto_ids]:
            normalized = str(source_id).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged_ids.append(normalized)
            if len(merged_ids) >= max_source_ids:
                break
        if merged_ids:
            merged_selection[key] = IndexSelection(mode="select", file_ids=merged_ids)

    return _request_with_updates(
        request,
        {
            "index_selection": merged_selection,
            "setting_overrides": existing_overrides,
        },
    )


def _auto_index_urls_for_request(
    *,
    context: ApiContext,
    user_id: str,
    request: ChatRequest,
    settings: dict[str, Any] | None = None,
) -> ChatRequest:
    if not env_bool("MAIA_CHAT_AUTO_INDEX_URLS_ENABLED", default=True):
        return request
    if str(request.command or "").strip().lower() == str(WEB_SEARCH_COMMAND).strip().lower():
        return request
    existing_overrides = (
        dict(request.setting_overrides)
        if isinstance(request.setting_overrides, dict)
        else {}
    )
    if bool(existing_overrides.get(_AUTO_URL_INDEX_MARKER)):
        return request
    urls = _extract_message_urls(request.message, max_urls=8)
    if not urls:
        return request
    strict_url_grounding = env_bool("MAIA_CHAT_STRICT_URL_GROUNDING", default=True)

    target_index_id = _pick_target_index_id(request, context)
    if target_index_id is None:
        logger.warning("auto_url_indexing_skipped reason=no_target_index urls=%s", ",".join(urls[:3]))
        existing_overrides[_AUTO_URL_INDEX_MARKER] = True
        return _request_with_updates(request, {"setting_overrides": existing_overrides})

    cache_ttl_seconds = max(
        0,
        _int_or_default(
            getattr(flowsettings, "MAIA_CHAT_AUTO_INDEX_URLS_CACHE_TTL_SECONDS", 1800),
            1800,
        ),
    )
    cache_max_entries = max(
        1,
        _int_or_default(
            getattr(flowsettings, "MAIA_CHAT_AUTO_INDEX_URLS_CACHE_MAX_ENTRIES", 1024),
            1024,
        ),
    )
    cached_file_ids = _auto_url_cache_get(
        user_id=user_id,
        index_id=target_index_id,
        urls=urls,
        ttl_seconds=cache_ttl_seconds,
    )
    if cached_file_ids:
        merged_selection = _apply_url_grounded_index_selection(
            request,
            index_id=target_index_id,
            file_ids=cached_file_ids,
            strict_url_grounding=strict_url_grounding,
        )
        existing_overrides[_AUTO_URL_INDEX_MARKER] = True
        logger.warning(
            "auto_url_indexing_cache_hit index_id=%s urls=%s file_ids=%d",
            target_index_id,
            ",".join(urls[:3]),
            len(cached_file_ids),
        )
        return _request_with_updates(
            request,
            {
                "index_selection": merged_selection,
                "setting_overrides": existing_overrides,
            },
        )

    existing_source_ids = _resolve_existing_url_source_ids(
        context=context,
        user_id=user_id,
        index_id=target_index_id,
        urls=urls,
    )
    existing_sources_have_docs = (
        _source_ids_have_document_relations(
            context=context,
            index_id=target_index_id,
            source_ids=existing_source_ids,
        )
        if existing_source_ids
        else False
    )

    resolved_settings = settings if isinstance(settings, dict) else load_user_settings(context, user_id)
    auto_reindex = env_bool("MAIA_CHAT_AUTO_INDEX_URLS_REINDEX", default=False)
    auto_include_pdfs = env_bool("MAIA_CHAT_AUTO_INDEX_URLS_INCLUDE_PDFS", default=False)
    auto_include_images = env_bool("MAIA_CHAT_AUTO_INDEX_URLS_INCLUDE_IMAGES", default=False)
    auto_crawl_depth = max(
        0,
        _int_or_default(
            getattr(flowsettings, "MAIA_CHAT_AUTO_INDEX_URLS_CRAWL_DEPTH", 1),
            1,
        ),
    )
    auto_crawl_max_pages = max(
        0,
        _int_or_default(
            getattr(flowsettings, "MAIA_CHAT_AUTO_INDEX_URLS_MAX_PAGES", 4),
            4,
        ),
    )
    auto_timeout_seconds = max(
        6,
        _int_or_default(
            getattr(flowsettings, "MAIA_CHAT_AUTO_INDEX_URLS_TIMEOUT_SECONDS", 40),
            40,
        ),
    )

    if existing_source_ids and existing_sources_have_docs and not auto_reindex:
        _auto_url_cache_put(
            user_id=user_id,
            index_id=target_index_id,
            urls=urls,
            file_ids=existing_source_ids,
            ttl_seconds=cache_ttl_seconds,
            max_entries=cache_max_entries,
        )
        merged_selection = _apply_url_grounded_index_selection(
            request,
            index_id=target_index_id,
            file_ids=existing_source_ids,
            strict_url_grounding=strict_url_grounding,
        )
        existing_overrides[_AUTO_URL_INDEX_MARKER] = True
        logger.warning(
            "auto_url_indexing_reused_existing_sources index_id=%s urls=%s file_ids=%d",
            target_index_id,
            ",".join(urls[:3]),
            len(existing_source_ids),
        )
        return _request_with_updates(
            request,
            {
                "index_selection": merged_selection,
                "setting_overrides": existing_overrides,
            },
        )

    if existing_source_ids and not existing_sources_have_docs:
        auto_reindex = True
        logger.warning(
            "auto_url_indexing_stale_sources_no_docs index_id=%s urls=%s source_ids=%d",
            target_index_id,
            ",".join(urls[:3]),
            len(existing_source_ids),
        )

    logger.warning(
        "auto_url_indexing_start index_id=%s urls=%s reindex=%s crawl_depth=%d max_pages=%d include_pdfs=%s include_images=%s timeout_seconds=%d",
        target_index_id,
        ",".join(urls[:3]),
        str(bool(auto_reindex)).lower(),
        auto_crawl_depth,
        auto_crawl_max_pages,
        str(bool(auto_include_pdfs)).lower(),
        str(bool(auto_include_images)).lower(),
        auto_timeout_seconds,
    )
    started_at = monotonic()

    def _run_index_urls_call(*, reindex_flag: bool) -> dict[str, Any]:
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(
                index_urls,
                context=context,
                user_id=user_id,
                urls=urls,
                index_id=target_index_id,
                reindex=reindex_flag,
                settings=resolved_settings,
                web_crawl_depth=auto_crawl_depth,
                web_crawl_max_pages=auto_crawl_max_pages,
                web_crawl_same_domain_only=True,
                include_pdfs=auto_include_pdfs,
                include_images=auto_include_images,
                scope="chat_temp",
            )
            return future.result(timeout=auto_timeout_seconds)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    try:
        result = _run_index_urls_call(reindex_flag=auto_reindex)
    except FutureTimeoutError:
        timeout_source_ids = _resolve_existing_url_source_ids(
            context=context,
            user_id=user_id,
            index_id=target_index_id,
            urls=urls,
        )
        timeout_sources_have_docs = (
            _source_ids_have_document_relations(
                context=context,
                index_id=target_index_id,
                source_ids=timeout_source_ids,
            )
            if timeout_source_ids
            else False
        )
        if timeout_source_ids and timeout_sources_have_docs:
            _auto_url_cache_put(
                user_id=user_id,
                index_id=target_index_id,
                urls=urls,
                file_ids=timeout_source_ids,
                ttl_seconds=cache_ttl_seconds,
                max_entries=cache_max_entries,
            )
            merged_selection = _apply_url_grounded_index_selection(
                request,
                index_id=target_index_id,
                file_ids=timeout_source_ids,
                strict_url_grounding=strict_url_grounding,
            )
            existing_overrides[_AUTO_URL_INDEX_MARKER] = True
            logger.warning(
                "auto_url_indexing_timeout_reused_existing_sources index_id=%s urls=%s file_ids=%d timeout_seconds=%d",
                target_index_id,
                ",".join(urls[:3]),
                len(timeout_source_ids),
                auto_timeout_seconds,
            )
            return _request_with_updates(
                request,
                {
                    "index_selection": merged_selection,
                    "setting_overrides": existing_overrides,
                },
            )
        logger.warning(
            "auto_url_indexing_timeout index_id=%s urls=%s timeout_seconds=%d",
            target_index_id,
            ",".join(urls[:3]),
            auto_timeout_seconds,
        )
        existing_overrides[_AUTO_URL_INDEX_MARKER] = True
        updates: dict[str, Any] = {"setting_overrides": existing_overrides}
        if strict_url_grounding:
            updates["index_selection"] = _override_request_index_selection(
                request,
                index_id=target_index_id,
                mode="disabled",
                file_ids=[],
            )
        return _request_with_updates(request, updates)
    except Exception as exc:
        error_source_ids = _resolve_existing_url_source_ids(
            context=context,
            user_id=user_id,
            index_id=target_index_id,
            urls=urls,
        )
        error_sources_have_docs = (
            _source_ids_have_document_relations(
                context=context,
                index_id=target_index_id,
                source_ids=error_source_ids,
            )
            if error_source_ids
            else False
        )
        if error_source_ids and error_sources_have_docs:
            _auto_url_cache_put(
                user_id=user_id,
                index_id=target_index_id,
                urls=urls,
                file_ids=error_source_ids,
                ttl_seconds=cache_ttl_seconds,
                max_entries=cache_max_entries,
            )
            merged_selection = _apply_url_grounded_index_selection(
                request,
                index_id=target_index_id,
                file_ids=error_source_ids,
                strict_url_grounding=strict_url_grounding,
            )
            existing_overrides[_AUTO_URL_INDEX_MARKER] = True
            logger.warning(
                "auto_url_indexing_error_reused_existing_sources index_id=%s urls=%s file_ids=%d",
                target_index_id,
                ",".join(urls[:3]),
                len(error_source_ids),
            )
            return _request_with_updates(
                request,
                {
                    "index_selection": merged_selection,
                    "setting_overrides": existing_overrides,
                },
            )
        logger.warning(
            "auto_url_indexing_failed urls=%s error=%s",
            ",".join(urls[:3]),
            " ".join(str(exc).split())[:240],
        )
        existing_overrides[_AUTO_URL_INDEX_MARKER] = True
        updates = {"setting_overrides": existing_overrides}
        if strict_url_grounding:
            updates["index_selection"] = _override_request_index_selection(
                request,
                index_id=target_index_id,
                mode="disabled",
                file_ids=[],
            )
        return _request_with_updates(request, updates)

    file_ids = [
        str(item).strip()
        for item in (result.get("file_ids", []) if isinstance(result, dict) else [])
        if str(item).strip()
    ]
    error_rows = [
        " ".join(str(item or "").split()).strip()
        for item in (result.get("errors", []) if isinstance(result, dict) else [])
        if " ".join(str(item or "").split()).strip()
    ]
    if not file_ids and _errors_indicate_already_indexed(error_rows):
        existing_source_ids = _resolve_existing_url_source_ids(
            context=context,
            user_id=user_id,
            index_id=target_index_id,
            urls=urls,
        )
        if existing_source_ids and _source_ids_have_document_relations(
            context=context,
            index_id=target_index_id,
            source_ids=existing_source_ids,
        ):
            file_ids = existing_source_ids
            logger.warning(
                "auto_url_indexing_reused_existing_sources index_id=%s urls=%s file_ids=%d",
                target_index_id,
                ",".join(urls[:3]),
                len(file_ids),
            )
    if not file_ids:
        existing_source_ids = _resolve_existing_url_source_ids(
            context=context,
            user_id=user_id,
            index_id=target_index_id,
            urls=urls,
        )
        if existing_source_ids and _source_ids_have_document_relations(
            context=context,
            index_id=target_index_id,
            source_ids=existing_source_ids,
        ):
            file_ids = existing_source_ids
            logger.warning(
                "auto_url_indexing_reused_existing_sources_post_index index_id=%s urls=%s file_ids=%d",
                target_index_id,
                ",".join(urls[:3]),
                len(file_ids),
            )
    if not file_ids:
        logger.warning("auto_url_indexing_no_file_ids urls=%s", ",".join(urls[:3]))
        existing_overrides[_AUTO_URL_INDEX_MARKER] = True
        updates = {"setting_overrides": existing_overrides}
        if strict_url_grounding:
            updates["index_selection"] = _override_request_index_selection(
                request,
                index_id=target_index_id,
                mode="disabled",
                file_ids=[],
            )
        return _request_with_updates(request, updates)

    _auto_url_cache_put(
        user_id=user_id,
        index_id=target_index_id,
        urls=urls,
        file_ids=file_ids,
        ttl_seconds=cache_ttl_seconds,
        max_entries=cache_max_entries,
    )
    merged_selection = _apply_url_grounded_index_selection(
        request,
        index_id=target_index_id,
        file_ids=file_ids,
        strict_url_grounding=strict_url_grounding,
    )
    existing_overrides[_AUTO_URL_INDEX_MARKER] = True
    logger.warning(
        "auto_url_indexing_completed index_id=%s urls=%s file_ids=%d",
        target_index_id,
        ",".join(urls[:3]),
        len(file_ids),
    )
    elapsed_ms = int((monotonic() - started_at) * 1000)
    logger.warning(
        "auto_url_indexing_timing index_id=%s urls=%s elapsed_ms=%d",
        target_index_id,
        ",".join(urls[:3]),
        elapsed_ms,
    )
    return _request_with_updates(
        request,
        {
            "index_selection": merged_selection,
            "setting_overrides": existing_overrides,
        },
    )


def _read_persisted_workspace_ids(chat_state: dict[str, Any]) -> dict[str, str]:
    app_state = chat_state.get("app") if isinstance(chat_state, dict) else None
    app_rows = app_state if isinstance(app_state, dict) else {}
    return {
        "deep_research_doc_id": str(app_rows.get("deep_research_doc_id") or "").strip(),
        "deep_research_doc_url": str(app_rows.get("deep_research_doc_url") or "").strip(),
        "deep_research_sheet_id": str(app_rows.get("deep_research_sheet_id") or "").strip(),
        "deep_research_sheet_url": str(app_rows.get("deep_research_sheet_url") or "").strip(),
    }


def _capture_workspace_ids_from_actions(actions: list[Any]) -> dict[str, str]:
    captured = {
        "deep_research_doc_id": "",
        "deep_research_doc_url": "",
        "deep_research_sheet_id": "",
        "deep_research_sheet_url": "",
    }
    for action in reversed(actions or []):
        tool_id = str(getattr(action, "tool_id", "") or "").strip()
        status = str(getattr(action, "status", "") or "").strip().lower()
        if status != "success":
            continue
        metadata = getattr(action, "metadata", {})
        meta = metadata if isinstance(metadata, dict) else {}
        if not captured["deep_research_doc_id"] and tool_id == "workspace.docs.research_notes":
            captured["deep_research_doc_id"] = str(meta.get("document_id") or "").strip()
            captured["deep_research_doc_url"] = str(meta.get("document_url") or "").strip()
        if not captured["deep_research_sheet_id"] and tool_id in (
            "workspace.sheets.track_step",
            "workspace.sheets.append",
        ):
            captured["deep_research_sheet_id"] = str(meta.get("spreadsheet_id") or "").strip()
            captured["deep_research_sheet_url"] = str(meta.get("spreadsheet_url") or "").strip()
        if all(captured.values()):
            break
    return captured


def _extract_plot_from_actions(actions: list[Any]) -> dict[str, Any] | None:
    for action in reversed(actions or []):
        status = str(getattr(action, "status", "") or "").strip().lower()
        if status and status != "success":
            continue
        metadata = getattr(action, "metadata", {})
        if not isinstance(metadata, dict):
            continue
        plot = metadata.get("plot")
        if isinstance(plot, dict) and str(plot.get("kind") or "").strip().lower() == "chart":
            return dict(plot)
    return None


def stream_chat_turn(
    context: ApiContext,
    user_id: str,
    request: ChatRequest,
) -> Generator[dict[str, Any], None, dict[str, Any]]:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is empty.")

    settings = load_user_settings(context, user_id)
    request = _auto_index_urls_for_request(
        context=context,
        user_id=user_id,
        request=request,
        settings=settings,
    )
    request = _apply_deep_search_defaults(
        context=context,
        user_id=user_id,
        request=request,
    )
    message = request.message.strip()
    conversation_id, conversation_name, data_source, conversation_icon_key = get_or_create_conversation(
        user_id=user_id,
        conversation_id=request.conversation_id,
    )
    conversation_name, conversation_icon_key = maybe_autoname_conversation(
        user_id=user_id,
        conversation_id=conversation_id,
        current_name=conversation_name,
        message=message,
        agent_mode=request.agent_mode,
    )
    data_source = deepcopy(data_source or {})
    data_source["conversation_icon_key"] = conversation_icon_key

    chat_history = deepcopy(data_source.get("messages", []))
    chat_state = deepcopy(data_source.get("state", STATE))
    persisted_workspace_ids = _read_persisted_workspace_ids(chat_state)
    selected_payload = build_selected_payload(
        context=context,
        user_id=user_id,
        existing_selected=data_source.get("selected", {}),
        requested_selected=request.index_selection,
    )
    turn_attachments = _normalize_request_attachments(request)

    requested_mode = str(request.agent_mode or "").strip().lower() or "ask"
    mode_variant = _mode_variant_from_request(request=request, requested_mode=requested_mode)
    if _is_orchestrator_mode(requested_mode):
        orchestrator = get_orchestrator()
        agent_result = None
        last_activity_seq = 0
        context_snippets, context_summary = build_agent_context_window(
            chat_history=chat_history,
            latest_message=message,
            agent_goal=request.agent_goal,
        )
        agent_goal_parts = []
        existing_goal = " ".join(str(request.agent_goal or "").split()).strip()
        if existing_goal:
            agent_goal_parts.append(existing_goal)
        if requested_mode == "company_agent" and context_summary:
            agent_goal_parts.append(f"Conversation context: {context_summary}")
        contextual_goal = " ".join(agent_goal_parts).strip()[:900]
        agent_request = request
        if contextual_goal and contextual_goal != existing_goal:
            try:
                agent_request = agent_request.model_copy(update={"agent_goal": contextual_goal})
            except Exception:
                request_payload = agent_request.model_dump()
                request_payload["agent_goal"] = contextual_goal
                agent_request = ChatRequest(**request_payload)
        agent_settings = dict(settings)
        if isinstance(request.setting_overrides, dict):
            agent_settings.update(request.setting_overrides)
        if requested_mode == _DEEP_SEARCH_MODE:
            agent_settings["__deep_search_enabled"] = True
        if context_snippets:
            agent_settings["__conversation_snippets"] = context_snippets
        if context_summary:
            agent_settings["__conversation_summary"] = context_summary
        agent_settings["__conversation_latest_user_message"] = message
        if persisted_workspace_ids["deep_research_doc_id"]:
            agent_settings["__deep_research_doc_id"] = persisted_workspace_ids["deep_research_doc_id"]
        if persisted_workspace_ids["deep_research_doc_url"]:
            agent_settings["__deep_research_doc_url"] = persisted_workspace_ids["deep_research_doc_url"]
        if persisted_workspace_ids["deep_research_sheet_id"]:
            agent_settings["__deep_research_sheet_id"] = persisted_workspace_ids["deep_research_sheet_id"]
        if persisted_workspace_ids["deep_research_sheet_url"]:
            agent_settings["__deep_research_sheet_url"] = persisted_workspace_ids["deep_research_sheet_url"]
            agent_settings["__deep_research_sheet_header_written"] = True
        try:
            iterator = orchestrator.run_stream(
                user_id=user_id,
                conversation_id=conversation_id,
                request=agent_request,
                settings=agent_settings,
            )
            while True:
                event = next(iterator)
                if isinstance(event, dict):
                    if event.get("type") == "activity":
                        payload = event.get("event")
                        if isinstance(payload, dict):
                            seq_raw = payload.get("seq")
                            if isinstance(seq_raw, int):
                                last_activity_seq = max(last_activity_seq, seq_raw)
                            elif isinstance(seq_raw, str) and seq_raw.isdigit():
                                last_activity_seq = max(last_activity_seq, int(seq_raw))
                    yield event
        except StopIteration as stop:
            agent_result = stop.value
        except Exception as exc:
            logger.exception("Orchestrator execution failed: %s", exc)
            fallback = fallback_answer_from_exception(exc)
            agent_result = type(
                "_FallbackAgentResult",
                (),
                {
                    "run_id": "",
                    "answer": fallback,
                    "info_html": "",
                    "actions_taken": [],
                    "sources_used": [],
                    "evidence_items": [],
                    "next_recommended_steps": [],
                    "needs_human_review": False,
                    "human_review_notes": "",
                    "web_summary": {},
                },
            )()

        run_id_value = str(getattr(agent_result, "run_id", "") or "")
        if run_id_value:
            last_activity_seq += 1
            yield {
                "type": "activity",
                "event": make_activity_stream_event(
                    run_id=run_id_value,
                    event_type="response_writing",
                    title="Writing final response",
                    detail="Composing grounded answer from executed tool outputs",
                    seq=last_activity_seq,
                ),
            }

        answer_text = ""
        for delta in chunk_text_for_stream(agent_result.answer):
            answer_text += delta
            yield {
                "type": "chat_delta",
                "delta": delta,
                "text": answer_text,
            }

        if run_id_value:
            last_activity_seq += 1
            yield {
                "type": "activity",
                "event": make_activity_stream_event(
                    run_id=run_id_value,
                    event_type="response_written",
                    title="Response draft completed",
                    detail=f"Prepared {len(answer_text)} characters for delivery",
                    seq=last_activity_seq,
                ),
            }
        normalized_agent_info_html = normalize_info_evidence_html(
            str(getattr(agent_result, "info_html", "") or "")
        )
        if normalized_agent_info_html:
            yield {"type": "info_delta", "delta": normalized_agent_info_html}
        answer_text = enforce_required_citations(
            answer=answer_text,
            info_html=normalized_agent_info_html,
            citation_mode=request.citation,
        )
        plot_data = _extract_plot_from_actions(agent_result.actions_taken)
        if plot_data:
            yield {"type": "plot", "plot": plot_data}
        agent_web_summary = (
            dict(getattr(agent_result, "web_summary", {}))
            if isinstance(getattr(agent_result, "web_summary", {}), dict)
            else {}
        )
        mindmap_payload: dict[str, Any] = {}
        if bool(request.use_mindmap):
            agent_mindmap_settings = dict(request.mindmap_settings or {})
            try:
                requested_mindmap_depth = int(agent_mindmap_settings.get("max_depth", 4))
            except Exception:
                requested_mindmap_depth = 4
            requested_map_type = str(
                agent_mindmap_settings.get("map_type", "work_graph") or "work_graph"
            ).strip().lower()
            if requested_map_type not in {"structure", "evidence", "work_graph"}:
                requested_map_type = "work_graph"
            action_rows = [
                item.to_dict() if hasattr(item, "to_dict") else dict(item)
                for item in list(getattr(agent_result, "actions_taken", []) or [])
                if isinstance(item, dict) or hasattr(item, "to_dict")
            ]
            source_rows = [
                item.to_dict() if hasattr(item, "to_dict") else dict(item)
                for item in list(getattr(agent_result, "sources_used", []) or [])
                if isinstance(item, dict) or hasattr(item, "to_dict")
            ]
            if action_rows or source_rows:
                mindmap_payload = mindmap_service.build_agent_work_graph(
                    request_message=message,
                    actions_taken=action_rows,
                    sources_used=source_rows,
                    map_type=requested_map_type,
                    max_depth=max(2, min(8, requested_mindmap_depth)),
                    run_id=str(getattr(agent_result, "run_id", "") or ""),
                )
        info_panel = build_info_panel_copy(
            request_message=message,
            answer_text=answer_text,
            info_html=normalized_agent_info_html,
            mode=requested_mode,
            next_steps=list(getattr(agent_result, "next_recommended_steps", []) or []),
            web_summary=agent_web_summary,
        )
        raw_agent_evidence_items = getattr(agent_result, "evidence_items", [])
        if isinstance(raw_agent_evidence_items, list):
            normalized_evidence_items: list[dict[str, Any]] = []
            for row in raw_agent_evidence_items[:32]:
                if not isinstance(row, dict):
                    continue
                normalized_evidence_items.append(dict(row))
            if normalized_evidence_items:
                info_panel["evidence_items"] = normalized_evidence_items
        if mode_variant:
            info_panel["mode_variant"] = mode_variant
        if mindmap_payload:
            info_panel["mindmap"] = mindmap_payload

        chat_state.setdefault("app", {})
        chat_state["app"]["last_agent_run_id"] = agent_result.run_id
        captured_workspace_ids = _capture_workspace_ids_from_actions(agent_result.actions_taken)
        if captured_workspace_ids["deep_research_doc_id"]:
            chat_state["app"]["deep_research_doc_id"] = captured_workspace_ids["deep_research_doc_id"]
        if captured_workspace_ids["deep_research_doc_url"]:
            chat_state["app"]["deep_research_doc_url"] = captured_workspace_ids["deep_research_doc_url"]
        if captured_workspace_ids["deep_research_sheet_id"]:
            chat_state["app"]["deep_research_sheet_id"] = captured_workspace_ids["deep_research_sheet_id"]
        if captured_workspace_ids["deep_research_sheet_url"]:
            chat_state["app"]["deep_research_sheet_url"] = captured_workspace_ids["deep_research_sheet_url"]

        messages = chat_history + [[message, answer_text]]
        retrieval_history = deepcopy(data_source.get("retrieval_messages", []))
        retrieval_history.append(normalized_agent_info_html)
        plot_history = deepcopy(data_source.get("plot_history", []))
        plot_history.append(plot_data)
        message_meta = deepcopy(data_source.get("message_meta", []))
        message_meta.append(
            {
                "mode": requested_mode,
                "activity_run_id": agent_result.run_id or None,
                "actions_taken": [item.to_dict() for item in agent_result.actions_taken],
                "sources_used": [item.to_dict() for item in agent_result.sources_used],
                "source_usage": [],
                "attachments": turn_attachments,
                "next_recommended_steps": agent_result.next_recommended_steps,
                "needs_human_review": bool(getattr(agent_result, "needs_human_review", False)),
                "human_review_notes": str(getattr(agent_result, "human_review_notes", "") or "").strip() or None,
                "web_summary": agent_web_summary,
                "info_panel": info_panel,
                "mindmap": mindmap_payload,
            }
        )

        agent_runs = deepcopy(data_source.get("agent_runs", []))
        agent_runs.append(
            {
                "run_id": agent_result.run_id,
                "mode": request.agent_mode,
                "actions_taken": [item.to_dict() for item in agent_result.actions_taken],
                "sources_used": [item.to_dict() for item in agent_result.sources_used],
                "source_usage": [],
                "next_recommended_steps": agent_result.next_recommended_steps,
                "needs_human_review": bool(getattr(agent_result, "needs_human_review", False)),
                "human_review_notes": str(getattr(agent_result, "human_review_notes", "") or "").strip() or None,
                "web_summary": agent_web_summary,
                "date_created": datetime.now(get_localzone()).isoformat(),
            }
        )

        conversation_payload = {
            "selected": selected_payload,
            "messages": messages,
            "retrieval_messages": retrieval_history,
            "plot_history": plot_history,
            "message_meta": message_meta,
            "state": chat_state,
            "likes": deepcopy(data_source.get("likes", [])),
            "agent_runs": agent_runs,
        }
        persist_conversation(conversation_id, conversation_payload)

        return {
            "conversation_id": conversation_id,
            "conversation_name": conversation_name,
            "message": message,
            "answer": answer_text,
            "info": normalized_agent_info_html,
            "plot": plot_data,
            "state": chat_state,
            "mode": requested_mode,
            "actions_taken": [item.to_dict() for item in agent_result.actions_taken],
            "sources_used": [item.to_dict() for item in agent_result.sources_used],
            "source_usage": [],
            "next_recommended_steps": agent_result.next_recommended_steps,
            "needs_human_review": bool(getattr(agent_result, "needs_human_review", False)),
            "human_review_notes": str(getattr(agent_result, "human_review_notes", "") or "").strip() or None,
            "web_summary": agent_web_summary,
            "activity_run_id": agent_result.run_id,
            "info_panel": info_panel,
            "mindmap": mindmap_payload,
        }

    pipeline, reasoning_state, reasoning_id = create_pipeline(
        context=context,
        settings=settings,
        request=request,
        user_id=user_id,
        state=chat_state,
        selected_by_index=selected_payload,
    )

    answer_text = ""
    info_text = ""
    plot_data: dict[str, Any] | None = None
    mindmap_payload: dict[str, Any] = {}

    pipeline_error: Exception | None = None
    mindmap_settings = dict(request.mindmap_settings or {})
    try:
        requested_mindmap_depth = int(mindmap_settings.get("max_depth", 4))
    except Exception:
        requested_mindmap_depth = 4
    requested_map_type = str(mindmap_settings.get("map_type", "structure") or "structure").strip().lower()
    if requested_map_type not in {"structure", "evidence", "work_graph"}:
        requested_map_type = "structure"
    try:
        for response in pipeline.stream(
            message,
            conversation_id,
            chat_history,
            mindmap_focus=request.mindmap_focus if isinstance(request.mindmap_focus, dict) else {},
            mindmap_max_depth=max(2, min(8, requested_mindmap_depth)),
            include_reasoning_map=bool(mindmap_settings.get("include_reasoning_map", True)),
            mindmap_map_type=requested_map_type,
        ):
            if not isinstance(response, Document) or response.channel is None:
                continue

            if response.channel == "chat":
                if response.content is None:
                    # Some reasoning pipelines emit a reset signal before sending
                    # a canonical final answer (for example replacing streamed raw text
                    # with citation-linked text). Keep only the canonical answer.
                    answer_text = ""
                    continue
                delta = str(response.content or "")
                if delta:
                    answer_text += delta
                    yield {
                        "type": "chat_delta",
                        "delta": delta,
                        "text": answer_text,
                    }

            elif response.channel == "info":
                if isinstance(getattr(response, "metadata", None), dict):
                    parsed_mindmap = response.metadata.get("mindmap")
                    if isinstance(parsed_mindmap, dict) and not mindmap_payload:
                        mindmap_payload = parsed_mindmap
                        yield {"type": "mindmap", "mindmap": mindmap_payload}
                delta = response.content if response.content else ""
                if delta:
                    info_text += delta
                    yield {
                        "type": "info_delta",
                        "delta": delta,
                    }

            elif response.channel == "plot":
                plot_data = response.content
                yield {"type": "plot", "plot": plot_data}

            elif response.channel == "debug":
                text = response.text if response.text else str(response.content)
                if text:
                    yield {"type": "debug", "message": text}
    except HTTPException as exc:
        logger.exception("Chat pipeline raised HTTPException: %s", exc)
        pipeline_error = exc
    except Exception as exc:
        logger.exception("Chat pipeline raised Exception: %s", exc)
        pipeline_error = exc

    if pipeline_error is not None and not answer_text:
        answer_text = fallback_answer_from_exception(pipeline_error)
        yield {"type": "chat_delta", "delta": answer_text, "text": answer_text}

    if not answer_text:
        answer_text = getattr(
            flowsettings,
            "KH_CHAT_EMPTY_MSG_PLACEHOLDER",
            "(Sorry, I don't know)",
        )
        yield {"type": "chat_delta", "delta": answer_text, "text": answer_text}

    info_text = normalize_info_evidence_html(info_text)

    answer_with_citation_suffix = append_required_citation_suffix(answer=answer_text, info_html=info_text)
    if answer_with_citation_suffix != answer_text:
        if answer_with_citation_suffix.startswith(answer_text):
            delta = answer_with_citation_suffix[len(answer_text) :]
            answer_text = answer_with_citation_suffix
            if delta:
                yield {"type": "chat_delta", "delta": delta, "text": answer_text}
        else:
            answer_text = answer_with_citation_suffix
            yield {"type": "chat_delta", "delta": f"\n\n{answer_text}", "text": answer_text}
    info_panel = build_info_panel_copy(
        request_message=message,
        answer_text=answer_text,
        info_html=info_text,
        mode="ask",
        next_steps=[],
        web_summary={},
    )
    if mindmap_payload:
        info_panel["mindmap"] = mindmap_payload

    chat_state.setdefault("app", {})
    chat_state["app"].update(reasoning_state.get("app", {}))
    chat_state[reasoning_id] = reasoning_state.get("pipeline", {})

    messages = chat_history + [[message, answer_text]]
    retrieval_history = deepcopy(data_source.get("retrieval_messages", []))
    retrieval_history.append(info_text)
    plot_history = deepcopy(data_source.get("plot_history", []))
    plot_history.append(plot_data)
    message_meta = deepcopy(data_source.get("message_meta", []))
    message_meta.append(
        {
            "mode": "ask",
            "activity_run_id": None,
            "actions_taken": [],
            "sources_used": [],
            "source_usage": [],
            "attachments": turn_attachments,
            "next_recommended_steps": [],
            "needs_human_review": False,
            "human_review_notes": None,
            "web_summary": {},
            "info_panel": info_panel,
            "mindmap": mindmap_payload,
        }
    )

    conversation_payload = {
        "selected": selected_payload,
        "messages": messages,
        "retrieval_messages": retrieval_history,
        "plot_history": plot_history,
        "message_meta": message_meta,
        "state": chat_state,
        "likes": deepcopy(data_source.get("likes", [])),
    }
    persist_conversation(conversation_id, conversation_payload)

    return {
        "conversation_id": conversation_id,
        "conversation_name": conversation_name,
        "message": message,
        "answer": answer_text,
        "info": info_text,
        "plot": plot_data,
        "state": chat_state,
        "mode": "ask",
        "actions_taken": [],
        "sources_used": [],
        "source_usage": [],
        "next_recommended_steps": [],
        "needs_human_review": False,
        "human_review_notes": None,
        "web_summary": {},
        "activity_run_id": None,
        "info_panel": info_panel,
        "mindmap": mindmap_payload,
    }


def _resolve_chat_timeout_seconds(*, requested_mode: str) -> int:
    timeout_seconds = max(
        10,
        int(getattr(flowsettings, "KH_CHAT_TIMEOUT_SECONDS", 45) or 45),
    )
    mode = str(requested_mode or "").strip().lower()
    if mode == _DEEP_SEARCH_MODE:
        timeout_seconds = max(
            timeout_seconds,
            int(getattr(flowsettings, "KH_CHAT_TIMEOUT_SECONDS_DEEP_SEARCH", 600) or 600),
        )
    elif mode == "company_agent":
        timeout_seconds = max(
            timeout_seconds,
            int(getattr(flowsettings, "KH_CHAT_TIMEOUT_SECONDS_COMPANY_AGENT", 300) or 300),
        )
    if _default_model_looks_local_ollama():
        local_timeout = int(
            getattr(flowsettings, "KH_CHAT_TIMEOUT_SECONDS_LOCAL_OLLAMA", 180) or 180
        )
        timeout_seconds = max(timeout_seconds, local_timeout)
    return timeout_seconds


def run_chat_turn(context: ApiContext, user_id: str, request: ChatRequest) -> dict[str, Any]:
    request = _auto_index_urls_for_request(
        context=context,
        user_id=user_id,
        request=request,
        settings=None,
    )
    requested_mode = str(request.agent_mode or "").strip().lower() or "ask"
    if API_CHAT_FAST_PATH and not _is_orchestrator_mode(requested_mode):
        try:
            fast_result = run_fast_chat_turn(context=context, user_id=user_id, request=request)
            if fast_result is not None:
                logger.warning("chat_path_selected path=fast_qa")
                return fast_result
            if request.command in (None, "", DEFAULT_SETTING):
                try:
                    _conversation_id, _conversation_name, data_source, _conversation_icon_key = get_or_create_conversation(
                        user_id=user_id,
                        conversation_id=request.conversation_id,
                    )
                    chat_history = deepcopy(data_source.get("messages", []))
                except Exception:
                    chat_history = []
                if _should_auto_web_fallback(message=request.message, chat_history=chat_history):
                    request = _request_with_command(request, WEB_SEARCH_COMMAND)
                    logger.warning("chat_path_selected path=web_fallback_llm")
            logger.warning("chat_path_fallback reason=fast_qa_returned_none")
        except Exception as exc:
            logger.exception("Fast ask path failed; falling back to streaming pipeline: %s", exc)
    elif _is_orchestrator_mode(requested_mode):
        logger.warning("chat_path_selected path=%s", requested_mode)
    elif not API_CHAT_FAST_PATH:
        logger.warning("chat_path_fallback reason=fast_path_disabled")

    timeout_seconds = _resolve_chat_timeout_seconds(requested_mode=requested_mode)

    def consume_stream() -> dict[str, Any]:
        iterator = stream_chat_turn(context=context, user_id=user_id, request=request)
        try:
            while True:
                next(iterator)
        except StopIteration as stop:
            return stop.value

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(consume_stream)
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeoutError:
        message = request.message.strip()
        timeout_mode = requested_mode if _is_orchestrator_mode(requested_mode) else "ask"
        timeout_mode_variant = _mode_variant_from_request(request=request, requested_mode=timeout_mode)
        turn_attachments = _normalize_request_attachments(request)
        conversation_id, conversation_name, data_source, conversation_icon_key = get_or_create_conversation(
            user_id=user_id,
            conversation_id=request.conversation_id,
        )
        conversation_name, conversation_icon_key = maybe_autoname_conversation(
            user_id=user_id,
            conversation_id=conversation_id,
            current_name=conversation_name,
            message=message,
            agent_mode=request.agent_mode,
        )
        data_source = deepcopy(data_source or {})
        data_source["conversation_icon_key"] = conversation_icon_key
        timeout_answer, timeout_info = build_extractive_timeout_answer(
            context=context,
            user_id=user_id,
        )
        timeout_info = normalize_info_evidence_html(timeout_info)
        timeout_answer = enforce_required_citations(
            answer=timeout_answer,
            info_html=timeout_info,
            citation_mode=request.citation,
        )
        timeout_info_panel = build_info_panel_copy(
            request_message=message,
            answer_text=timeout_answer,
            info_html=timeout_info,
            mode=timeout_mode,
            next_steps=[],
            web_summary={},
        )
        if timeout_mode_variant:
            timeout_info_panel["mode_variant"] = timeout_mode_variant

        messages = deepcopy(data_source.get("messages", []))
        if message:
            messages.append([message, timeout_answer])
        retrieval_history = deepcopy(data_source.get("retrieval_messages", []))
        retrieval_history.append(timeout_info)
        plot_history = deepcopy(data_source.get("plot_history", []))
        plot_history.append(None)
        message_meta = deepcopy(data_source.get("message_meta", []))
        message_meta.append(
            {
                "mode": timeout_mode,
                "activity_run_id": None,
                "actions_taken": [],
                "sources_used": [],
                "source_usage": [],
                "attachments": turn_attachments,
                "next_recommended_steps": [],
                "needs_human_review": False,
                "human_review_notes": None,
                "web_summary": {},
                "info_panel": timeout_info_panel,
                "mindmap": {},
            }
        )

        conversation_payload = {
            "selected": deepcopy(data_source.get("selected", {})),
            "messages": messages,
            "retrieval_messages": retrieval_history,
            "plot_history": plot_history,
            "message_meta": message_meta,
            "state": deepcopy(data_source.get("state", STATE)),
            "likes": deepcopy(data_source.get("likes", [])),
        }
        persist_conversation(conversation_id, conversation_payload)

        return {
            "conversation_id": conversation_id,
            "conversation_name": conversation_name,
            "message": message,
            "answer": timeout_answer,
            "info": timeout_info,
            "plot": None,
            "state": deepcopy(data_source.get("state", STATE)),
            "mode": timeout_mode,
            "actions_taken": [],
            "sources_used": [],
            "source_usage": [],
            "next_recommended_steps": [],
            "needs_human_review": False,
            "human_review_notes": None,
            "web_summary": {},
            "activity_run_id": None,
            "info_panel": timeout_info_panel,
            "mindmap": {},
        }
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
