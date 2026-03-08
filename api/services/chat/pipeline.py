from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select
from theflow.settings import settings as flowsettings
from theflow.utils.modules import import_dotted_string

from ktem.components import reasonings
from ktem.db.models import engine
from ktem.llms.manager import llms
from ktem.pages.chat.common import STATE
from ktem.utils.commands import WEB_SEARCH_COMMAND

from api.context import ApiContext
from api.schemas import ChatRequest

from .citations import resolve_required_citation_mode
from .constants import DEFAULT_SETTING, PLACEHOLDER_KEYS, logger
from .language import build_response_language_rule, resolve_response_language

NON_TEMPLATED_RESPONSE_GUARD = (
    "Respond in a natural assistant style adapted to the user request and evidence. "
    "Avoid fixed/canned section templates and avoid repeating the same heading pattern across turns. "
    "Use headings, bullets, or tables only when they materially improve clarity."
)


@lru_cache(maxsize=1)
def get_web_search_cls():
    backend = getattr(flowsettings, "KH_WEB_SEARCH_BACKEND", None)
    if not backend:
        return None
    try:
        return import_dotted_string(backend, safe=False)
    except Exception:
        return None


def is_placeholder_api_key(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    return value.strip().lower() in PLACEHOLDER_KEYS


@lru_cache(maxsize=64)
def llm_name_uses_placeholder_key(llm_name: str) -> bool:
    if not llm_name:
        return True

    all_models = llms.info()
    if llm_name not in all_models:
        return True

    model_info = all_models.get(llm_name, {})
    model_spec = model_info.get("spec", {}) if isinstance(model_info, dict) else {}
    if not isinstance(model_spec, dict):
        return True

    for key, value in model_spec.items():
        if not isinstance(key, str):
            continue
        if "api_key" in key.lower() and is_placeholder_api_key(value):
            return True

    # If model does not expose API key fields (e.g. local model), do not disable.
    return False


def default_llm_name() -> str:
    try:
        return llms.get_default_name()
    except Exception:
        return ""


def create_pipeline(
    context: ApiContext,
    settings: dict[str, Any],
    request: ChatRequest,
    user_id: str,
    state: dict[str, Any],
    selected_by_index: dict[str, list[Any]],
):
    reasoning_mode = (
        settings.get("reasoning.use")
        if request.reasoning_type in (None, DEFAULT_SETTING, "")
        else request.reasoning_type
    )
    if reasoning_mode not in reasonings:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown reasoning type: {reasoning_mode}",
        )

    reasoning_cls = reasonings[reasoning_mode]
    reasoning_id = reasoning_cls.get_info()["id"]

    effective_settings = deepcopy(settings)
    effective_settings.update(request.setting_overrides)

    llm_setting_key = f"reasoning.options.{reasoning_id}.llm"
    if llm_setting_key in effective_settings and request.llm not in (
        None,
        DEFAULT_SETTING,
        "",
    ):
        effective_settings[llm_setting_key] = request.llm

    if request.use_mindmap is not None:
        effective_settings["reasoning.options.simple.create_mindmap"] = request.use_mindmap
    if isinstance(request.mindmap_settings, dict):
        if "max_depth" in request.mindmap_settings:
            try:
                max_depth = int(request.mindmap_settings.get("max_depth", 4))
            except Exception:
                max_depth = 4
            effective_settings["reasoning.options.simple.mindmap_max_depth"] = max(
                2, min(8, max_depth)
            )
        if "include_reasoning_map" in request.mindmap_settings:
            effective_settings["reasoning.options.simple.include_reasoning_map"] = bool(
                request.mindmap_settings.get("include_reasoning_map")
            )
        if "map_type" in request.mindmap_settings:
            parsed_map_type = str(request.mindmap_settings.get("map_type", "structure") or "structure").strip().lower()
            if parsed_map_type not in {"structure", "evidence", "work_graph", "context_mindmap"}:
                parsed_map_type = "structure"
            if parsed_map_type == "context_mindmap":
                parsed_map_type = "structure"
            effective_settings["reasoning.options.simple.mindmap_map_type"] = parsed_map_type

    configured_citation_mode = effective_settings.get("reasoning.options.simple.highlight_citation")
    citation_mode_input = request.citation
    if citation_mode_input in (None, DEFAULT_SETTING, ""):
        citation_mode_input = str(configured_citation_mode or "")
    effective_settings["reasoning.options.simple.highlight_citation"] = resolve_required_citation_mode(
        str(citation_mode_input or "")
    )

    resolved_response_language = resolve_response_language(
        request.language if request.language not in (None, DEFAULT_SETTING, "") else None,
        request.message,
    )
    if resolved_response_language:
        effective_settings["reasoning.lang"] = resolved_response_language
    elif request.language not in (None, DEFAULT_SETTING, ""):
        effective_settings["reasoning.lang"] = request.language

    system_prompt_key = f"reasoning.options.{reasoning_id}.system_prompt"
    existing_system_prompt = str(effective_settings.get(system_prompt_key, "") or "").strip()
    language_guard = build_response_language_rule(
        requested_language=request.language if request.language not in (None, DEFAULT_SETTING, "") else None,
        latest_message=request.message,
    )
    guard_fragments = [existing_system_prompt]
    lowered_prompt = existing_system_prompt.lower()
    if NON_TEMPLATED_RESPONSE_GUARD.lower() not in lowered_prompt:
        guard_fragments.append(NON_TEMPLATED_RESPONSE_GUARD)
    if "language rule:" not in lowered_prompt:
        guard_fragments.append(language_guard)
    effective_settings[system_prompt_key] = "\n".join([row for row in guard_fragments if row]).strip()

    # Prevent background reranking threads from failing when configured
    # LLM uses placeholder API keys.
    default_reranking_llm = default_llm_name()
    for index in context.app.index_manager.indices:
        reranking_key = f"index.options.{index.id}.reranking_llm"
        reranking_llm_name = str(
            effective_settings.get(reranking_key, default_reranking_llm) or ""
        )
        if llm_name_uses_placeholder_key(reranking_llm_name):
            effective_settings[f"index.options.{index.id}.use_llm_reranking"] = False

    retrievers = []

    def ensure_selector_proxy(index) -> None:
        if getattr(index, "_selector_ui", None) is not None:
            return

        class SelectorProxy:
            def __init__(self, wrapped_index):
                self._wrapped_index = wrapped_index

            def get_selected_ids(self, components):
                mode = "all"
                selected: list[str] = []
                selected_user_id = user_id

                if isinstance(components, list):
                    if len(components) > 0 and isinstance(components[0], str):
                        mode = components[0]
                    if len(components) > 1 and isinstance(components[1], list):
                        selected = [str(item) for item in components[1]]
                    if len(components) > 2 and components[2] is not None:
                        selected_user_id = str(components[2])

                if selected_user_id is None:
                    return []
                if mode == "disabled":
                    return []
                if mode == "select":
                    return selected

                Source = self._wrapped_index._resources["Source"]
                with Session(engine) as session:
                    statement = select(Source.id)
                    if self._wrapped_index.config.get("private", False):
                        statement = statement.where(Source.user == selected_user_id)
                    return [str(file_id) for (file_id,) in session.execute(statement).all()]

        index._selector_ui = SelectorProxy(index)

    if request.command == WEB_SEARCH_COMMAND:
        web_search_cls = get_web_search_cls()
        if web_search_cls is None:
            raise HTTPException(status_code=400, detail="Web search backend is not available.")
        retrievers.append(web_search_cls())
    else:
        for index in context.app.index_manager.indices:
            selected = selected_by_index.get(str(index.id), ["all", [], user_id])
            mode = selected[0] if isinstance(selected, list) and selected else "all"
            if mode == "disabled":
                continue

            # Prefer text retrieval in API mode for predictable latency and
            # avoid embedding-query stalls during answer generation.
            retrieval_mode_key = f"index.options.{index.id}.retrieval_mode"
            if retrieval_mode_key not in request.setting_overrides:
                effective_settings[retrieval_mode_key] = "text"
            use_reranking_key = f"index.options.{index.id}.use_reranking"
            if use_reranking_key not in request.setting_overrides:
                effective_settings[use_reranking_key] = False
            use_llm_reranking_key = f"index.options.{index.id}.use_llm_reranking"
            if use_llm_reranking_key not in request.setting_overrides:
                effective_settings[use_llm_reranking_key] = False
            num_retrieval_key = f"index.options.{index.id}.num_retrieval"
            if num_retrieval_key not in request.setting_overrides:
                effective_settings[num_retrieval_key] = 6

            ensure_selector_proxy(index)
            try:
                retrievers.extend(
                    index.get_retriever_pipelines(effective_settings, user_id, selected)
                )
            except Exception as exc:
                logger.warning(
                    "Skipping retrievers for index '%s' due to error: %s",
                    getattr(index, "name", index.id),
                    exc,
                )

    reasoning_state = {
        "app": deepcopy(state.get("app", STATE["app"])),
        "pipeline": deepcopy(state.get(reasoning_id, {})),
    }
    pipeline = reasoning_cls.get_pipeline(effective_settings, reasoning_state, retrievers)
    return pipeline, reasoning_state, reasoning_id
