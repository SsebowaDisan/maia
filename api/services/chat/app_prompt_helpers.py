from __future__ import annotations

import re
from typing import Any

from sqlmodel import Session, select

from api.context import ApiContext
from api.schemas import ChatRequest
from api.services.agent.llm_runtime import call_json_response

from ktem.db.models import engine
from ktem.llms.manager import llms

from .app_index_helpers import _selected_index_ids_for_deep_search

_DEEP_SEARCH_MODE = "deep_search"
_ORCHESTRATOR_MODES = {"company_agent", _DEEP_SEARCH_MODE, "brain"}
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
    normalized_mode = str(requested_mode or "").strip().lower()
    setting_overrides = (
        dict(request.setting_overrides)
        if isinstance(request.setting_overrides, dict)
        else {}
    )
    if normalized_mode == "ask" and _truthy_flag(setting_overrides.get("__rag_mode_enabled")):
        return "rag"
    if normalized_mode != _DEEP_SEARCH_MODE:
        return ""
    if _truthy_flag(setting_overrides.get("__research_web_only")):
        return "web_search"
    return ""
