from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
import html
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import re
import json
import uuid
from typing import Any, Generator
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from decouple import config
from fastapi import HTTPException
from sqlmodel import Session, select
from theflow.settings import settings as flowsettings
from theflow.utils.modules import import_dotted_string
from tzlocal import get_localzone

from maia.base import Document

from ktem.components import reasonings
from ktem.db.models import Conversation, engine
from ktem.llms.manager import llms
from ktem.pages.chat.common import STATE
from ktem.utils.commands import WEB_SEARCH_COMMAND

from api.context import ApiContext
from api.schemas import ChatRequest
from api.services.agent.events import EVENT_SCHEMA_VERSION, infer_stage, infer_status
from api.services.agent.orchestrator import get_orchestrator
from api.services.settings_service import load_user_settings

DEFAULT_SETTING = "(default)"
logger = logging.getLogger(__name__)
PLACEHOLDER_KEYS = {
    "",
    "your-key",
    "<your_openai_key>",
    "changeme",
    "none",
    "null",
}
API_CHAT_FAST_PATH = config("MAIA_API_CHAT_FAST_PATH", default=True, cast=bool)
API_FAST_QA_MAX_IMAGES = config("MAIA_FAST_QA_MAX_IMAGES", default=2, cast=int)
API_FAST_QA_MAX_SNIPPETS = config("MAIA_FAST_QA_MAX_SNIPPETS", default=14, cast=int)
API_FAST_QA_SOURCE_SCAN = config("MAIA_FAST_QA_SOURCE_SCAN", default=120, cast=int)
API_FAST_QA_MAX_SOURCES = config("MAIA_FAST_QA_MAX_SOURCES", default=18, cast=int)
API_FAST_QA_MAX_CHUNKS_PER_SOURCE = config(
    "MAIA_FAST_QA_MAX_CHUNKS_PER_SOURCE", default=3, cast=int
)
API_FAST_QA_TEMPERATURE = config("MAIA_FAST_QA_TEMPERATURE", default=0.2, cast=float)


@lru_cache(maxsize=1)
def _get_web_search_cls():
    backend = getattr(flowsettings, "KH_WEB_SEARCH_BACKEND", None)
    if not backend:
        return None
    try:
        return import_dotted_string(backend, safe=False)
    except Exception:
        return None


def _get_or_create_conversation(
    user_id: str, conversation_id: str | None
) -> tuple[str, str, dict[str, Any]]:
    with Session(engine) as session:
        if conversation_id:
            conv = session.exec(
                select(Conversation).where(Conversation.id == conversation_id)
            ).first()
            if conv is None:
                raise HTTPException(status_code=404, detail="Conversation not found.")
            if conv.user != user_id and not conv.is_public:
                raise HTTPException(status_code=403, detail="Access denied.")
            return conv.id, conv.name, deepcopy(conv.data_source or {})

        conv = Conversation(user=user_id)
        session.add(conv)
        session.commit()
        session.refresh(conv)
        return conv.id, conv.name, {}


def _build_selected_payload(
    context: ApiContext,
    user_id: str,
    existing_selected: dict[str, Any],
    requested_selected: dict[str, Any],
) -> dict[str, list[Any]]:
    payload: dict[str, list[Any]] = {}

    for idx, index in enumerate(context.app.index_manager.indices):
        key = str(index.id)

        mode = "all" if idx == 0 else "disabled"
        selected_ids: list[str] = []

        existing = existing_selected.get(key)
        if isinstance(existing, list) and len(existing) >= 2:
            if isinstance(existing[0], str):
                mode = existing[0]
            if isinstance(existing[1], list):
                selected_ids = [str(item) for item in existing[1]]

        requested = requested_selected.get(key)
        if requested is not None:
            mode = requested.mode
            selected_ids = [str(item) for item in requested.file_ids]

        payload[key] = [mode, selected_ids, user_id]

    return payload


def _fallback_answer_from_exception(exc: Exception) -> str:
    text = str(exc)
    lowered = text.lower()
    if "api key" in lowered or "api_key_invalid" in lowered:
        return (
            "LLM is not configured with a valid API key yet. "
            "File indexing works, but chat generation is currently using fallback mode. "
            "Set a valid LLM key in settings to enable full AI answers."
        )
    if _llm_name_uses_placeholder_key(_default_llm_name()):
        return (
            "LLM is not configured with a valid API key yet. "
            "File indexing works, but chat generation is currently using fallback mode. "
            "Set a valid LLM key in settings to enable full AI answers."
        )

    return (
        "The chat model is currently unavailable. "
        "Please try again shortly or configure a valid LLM in settings."
    )


def _make_activity_stream_event(
    *,
    run_id: str,
    event_type: str,
    title: str,
    detail: str = "",
    metadata: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    seq: int = 0,
    stage: str | None = None,
    status: str | None = None,
    snapshot_ref: str | None = None,
) -> dict[str, Any]:
    payload_data = dict(data or {})
    if metadata:
        payload_data.update(metadata)
    ts = datetime.now(timezone.utc).isoformat()
    return {
        "event_schema_version": EVENT_SCHEMA_VERSION,
        "event_id": f"evt_stream_{uuid.uuid4().hex}",
        "run_id": run_id,
        "seq": max(0, int(seq)),
        "ts": ts,
        "type": event_type,
        "stage": stage or infer_stage(event_type),
        "status": status or infer_status(event_type),
        "event_type": event_type,
        "title": title,
        "detail": detail,
        "timestamp": ts,
        "data": payload_data,
        "snapshot_ref": snapshot_ref,
        "metadata": payload_data,
    }


def _is_placeholder_api_key(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    return value.strip().lower() in PLACEHOLDER_KEYS


@lru_cache(maxsize=64)
def _llm_name_uses_placeholder_key(llm_name: str) -> bool:
    if not llm_name:
        return True

    all_models = llms.info()
    if llm_name not in all_models:
        return True

    model_info = all_models.get(llm_name, {})
    model_spec = model_info.get("spec", {}) if isinstance(model_info, dict) else {}
    if not isinstance(model_spec, dict):
        return True

    saw_api_key_field = False
    for key, value in model_spec.items():
        if not isinstance(key, str):
            continue
        lowered_key = key.lower()
        if "api_key" in lowered_key:
            saw_api_key_field = True
            if _is_placeholder_api_key(value):
                return True

    # If model does not expose API key fields (e.g. local model), do not disable.
    return False


def _default_llm_name() -> str:
    try:
        return llms.get_default_name()
    except Exception:
        return ""


def _chunk_text_for_stream(text: str, chunk_size: int = 220) -> list[str]:
    if not text:
        return []
    size = max(32, int(chunk_size or 220))
    return [text[idx: idx + size] for idx in range(0, len(text), size)]


def _create_pipeline(
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

    if request.citation not in (None, DEFAULT_SETTING, ""):
        effective_settings["reasoning.options.simple.highlight_citation"] = request.citation

    if request.language not in (None, DEFAULT_SETTING, ""):
        effective_settings["reasoning.lang"] = request.language

    # Prevent background reranking threads from failing when the configured
    # LLM uses placeholder API keys.
    default_reranking_llm = _default_llm_name()
    for index in context.app.index_manager.indices:
        reranking_key = f"index.options.{index.id}.reranking_llm"
        reranking_llm_name = str(
            effective_settings.get(reranking_key, default_reranking_llm) or ""
        )
        if _llm_name_uses_placeholder_key(reranking_llm_name):
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
        web_search_cls = _get_web_search_cls()
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
            # to avoid embedding-query stalls during answer generation.
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


def _persist_conversation(
    conversation_id: str,
    payload: dict[str, Any],
) -> None:
    with Session(engine) as session:
        conv = session.exec(
            select(Conversation).where(Conversation.id == conversation_id)
        ).first()
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        conv.data_source = payload
        conv.date_updated = datetime.now(get_localzone())
        session.add(conv)
        session.commit()


def _build_extractive_timeout_answer(
    context: ApiContext,
    user_id: str,
) -> tuple[str, str]:
    """Return a local extractive fallback answer when full generation times out."""
    try:
        index = context.get_index(None)
        Source = index._resources["Source"]
        IndexTable = index._resources["Index"]
        doc_store = index._resources["DocStore"]
    except Exception:
        return (
            "The request timed out, and no local fallback context was available.",
            "",
        )

    source_row = None
    with Session(engine) as session:
        stmt = select(Source).order_by(Source.date_created.desc())  # type: ignore[attr-defined]
        if index.config.get("private", False):
            stmt = stmt.where(Source.user == user_id)
        source_row = session.execute(stmt).first()
        if not source_row:
            return (
                "The request timed out. No indexed files were found for fallback answering.",
                "",
            )
        source = source_row[0]
        source_id = source.id
        source_name = str(source.name)

        doc_id_stmt = (
            select(IndexTable.target_id)
            .where(
                IndexTable.source_id == source_id,
                IndexTable.relation_type == "document",
            )
            .limit(8)
        )
        doc_ids = [str(row[0]) for row in session.execute(doc_id_stmt).all()]

    if not doc_ids:
        return (
            f"The request timed out. I found file '{source_name}', but no indexed text chunks were available.",
            "",
        )

    try:
        docs = doc_store.get(doc_ids)
    except Exception:
        docs = []

    texts: list[str] = []
    for doc in docs or []:
        text = getattr(doc, "text", "") or ""
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            texts.append(text)
        if len(" ".join(texts)) >= 1200:
            break

    if not texts:
        return (
            f"The request timed out. I found file '{source_name}', but could not extract readable text for fallback answering.",
            "",
        )

    snippet = " ".join(texts)[:1200].strip()
    answer = (
        f"I could not finish full model generation in time. "
        f"Based on the latest indexed file '{source_name}', the content indicates: {snippet}"
    )
    info_html = (
        "<details class='evidence' open>"
        "<summary><i>Fallback retrieval</i></summary>"
        f"<div><b>Source:</b> {source_name}</div>"
        f"<div><b>Extract:</b> {snippet}</div>"
        "</details>"
    )
    return answer, info_html


def _load_recent_chunks_for_fast_qa(
    context: ApiContext,
    user_id: str,
    selected_payload: dict[str, list[Any]],
    query: str,
    max_sources: int = 48,
    max_chunks: int = 10,
) -> list[dict[str, Any]]:
    try:
        index = context.get_index(None)
        Source = index._resources["Source"]
        IndexTable = index._resources["Index"]
        doc_store = index._resources["DocStore"]
    except Exception:
        return []

    selected = selected_payload.get(str(index.id), ["all", [], user_id])
    mode = selected[0] if isinstance(selected, list) and selected else "all"
    selected_ids = selected[1] if isinstance(selected, list) and len(selected) > 1 else []
    selected_ids = [str(item) for item in selected_ids] if isinstance(selected_ids, list) else []

    source_ids: list[str] = []
    source_name_by_id: dict[str, str] = {}
    source_scan = max(1, int(max_sources))
    chunk_limit = max(1, int(max_chunks))
    with Session(engine) as session:
        if mode == "disabled":
            return []

        if mode == "select" and selected_ids:
            stmt = select(Source.id, Source.name).where(Source.id.in_(selected_ids))
            if index.config.get("private", False):
                stmt = stmt.where(Source.user == user_id)
            rows = session.execute(stmt).all()
            for row in rows:
                source_id = str(row[0])
                source_ids.append(source_id)
                source_name_by_id[source_id] = str(row[1])
        else:
            stmt = select(Source.id, Source.name).order_by(Source.date_created.desc())  # type: ignore[attr-defined]
            if index.config.get("private", False):
                stmt = stmt.where(Source.user == user_id)
            rows = session.execute(stmt.limit(source_scan)).all()
            for row in rows:
                source_id = str(row[0])
                source_ids.append(source_id)
                source_name_by_id[source_id] = str(row[1])

        if not source_ids:
            return []

        rel_stmt = (
            select(IndexTable.target_id, IndexTable.source_id)
            .where(
                IndexTable.relation_type == "document",
                IndexTable.source_id.in_(source_ids),
            )
            .limit(max(chunk_limit * 18, source_scan * 4))
        )
        rel_rows = session.execute(rel_stmt).all()

    if not rel_rows:
        return []

    target_to_source: dict[str, str] = {}
    target_ids: list[str] = []
    for target_id, source_id in rel_rows:
        target_key = str(target_id)
        source_key = str(source_id)
        target_to_source[target_key] = source_key
        target_ids.append(target_key)

    try:
        docs = doc_store.get(target_ids)
    except Exception:
        return []

    summary_intent = bool(
        re.search(
            r"\b(about|summary|summarize|overview|describe|explain|what is|what's)\b",
            query.lower(),
        )
    )
    stopwords = {
        "about",
        "document",
        "file",
        "pdf",
        "summary",
        "summarize",
        "overview",
        "describe",
        "this",
        "that",
        "what",
        "which",
        "with",
        "from",
        "tell",
    }
    query_terms = [
        t
        for t in re.findall(r"[a-zA-Z0-9]+", query.lower())
        if len(t) > 2 and t not in stopwords
    ][:16]

    scored_text: list[dict[str, Any]] = []
    image_by_source: dict[str, dict[str, Any]] = {}
    for doc in docs or []:
        doc_id = str(getattr(doc, "doc_id", "") or "")
        if not doc_id:
            continue

        metadata = getattr(doc, "metadata", {}) or {}
        doc_type = str(metadata.get("type", "") or "")
        page_label = str(metadata.get("page_label", "") or "")

        source_id = target_to_source.get(doc_id, "")
        source_name = str(metadata.get("file_name", "") or "") or source_name_by_id.get(
            source_id, "Indexed file"
        )
        source_name_lower = source_name.lower()
        source_key = source_id or f"name:{source_name}"

        image_origin = metadata.get("image_origin")
        if isinstance(image_origin, str) and image_origin.startswith("data:image/"):
            existing = image_by_source.get(source_key)
            if (
                existing is None
                or (doc_type == "thumbnail" and existing.get("doc_type") != "thumbnail")
            ):
                image_by_source[source_key] = {
                    "source_id": source_id,
                    "source_name": source_name,
                    "doc_type": doc_type,
                    "page_label": page_label,
                    "image_origin": image_origin,
                }

        raw_text = str(getattr(doc, "text", "") or "")
        text = re.sub(r"\s+", " ", raw_text).strip()
        if not text:
            continue
        if doc_type == "thumbnail" and len(text) <= 20:
            continue

        lowered = text.lower()
        score = sum(lowered.count(term) for term in query_terms)
        score += 4 * sum(source_name_lower.count(term) for term in query_terms)
        if doc_type == "ocr":
            score += 4
        elif doc_type == "table":
            score += 2
        elif doc_type == "image":
            score += 2
        if summary_intent:
            score += min(len(text) // 80, 10)
        if "pdf" in query_terms and source_name_lower.endswith(".pdf"):
            score += 8
        if source_name_lower.startswith("http://") or source_name_lower.startswith("https://"):
            score -= 1

        scored_text.append(
            {
                "score": score,
                "source_id": source_id,
                "source_key": source_key,
                "source_name": source_name,
                "text": text[:1200],
                "doc_type": doc_type,
                "page_label": page_label,
                "image_origin": image_by_source.get(source_key, {}).get("image_origin"),
            }
        )

    if not scored_text and not image_by_source:
        return []

    # Backfill image payload after full pass so ordering of thumbnail/text docs does not matter.
    for item in scored_text:
        if item.get("image_origin"):
            continue
        source_key = str(item.get("source_key", ""))
        item["image_origin"] = image_by_source.get(source_key, {}).get("image_origin")

    # For direct file-scoped queries, include broad context instead of strict keyword slices.
    if mode == "select" and selected_ids:
        scored_text.sort(
            key=lambda item: (
                item.get("source_name", ""),
                int(item.get("page_label") or 0),
                -len(str(item.get("text", ""))),
            )
        )
        selected_text = scored_text[: chunk_limit * 2]
    else:
        scored_text.sort(key=lambda item: int(item.get("score", 0)), reverse=True)
        source_cap = max(1, int(API_FAST_QA_MAX_CHUNKS_PER_SOURCE))
        max_distinct_sources = max(1, int(API_FAST_QA_MAX_SOURCES))
        selected_text = []
        per_source_count: dict[str, int] = {}
        for item in scored_text:
            source_key = str(item.get("source_key", ""))
            if not source_key:
                continue
            source_seen = source_key in per_source_count
            if not source_seen and len(per_source_count) >= max_distinct_sources:
                continue
            source_hits = per_source_count.get(source_key, 0)
            if source_hits >= source_cap:
                continue
            selected_text.append(item)
            per_source_count[source_key] = source_hits + 1
            if len(selected_text) >= chunk_limit:
                break
        if len(selected_text) < chunk_limit:
            for item in scored_text:
                if item in selected_text:
                    continue
                selected_text.append(item)
                if len(selected_text) >= chunk_limit:
                    break

    # Add image-only sources if no text was selected from that source.
    selected_sources = {str(item.get("source_key", "")) for item in selected_text}
    for source_key, image_payload in image_by_source.items():
        if source_key in selected_sources:
            continue
        selected_text.append(
            {
                "score": -1,
                "source_id": str(image_payload.get("source_id", "") or ""),
                "source_key": source_key,
                "source_name": str(image_payload.get("source_name", "") or "Indexed file"),
                "text": "Image evidence available for visual analysis.",
                "doc_type": str(image_payload.get("doc_type", "") or "thumbnail"),
                "page_label": str(image_payload.get("page_label", "") or ""),
                "image_origin": image_payload.get("image_origin"),
            }
        )

    return selected_text


def _assign_fast_source_refs(
    snippets: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ref_by_key: dict[tuple[str, str], int] = {}
    refs: list[dict[str, Any]] = []
    enriched: list[dict[str, Any]] = []

    for snippet in snippets:
        source_id = str(snippet.get("source_id", "") or "").strip()
        source_name = str(snippet.get("source_name", "Indexed file"))
        page_label = str(snippet.get("page_label", "") or "").strip()
        key = (source_id or source_name, page_label)
        ref_id = ref_by_key.get(key)
        if ref_id is None:
            ref_id = len(refs) + 1
            ref_by_key[key] = ref_id
            label = source_name
            if page_label:
                label += f" (page {page_label})"
            refs.append(
                {
                    "id": ref_id,
                    "source_id": source_id,
                    "source_name": source_name,
                    "page_label": page_label,
                    "label": label,
                }
            )

        enriched_item = dict(snippet)
        enriched_item["ref_id"] = ref_id
        enriched.append(enriched_item)

    return enriched, refs


def _render_fast_citation_links(
    answer: str,
    refs: list[dict[str, Any]],
    citation_mode: str | None,
) -> str:
    if not answer.strip():
        return answer

    mode = (citation_mode or "").strip().lower()
    if mode == "off":
        return answer

    ref_by_id: dict[int, dict[str, Any]] = {
        int(ref.get("id", 0) or 0): ref for ref in refs if int(ref.get("id", 0) or 0) > 0
    }
    max_ref = len(ref_by_id)

    def replace_ref(match: re.Match[str]) -> str:
        ref_num = int(match.group(1))
        if ref_num < 1 or ref_num > max_ref:
            return match.group(0)
        ref = ref_by_id.get(ref_num, {})
        file_id = str(ref.get("source_id", "") or "").strip()
        page_label = str(ref.get("page_label", "") or "").strip()
        attrs = [f"href='#evidence-{ref_num}'", f"id='citation-{ref_num}'", "class='citation'"]
        if file_id:
            attrs.append(f"data-file-id='{html.escape(file_id, quote=True)}'")
        if page_label:
            attrs.append(f"data-page='{html.escape(page_label, quote=True)}'")
        return (
            f"<a {' '.join(attrs)}>"
            f"[{ref_num}]</a>"
        )

    enriched = re.sub(r"\[(\d{1,3})\]", replace_ref, answer)

    if "class='citation'" in enriched or 'class="citation"' in enriched:
        return enriched

    if not refs:
        return enriched

    fallback_refs = " ".join(
        [
            (
                f"<a class='citation' href='#evidence-{ref['id']}' id='citation-{ref['id']}'"
                + (
                    f" data-file-id='{html.escape(str(ref.get('source_id', '') or ''), quote=True)}'"
                    if str(ref.get("source_id", "") or "").strip()
                    else ""
                )
                + (
                    f" data-page='{html.escape(str(ref.get('page_label', '') or ''), quote=True)}'"
                    if str(ref.get("page_label", "") or "").strip()
                    else ""
                )
                + f">[{ref['id']}]</a>"
            )
            for ref in refs[: min(3, len(refs))]
        ]
    )
    return f"{enriched}\n\nEvidence: {fallback_refs}"


def _normalize_fast_answer(answer: str) -> str:
    text = (answer or "").strip()
    if not text:
        return ""

    # Keep headings readable when models place them mid-line.
    text = re.sub(r"(?<!\n)(#{2,6}\s+)", r"\n\n\1", text)
    # Collapse duplicated heading markers like "### ## Title" into a single heading.
    text = re.sub(r"(^|\n)\s*#{1,6}\s*#{1,6}\s*", r"\1## ", text)

    # Remove malformed bold markers that often break markdown rendering.
    malformed_bold = bool(re.search(r"#{2,6}\s*\*\*|\*\*[^*]+-\s*\*\*", text))
    if malformed_bold or text.count("**") % 2 == 1:
        text = text.replace("**", "")

    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _call_openai_fast_qa(
    question: str,
    snippets: list[dict[str, Any]],
    chat_history: list[list[str]],
    refs: list[dict[str, Any]],
    citation_mode: str | None,
) -> str | None:
    api_key = str(config("OPENAI_API_KEY", default="") or "").strip()
    if _is_placeholder_api_key(api_key):
        return None

    base_url = str(config("OPENAI_API_BASE", default="https://api.openai.com/v1")) or "https://api.openai.com/v1"
    model = str(config("OPENAI_CHAT_MODEL", default="gpt-4o-mini")) or "gpt-4o-mini"

    context_blocks = []
    for snippet in snippets[:API_FAST_QA_MAX_SNIPPETS]:
        source_name = str(snippet.get("source_name", "Indexed file"))
        page_label = str(snippet.get("page_label", "") or "").strip()
        text = str(snippet.get("text", "") or "").strip()
        doc_type = str(snippet.get("doc_type", "") or "").strip()
        ref_id = int(snippet.get("ref_id", 0) or 0)
        header_parts = [f"Ref: [{ref_id}] Source: {source_name}"]
        if page_label:
            header_parts.append(f"Page: {page_label}")
        if doc_type:
            header_parts.append(f"Type: {doc_type}")
        context_blocks.append(f"{' | '.join(header_parts)}\nExcerpt: {text}")

    visual_evidence: list[tuple[str, str, str, int]] = []
    seen_images: set[str] = set()
    for snippet in snippets:
        source_name = str(snippet.get("source_name", "Indexed file"))
        page_label = str(snippet.get("page_label", "") or "")
        ref_id = int(snippet.get("ref_id", 0) or 0)
        image_origin = snippet.get("image_origin")
        if not isinstance(image_origin, str) or not image_origin.startswith("data:image/"):
            continue
        if image_origin in seen_images:
            continue
        seen_images.add(image_origin)
        visual_evidence.append((source_name, page_label, image_origin, ref_id))
        if len(visual_evidence) >= max(0, API_FAST_QA_MAX_IMAGES):
            break
    history_blocks = []
    for turn in chat_history[-3:]:
        if not isinstance(turn, list) or len(turn) < 2:
            continue
        history_blocks.append(f"User: {turn[0]}\nAssistant: {turn[1]}")

    history_text = "\n\n".join(history_blocks) if history_blocks else "(none)"
    context_text = "\n\n".join(context_blocks)
    refs_text = "\n".join(
        [f"[{ref['id']}] {ref['label']}" for ref in refs[: min(len(refs), 20)]]
    )
    overview_intent = bool(
        re.search(
            r"\b(what\s+is\s+this\s+(pdf|document)\s+about|what'?s\s+this\s+(pdf|document)\s+about|summary|summarize|overview)\b",
            question.lower(),
        )
    )
    mode = (citation_mode or "").strip().lower()
    if mode == "off":
        citation_instruction = "Citations are disabled for this response."
    elif mode == "footnote":
        citation_instruction = (
            "Keep the main paragraphs citation-free, then add a final 'Sources' section "
            "with refs in square brackets (for example [1], [2]) tied to the key claims."
        )
    else:
        citation_instruction = (
            "Cite factual claims with source refs in square brackets like [1], [2]. "
            "Every major claim should have at least one citation."
        )
    if overview_intent:
        output_instruction = (
            "Output format rules:\n"
            "- Start with a direct 1-2 sentence summary.\n"
            "- Choose the most useful structure for this question (short paragraphs, bullets, or a compact table).\n"
            "- Vary phrasing and headings naturally; do not force a repeated section template.\n"
            "- For transactional documents (receipt/invoice/statement), extract explicit fields first, then add a brief interpretation.\n"
            "- Distinguish confirmed facts from inference when confidence is limited.\n"
            "- If data is missing, say: Not visible in indexed content.\n"
            "- Use clean markdown and avoid malformed formatting."
        )
    else:
        output_instruction = (
            "Output format rules:\n"
            "- Answer directly in a concise professional style.\n"
            "- Use headings/bullets only when they improve clarity.\n"
            "- Avoid repeated template phrasing across turns.\n"
            "- Use clean markdown and avoid malformed formatting."
        )
    prompt = (
        "Use the provided indexed context to answer the user question in detail. "
        "When multiple sources are relevant, synthesize across them and call out agreements or differences. "
        "When a question asks what a PDF/image is about, adapt the structure to the document type and available evidence instead of a fixed template. "
        "If visual evidence is provided, use it to improve detail while clearly signaling assumptions. "
        f"{citation_instruction}\n\n"
        f"{output_instruction}\n\n"
        f"Source index:\n{refs_text or '(none)'}\n\n"
        f"Recent chat history:\n{history_text}\n\n"
        f"Indexed context:\n{context_text}\n\n"
        f"Question: {question}"
    )
    user_content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for source_name, page_label, image_origin, ref_id in visual_evidence:
        label = f"Visual evidence [{ref_id}] from {source_name}"
        if page_label:
            label += f" (page {page_label})"
        user_content.append({"type": "text", "text": label})
        user_content.append({"type": "image_url", "image_url": {"url": image_origin}})

    temperature = max(0.0, min(1.0, float(API_FAST_QA_TEMPERATURE)))

    try:
        request_payload = {
            "model": model,
            "temperature": temperature,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Maia. Provide faithful, high-detail answers from indexed evidence. "
                        "Adapt structure to the user's question and evidence; do not force fixed section templates. "
                        "Use concise sections and bullet points only when useful."
                    ),
                },
                {"role": "user", "content": user_content},
            ],
        }
        request = Request(
            f"{base_url.rstrip('/')}/chat/completions",
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            data=json.dumps(request_payload).encode("utf-8"),
        )
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        raw_answer = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
        if isinstance(raw_answer, list):
            answer_parts = []
            for part in raw_answer:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text" and part.get("text"):
                    answer_parts.append(str(part.get("text")))
            answer = "\n".join(answer_parts).strip()
        else:
            answer = str(raw_answer or "").strip()
        return answer or None
    except HTTPError:
        return None
    except Exception:
        return None


def _run_fast_chat_turn(
    context: ApiContext,
    user_id: str,
    request: ChatRequest,
) -> dict[str, Any] | None:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is empty.")
    if request.command not in (None, "", DEFAULT_SETTING):
        return None

    conversation_id, conversation_name, data_source = _get_or_create_conversation(
        user_id=user_id,
        conversation_id=request.conversation_id,
    )
    chat_history = deepcopy(data_source.get("messages", []))
    chat_state = deepcopy(data_source.get("state", STATE))

    selected_payload = _build_selected_payload(
        context=context,
        user_id=user_id,
        existing_selected=data_source.get("selected", {}),
        requested_selected=request.index_selection,
    )

    snippets = _load_recent_chunks_for_fast_qa(
        context=context,
        user_id=user_id,
        selected_payload=selected_payload,
        query=message,
        max_sources=max(API_FAST_QA_SOURCE_SCAN, API_FAST_QA_MAX_SOURCES),
        max_chunks=max(10, API_FAST_QA_MAX_SNIPPETS),
    )
    if not snippets:
        return None

    snippets_with_refs, refs = _assign_fast_source_refs(snippets)
    answer = _call_openai_fast_qa(
        question=message,
        snippets=snippets_with_refs,
        chat_history=chat_history,
        refs=refs,
        citation_mode=request.citation,
    )
    if not answer:
        return None
    answer = _normalize_fast_answer(answer)
    answer = _render_fast_citation_links(
        answer=answer,
        refs=refs,
        citation_mode=request.citation,
    )

    info_blocks: list[str] = []
    rendered_refs: set[int] = set()
    for snippet in snippets_with_refs:
        ref_id = int(snippet.get("ref_id", 0) or 0)
        if ref_id > 0 and ref_id in rendered_refs:
            continue
        if ref_id > 0:
            rendered_refs.add(ref_id)

        source_name = html.escape(str(snippet.get("source_name", "Indexed file")))
        page_label = html.escape(str(snippet.get("page_label", "") or ""))
        excerpt = html.escape(str(snippet.get("text", "") or "")[:1400])
        image_origin = snippet.get("image_origin")
        summary_label = f"Evidence [{ref_id}]" if ref_id > 0 else "Evidence"
        if page_label:
            summary_label += f" - page {page_label}"

        details_id = f" id='evidence-{ref_id}'" if ref_id > 0 else ""
        source_id = str(snippet.get("source_id", "") or "").strip()
        details_file_attr = (
            f" data-file-id='{html.escape(source_id, quote=True)}'" if source_id else ""
        )
        source_label = source_name
        if ref_id > 0:
            source_label = f"[{ref_id}] {source_name}"
        block = (
            f"<details class='evidence'{details_id}{details_file_attr} {'open' if not info_blocks else ''}>"
            f"<summary><i>{summary_label}</i></summary>"
            f"<div><b>Source:</b> {source_label}</div>"
            f"<div class='evidence-content'><b>Extract:</b> {excerpt}</div>"
        )
        if isinstance(image_origin, str) and image_origin.startswith("data:image/"):
            safe_src = html.escape(image_origin, quote=True)
            block += (
                "<figure>"
                f"<img src=\"{safe_src}\" alt=\"evidence image\"/>"
                "</figure>"
            )
        block += "</details>"
        info_blocks.append(block)
        if len(info_blocks) >= 6:
            break

    info_text = "".join(info_blocks)

    messages = chat_history + [[message, answer]]
    retrieval_history = deepcopy(data_source.get("retrieval_messages", []))
    retrieval_history.append(info_text)
    plot_history = deepcopy(data_source.get("plot_history", []))
    plot_history.append(None)
    message_meta = deepcopy(data_source.get("message_meta", []))
    message_meta.append(
        {
            "mode": "ask",
            "activity_run_id": None,
            "actions_taken": [],
            "sources_used": [],
            "next_recommended_steps": [],
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
    _persist_conversation(conversation_id, conversation_payload)

    return {
        "conversation_id": conversation_id,
        "conversation_name": conversation_name,
        "message": message,
        "answer": answer,
        "info": info_text,
        "plot": None,
        "state": chat_state,
        "mode": "ask",
        "actions_taken": [],
        "sources_used": [],
        "next_recommended_steps": [],
        "activity_run_id": None,
    }


def stream_chat_turn(
    context: ApiContext,
    user_id: str,
    request: ChatRequest,
) -> Generator[dict[str, Any], None, dict[str, Any]]:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is empty.")

    settings = load_user_settings(context, user_id)
    conversation_id, conversation_name, data_source = _get_or_create_conversation(
        user_id=user_id,
        conversation_id=request.conversation_id,
    )

    chat_history = deepcopy(data_source.get("messages", []))
    chat_state = deepcopy(data_source.get("state", STATE))
    selected_payload = _build_selected_payload(
        context=context,
        user_id=user_id,
        existing_selected=data_source.get("selected", {}),
        requested_selected=request.index_selection,
    )

    if request.agent_mode == "company_agent":
        orchestrator = get_orchestrator()
        agent_result = None
        last_activity_seq = 0
        try:
            iterator = orchestrator.run_stream(
                user_id=user_id,
                conversation_id=conversation_id,
                request=request,
                settings=settings,
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
            logger.exception("Company agent execution failed: %s", exc)
            fallback = _fallback_answer_from_exception(exc)
            agent_result = type(
                "_FallbackAgentResult",
                (),
                {
                    "run_id": "",
                    "answer": fallback,
                    "info_html": "",
                    "actions_taken": [],
                    "sources_used": [],
                    "next_recommended_steps": [],
                },
            )()

        run_id_value = str(getattr(agent_result, "run_id", "") or "")
        if run_id_value:
            last_activity_seq += 1
            yield {
                "type": "activity",
                "event": _make_activity_stream_event(
                    run_id=run_id_value,
                    event_type="response_writing",
                    title="Writing final response",
                    detail="Composing grounded answer from executed tool outputs",
                    seq=last_activity_seq,
                ),
            }

        answer_text = ""
        for delta in _chunk_text_for_stream(agent_result.answer):
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
                "event": _make_activity_stream_event(
                    run_id=run_id_value,
                    event_type="response_written",
                    title="Response draft completed",
                    detail=f"Prepared {len(answer_text)} characters for delivery",
                    seq=last_activity_seq,
                ),
            }
        if agent_result.info_html:
            yield {"type": "info_delta", "delta": agent_result.info_html}

        chat_state.setdefault("app", {})
        chat_state["app"]["last_agent_run_id"] = agent_result.run_id

        messages = chat_history + [[message, answer_text]]
        retrieval_history = deepcopy(data_source.get("retrieval_messages", []))
        retrieval_history.append(agent_result.info_html)
        plot_history = deepcopy(data_source.get("plot_history", []))
        plot_history.append(None)
        message_meta = deepcopy(data_source.get("message_meta", []))
        message_meta.append(
            {
                "mode": "company_agent",
                "activity_run_id": agent_result.run_id or None,
                "actions_taken": [item.to_dict() for item in agent_result.actions_taken],
                "sources_used": [item.to_dict() for item in agent_result.sources_used],
                "next_recommended_steps": agent_result.next_recommended_steps,
            }
        )

        agent_runs = deepcopy(data_source.get("agent_runs", []))
        agent_runs.append(
            {
                "run_id": agent_result.run_id,
                "mode": request.agent_mode,
                "actions_taken": [item.to_dict() for item in agent_result.actions_taken],
                "sources_used": [item.to_dict() for item in agent_result.sources_used],
                "next_recommended_steps": agent_result.next_recommended_steps,
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
        _persist_conversation(conversation_id, conversation_payload)

        return {
            "conversation_id": conversation_id,
            "conversation_name": conversation_name,
            "message": message,
            "answer": answer_text,
            "info": agent_result.info_html,
            "plot": None,
            "state": chat_state,
            "mode": "company_agent",
            "actions_taken": [item.to_dict() for item in agent_result.actions_taken],
            "sources_used": [item.to_dict() for item in agent_result.sources_used],
            "next_recommended_steps": agent_result.next_recommended_steps,
            "activity_run_id": agent_result.run_id,
        }

    pipeline, reasoning_state, reasoning_id = _create_pipeline(
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

    pipeline_error: Exception | None = None
    try:
        for response in pipeline.stream(message, conversation_id, chat_history):
            if not isinstance(response, Document) or response.channel is None:
                continue

            if response.channel == "chat":
                delta = response.content if response.content else ""
                if delta:
                    answer_text += delta
                    yield {
                        "type": "chat_delta",
                        "delta": delta,
                        "text": answer_text,
                    }

            elif response.channel == "info":
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
        pipeline_error = exc
    except Exception as exc:
        pipeline_error = exc

    if pipeline_error is not None and not answer_text:
        answer_text = _fallback_answer_from_exception(pipeline_error)
        yield {"type": "chat_delta", "delta": answer_text, "text": answer_text}

    if not answer_text:
        answer_text = getattr(
            flowsettings,
            "KH_CHAT_EMPTY_MSG_PLACEHOLDER",
            "(Sorry, I don't know)",
        )
        yield {"type": "chat_delta", "delta": answer_text, "text": answer_text}

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
            "next_recommended_steps": [],
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
    _persist_conversation(conversation_id, conversation_payload)

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
        "next_recommended_steps": [],
        "activity_run_id": None,
    }


def run_chat_turn(context: ApiContext, user_id: str, request: ChatRequest) -> dict[str, Any]:
    if API_CHAT_FAST_PATH and request.agent_mode != "company_agent":
        fast_result = _run_fast_chat_turn(context=context, user_id=user_id, request=request)
        if fast_result is not None:
            return fast_result

    timeout_seconds = int(getattr(flowsettings, "KH_CHAT_TIMEOUT_SECONDS", 45) or 45)

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
        conversation_id, conversation_name, data_source = _get_or_create_conversation(
            user_id=user_id,
            conversation_id=request.conversation_id,
        )
        timeout_answer, timeout_info = _build_extractive_timeout_answer(
            context=context,
            user_id=user_id,
        )

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
                "mode": "ask",
                "activity_run_id": None,
                "actions_taken": [],
                "sources_used": [],
                "next_recommended_steps": [],
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
        _persist_conversation(conversation_id, conversation_payload)

        return {
            "conversation_id": conversation_id,
            "conversation_name": conversation_name,
            "message": message,
            "answer": timeout_answer,
            "info": timeout_info,
            "plot": None,
            "state": deepcopy(data_source.get("state", STATE)),
            "mode": "ask",
            "actions_taken": [],
            "sources_used": [],
            "next_recommended_steps": [],
            "activity_run_id": None,
        }
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
