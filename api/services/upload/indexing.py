from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from pathlib import Path
import threading
from typing import Any, Callable

import httpx
from fastapi import HTTPException

from api.context import ApiContext
from api.services.observability.citation_trace import record_trace_event

from .common import get_index, normalize_ids, normalize_upload_scope
from .indexing_config import *
from . import indexing_ops_helpers as _ops_helpers
from . import indexing_paddle_helpers as _paddle_helpers
from . import indexing_pdf_page_helpers as _page_helpers
from . import indexing_pdf_route_helpers as _route_helpers
from . import indexing_startup_helpers as _startup_helpers
from .pdf_highlight_locator import precompute_page_units_background

_PADDLE_OCR_ENGINE: Any | None = None
_PADDLE_OCR_LOCK = threading.Lock()
_PADDLE_OCR_REF: dict[str, Any] = {"engine": None}
_source_ids_have_document_relations = _ops_helpers.source_ids_have_document_relations_impl

# Content-hash-keyed classification cache.
# Keyed on SHA256 of the uploaded file so re-uploads of identical PDFs skip
# the expensive pypdf + fitz classification pass entirely.
_PDF_HASH_CACHE: dict[str, dict[str, Any]] = {}
_PDF_HASH_CACHE_LOCK = threading.Lock()
_PDF_HASH_CACHE_MAX = 256

def _is_paddle_runtime_expected() -> bool:
    return _startup_helpers.is_paddle_runtime_expected_impl(
        reader_mode=UPLOAD_INDEX_READER_MODE,
        paddleocr_enabled=UPLOAD_PADDLEOCR_ENABLED,
        paddleocr_vl_api_enabled=UPLOAD_PADDLEOCR_VL_API_ENABLED,
    )

def _is_vlm_runtime_expected() -> bool:
    return _startup_helpers.is_vlm_runtime_expected_impl(
        review_enabled=UPLOAD_PDF_VLM_REVIEW_ENABLED,
        extract_enabled=UPLOAD_PDF_VLM_EXTRACT_ENABLED,
    )

def _run_vlm_startup_checks() -> list[str]:
    return _startup_helpers.run_vlm_startup_checks_impl(
        startup_check=UPLOAD_PDF_VLM_STARTUP_CHECK,
        startup_strict=UPLOAD_PDF_VLM_STARTUP_STRICT,
        review_enabled=UPLOAD_PDF_VLM_REVIEW_ENABLED,
        extract_enabled=UPLOAD_PDF_VLM_EXTRACT_ENABLED,
        review_model=UPLOAD_PDF_VLM_REVIEW_MODEL,
        extract_model=UPLOAD_PDF_VLM_EXTRACT_MODEL,
        base_url=UPLOAD_PDF_VLM_BASE_URL,
        logger_warning=logger.info,
    )

def run_upload_startup_checks() -> list[str]:
    notices = _run_paddle_startup_checks()
    notices.extend(_run_vlm_startup_checks())
    return notices

def _run_paddle_startup_checks() -> list[str]:
    return _startup_helpers.run_paddle_startup_checks_impl(
        startup_check=UPLOAD_PADDLEOCR_STARTUP_CHECK,
        startup_strict=UPLOAD_PADDLEOCR_STARTUP_STRICT,
        startup_warmup=UPLOAD_PADDLEOCR_STARTUP_WARMUP,
        reader_mode=UPLOAD_INDEX_READER_MODE,
        is_paddle_runtime_expected=_is_paddle_runtime_expected(),
        paddleocr_vl_api_enabled=UPLOAD_PADDLEOCR_VL_API_ENABLED,
        paddleocr_vl_api_url=UPLOAD_PADDLEOCR_VL_API_URL,
        paddleocr_vl_api_token=UPLOAD_PADDLEOCR_VL_API_TOKEN,
        paddleocr_vl_api_verify_ssl=UPLOAD_PADDLEOCR_VL_API_VERIFY_SSL,
        paddleocr_vl_api_ca_bundle=UPLOAD_PADDLEOCR_VL_API_CA_BUNDLE,
        get_paddle_ocr_engine_fn=_get_paddle_ocr_engine,
        logger_warning=logger.info,
    )


_page_has_images = _page_helpers.page_has_images_impl
_sample_page_indexes = _page_helpers.sample_page_indexes_impl
_normalize_page_indexes = _page_helpers.normalize_page_indexes_impl
_ollama_timeout = _page_helpers.ollama_timeout_impl
_extract_json_object = _page_helpers.extract_json_object_impl
_dedupe_text_lines = _page_helpers.dedupe_text_lines_impl
_merge_text_lines = lambda primary, extra: _page_helpers.merge_text_lines_impl(
    primary,
    extra,
    dedupe_text_lines_fn=_dedupe_text_lines,
)

def _count_image_pages(
    pages: list[Any],
    page_indexes: list[int] | None = None,
    skip_edge_pages: int = 0,
) -> int:
    return _page_helpers.count_image_pages_impl(
        pages,
        page_has_images_fn=_page_has_images,
        page_indexes=page_indexes,
        skip_edge_pages=skip_edge_pages,
    )

def _detect_pdf_images_with_pymupdf(
    path: Path,
    *,
    page_indexes: list[int] | None = None,
    skip_edge_pages: int = 0,
) -> tuple[set[int], int]:
    return _page_helpers.detect_pdf_images_with_pymupdf_impl(
        path,
        normalize_page_indexes_fn=_normalize_page_indexes,
        page_indexes=page_indexes,
        skip_edge_pages=skip_edge_pages,
    )

def _parse_vlm_classifier_response(text: str) -> dict[str, Any]:
    return _page_helpers.parse_vlm_classifier_response_impl(
        text,
        extract_json_object_fn=_extract_json_object,
    )

def _extract_text_lines_from_vlm_response(text: str) -> list[str]:
    return _page_helpers.extract_text_lines_from_vlm_response_impl(
        text,
        extract_json_object_fn=_extract_json_object,
        dedupe_text_lines_fn=_dedupe_text_lines,
    )

def _run_ollama_vlm_for_image(
    *,
    client: httpx.Client,
    model: str,
    prompt: str,
    image_path: Path,
) -> str:
    return _page_helpers.run_ollama_vlm_for_image_impl(
        client=client,
        model=model,
        prompt=prompt,
        image_path=image_path,
        base_url=UPLOAD_PDF_VLM_BASE_URL,
    )

def _review_pdf_route_with_vlm(
    path: Path,
    *,
    total_pages_hint: int,
    sampled_indexes: list[int] | None = None,
) -> dict[str, Any]:
    return _route_helpers.review_pdf_route_with_vlm_impl(
        path,
        total_pages_hint=total_pages_hint,
        sampled_indexes=sampled_indexes,
        review_enabled=UPLOAD_PDF_VLM_REVIEW_ENABLED,
        review_max_pages=UPLOAD_PDF_VLM_REVIEW_MAX_PAGES,
        review_render_dpi=UPLOAD_PDF_VLM_REVIEW_RENDER_DPI,
        review_timeout_seconds=UPLOAD_PDF_VLM_REVIEW_TIMEOUT_SECONDS,
        review_model=UPLOAD_PDF_VLM_REVIEW_MODEL,
        base_url=UPLOAD_PDF_VLM_BASE_URL,
        normalize_page_indexes_fn=_normalize_page_indexes,
        sample_page_indexes_fn=_sample_page_indexes,
        ollama_timeout_fn=_ollama_timeout,
        run_ollama_vlm_for_image_fn=_run_ollama_vlm_for_image,
        parse_vlm_classifier_response_fn=_parse_vlm_classifier_response,
    )

def _apply_vlm_review_upgrade(
    path: Path,
    classification: dict[str, Any],
    *,
    sampled_indexes: list[int] | None = None,
) -> dict[str, Any]:
    return _route_helpers.apply_vlm_review_upgrade_impl(
        path,
        classification,
        sampled_indexes=sampled_indexes,
        review_enabled=UPLOAD_PDF_VLM_REVIEW_ENABLED,
        review_pdf_route_with_vlm_fn=_review_pdf_route_with_vlm,
    )


@lru_cache(maxsize=256)
def _classify_pdf_ingestion_route_cached(
    resolved_path: str,
    modified_ns: int,
    file_size: int,
) -> dict[str, Any]:
    return _route_helpers.classify_pdf_ingestion_route_cached_impl(
        resolved_path,
        modified_ns,
        file_size,
        policy=UPLOAD_PDF_OCR_POLICY,
        scan_pages=UPLOAD_PDF_OCR_SCAN_PAGES,
        min_text_chars_per_page=UPLOAD_PDF_OCR_MIN_TEXT_CHARS_PER_PAGE,
        very_low_text_chars_per_page=UPLOAD_PDF_OCR_VERY_LOW_TEXT_CHARS_PER_PAGE,
        min_low_text_page_ratio=UPLOAD_PDF_OCR_MIN_LOW_TEXT_PAGE_RATIO,
        min_image_page_ratio=UPLOAD_PDF_OCR_MIN_IMAGE_PAGE_RATIO,
        trigger_any_image_low_text_page=UPLOAD_PDF_OCR_TRIGGER_ON_ANY_IMAGE_LOW_TEXT_PAGE,
        trigger_any_very_low_text_page=UPLOAD_PDF_OCR_TRIGGER_ON_ANY_VERY_LOW_TEXT_PAGE,
        min_image_pages_full_scan=UPLOAD_PDF_OCR_MIN_IMAGE_PAGES_FULL_SCAN,
        trigger_any_image_page_full_scan=UPLOAD_PDF_OCR_TRIGGER_ON_ANY_IMAGE_PAGE_FULL_SCAN,
        skip_edge_pages=UPLOAD_PDF_OCR_SKIP_EDGE_PAGES,
        min_image_page_ratio_full_scan=UPLOAD_PDF_OCR_MIN_IMAGE_PAGE_RATIO_FULL_SCAN,
        heavy_min_image_page_ratio=UPLOAD_PDF_HEAVY_MIN_IMAGE_PAGE_RATIO,
        heavy_min_low_text_page_ratio=UPLOAD_PDF_HEAVY_MIN_LOW_TEXT_PAGE_RATIO,
        heavy_on_any_image_page=UPLOAD_PDF_HEAVY_ON_ANY_IMAGE_PAGE,
        sample_page_indexes_fn=_sample_page_indexes,
        page_has_images_fn=_page_has_images,
        detect_pdf_images_with_pymupdf_fn=_detect_pdf_images_with_pymupdf,
        apply_vlm_review_upgrade_fn=_apply_vlm_review_upgrade,
    )

def _classify_pdf_ingestion_route(path: Path, content_hash: str = "") -> dict[str, Any]:
    if content_hash:
        with _PDF_HASH_CACHE_LOCK:
            cached = _PDF_HASH_CACHE.get(content_hash)
        if cached is not None:
            return dict(cached)
        result = _route_helpers.classify_pdf_ingestion_route_impl(
            path,
            classify_pdf_ingestion_route_cached_fn=_classify_pdf_ingestion_route_cached,
        )
        with _PDF_HASH_CACHE_LOCK:
            if len(_PDF_HASH_CACHE) >= _PDF_HASH_CACHE_MAX:
                _PDF_HASH_CACHE.pop(next(iter(_PDF_HASH_CACHE)), None)
            _PDF_HASH_CACHE[content_hash] = dict(result)
        return result
    return _route_helpers.classify_pdf_ingestion_route_impl(
        path,
        classify_pdf_ingestion_route_cached_fn=_classify_pdf_ingestion_route_cached,
    )

def _pdf_should_use_ocr(path: Path) -> bool:
    return _route_helpers.pdf_should_use_ocr_impl(
        path,
        classify_pdf_ingestion_route_fn=_classify_pdf_ingestion_route,
    )

def _get_paddle_ocr_engine() -> Any:
    global _PADDLE_OCR_ENGINE
    engine_obj = _paddle_helpers.get_paddle_ocr_engine_impl(
        paddle_ocr_engine_ref=_PADDLE_OCR_REF,
        paddle_ocr_lock=_PADDLE_OCR_LOCK,
        paddleocr_lang=UPLOAD_PADDLEOCR_LANG,
        paddleocr_use_gpu=UPLOAD_PADDLEOCR_USE_GPU,
    )
    _PADDLE_OCR_ENGINE = engine_obj
    return engine_obj

def _extract_text_lines_from_paddle_result(raw_result: Any) -> list[str]:
    return _paddle_helpers.extract_text_lines_from_paddle_result_impl(raw_result)

def _extract_text_lines_from_vlm_page(
    *,
    client: httpx.Client,
    image_path: Path,
    page_number: int,
) -> list[str]:
    return _paddle_helpers.extract_text_lines_from_vlm_page_impl(
        client=client,
        image_path=image_path,
        page_number=page_number,
        extract_model=UPLOAD_PDF_VLM_EXTRACT_MODEL,
        run_ollama_vlm_for_image_fn=_run_ollama_vlm_for_image,
        extract_text_lines_from_vlm_response_fn=_extract_text_lines_from_vlm_response,
        base_url=UPLOAD_PDF_VLM_BASE_URL,
    )

def _extract_pdf_text_with_paddleocr(
    file_path: Path,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[Path, list[str]]:
    return _paddle_helpers.extract_pdf_text_with_paddleocr_impl(
        file_path,
        should_cancel=should_cancel,
        get_paddle_ocr_engine_fn=_get_paddle_ocr_engine,
        extract_text_lines_from_paddle_result_fn=_extract_text_lines_from_paddle_result,
        merge_text_lines_fn=_merge_text_lines,
        extract_text_lines_from_vlm_page_fn=_extract_text_lines_from_vlm_page,
        indexing_canceled_error_cls=IndexingCanceledError,
        paddleocr_max_pages=UPLOAD_PADDLEOCR_MAX_PAGES,
        paddleocr_render_dpi=UPLOAD_PADDLEOCR_RENDER_DPI,
        vlm_extract_enabled=UPLOAD_PDF_VLM_EXTRACT_ENABLED,
        vlm_extract_max_pages=UPLOAD_PDF_VLM_EXTRACT_MAX_PAGES,
        vlm_extract_render_dpi=UPLOAD_PDF_VLM_EXTRACT_RENDER_DPI,
        vlm_extract_timeout_seconds=UPLOAD_PDF_VLM_EXTRACT_TIMEOUT_SECONDS,
        ollama_timeout_fn=_ollama_timeout,
        paddleocr_vl_api_enabled=UPLOAD_PADDLEOCR_VL_API_ENABLED,
        paddleocr_vl_api_url=UPLOAD_PADDLEOCR_VL_API_URL,
        paddleocr_vl_api_token=UPLOAD_PADDLEOCR_VL_API_TOKEN,
        paddleocr_vl_api_timeout_seconds=UPLOAD_PADDLEOCR_VL_API_TIMEOUT_SECONDS,
        paddleocr_vl_api_file_type=UPLOAD_PADDLEOCR_VL_API_FILE_TYPE,
        paddleocr_vl_api_use_doc_orientation_classify=UPLOAD_PADDLEOCR_VL_API_USE_DOC_ORIENTATION_CLASSIFY,
        paddleocr_vl_api_use_doc_unwarping=UPLOAD_PADDLEOCR_VL_API_USE_DOC_UNWARPING,
        paddleocr_vl_api_use_chart_recognition=UPLOAD_PADDLEOCR_VL_API_USE_CHART_RECOGNITION,
        paddleocr_vl_api_verify_ssl=UPLOAD_PADDLEOCR_VL_API_VERIFY_SSL,
        paddleocr_vl_api_ca_bundle=UPLOAD_PADDLEOCR_VL_API_CA_BUNDLE,
    )

def _build_target_uploaded_meta(
    *,
    target_path: Path,
    source_path: Path,
    uploaded_file_meta: dict[str, dict[str, Any]] | None,
    route: str,
    reader_mode: str,
) -> dict[str, dict[str, Any]]:
    return _paddle_helpers.build_target_uploaded_meta_impl(
        target_path=target_path,
        source_path=source_path,
        uploaded_file_meta=uploaded_file_meta,
        route=route,
        reader_mode=reader_mode,
    )

def _run_index_pipeline_for_file(
    *,
    index: Any,
    user_id: str,
    source_path: Path,
    target_path: Path,
    reindex: bool,
    base_settings: dict[str, Any],
    prefix: str,
    reader_mode: str,
    uploaded_file_meta: dict[str, dict[str, Any]] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    route: str = "normal",
) -> dict[str, Any]:
    return _paddle_helpers.run_index_pipeline_for_file_impl(
        index=index,
        user_id=user_id,
        source_path=source_path,
        target_path=target_path,
        reindex=reindex,
        base_settings=base_settings,
        prefix=prefix,
        reader_mode=reader_mode,
        uploaded_file_meta=uploaded_file_meta,
        should_cancel=should_cancel,
        route=route,
        collect_index_stream_fn=collect_index_stream,
        build_target_uploaded_meta_fn=_build_target_uploaded_meta,
        upload_index_quick_mode=UPLOAD_INDEX_QUICK_MODE,
    )

def _index_pdf_with_paddleocr_route(
    *,
    index: Any,
    user_id: str,
    file_path: Path,
    reindex: bool,
    base_settings: dict[str, Any],
    prefix: str,
    uploaded_file_meta: dict[str, dict[str, Any]] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    return _paddle_helpers.index_pdf_with_paddleocr_route_impl(
        index=index,
        user_id=user_id,
        file_path=file_path,
        reindex=reindex,
        base_settings=base_settings,
        prefix=prefix,
        uploaded_file_meta=uploaded_file_meta,
        should_cancel=should_cancel,
        extract_pdf_text_with_paddleocr_fn=_extract_pdf_text_with_paddleocr,
        run_index_pipeline_for_file_fn=_run_index_pipeline_for_file,
    )

def _select_reader_mode_for_file(
    *,
    configured_mode: str,
    file_path: Path,
) -> str:
    return _route_helpers.select_reader_mode_for_file_impl(
        configured_mode=configured_mode,
        file_path=file_path,
        ocr_preferred_extensions=OCR_PREFERRED_EXTENSIONS,
        pdf_should_use_ocr_fn=_pdf_should_use_ocr,
    )

def _fallback_reader_mode_for_pdf(
    file_path: Path,
    configured_mode: str,
    *,
    classification: dict[str, Any] | None = None,
) -> str:
    return _route_helpers.fallback_reader_mode_for_pdf_impl(
        file_path,
        configured_mode,
        classification=classification,
        pdf_should_use_ocr_fn=_pdf_should_use_ocr,
    )

def _should_route_pdf_to_paddle(
    *,
    configured_mode: str,
    classification: dict[str, Any],
) -> bool:
    return _route_helpers.should_route_pdf_to_paddle_impl(
        configured_mode=configured_mode,
        classification=classification,
        paddleocr_vl_api_enabled=UPLOAD_PADDLEOCR_VL_API_ENABLED,
        paddleocr_vl_api_url=UPLOAD_PADDLEOCR_VL_API_URL,
        paddleocr_vl_api_token=UPLOAD_PADDLEOCR_VL_API_TOKEN,
    )


IndexingCanceledError = _ops_helpers.IndexingCanceledError
_resolve_existing_file_id_for_upload = _ops_helpers.resolve_existing_file_id_for_upload_impl
_is_already_indexed_error = _ops_helpers.is_already_indexed_error_impl

def collect_index_stream(
    output_stream,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[list[str], list[str], list[dict], list[str]]:
    return _ops_helpers.collect_index_stream_impl(
        output_stream,
        should_cancel=should_cancel,
        indexing_canceled_error_cls=IndexingCanceledError,
    )

def apply_upload_scope_to_sources(
    index: Any,
    user_id: str,
    file_ids: list[str],
    scope: str,
) -> None:
    return _ops_helpers.apply_upload_scope_to_sources_impl(
        index=index,
        user_id=user_id,
        file_ids=file_ids,
        scope=scope,
        normalize_ids_fn=normalize_ids,
        normalize_upload_scope_fn=normalize_upload_scope,
    )

def index_files(
    context: ApiContext,
    user_id: str,
    file_paths: list[Path],
    index_id: int | None,
    reindex: bool,
    settings: dict[str, Any],
    scope: str = "persistent",
    uploaded_file_meta: dict[str, dict[str, Any]] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    if not file_paths:
        raise HTTPException(status_code=400, detail="No files were provided.")

    index = get_index(context, index_id)
    record_trace_event(
        "index.started",
        {
            "index_id": getattr(index, "id", None),
            "file_count": len(file_paths),
            "reindex": bool(reindex),
            "scope": str(scope or ""),
        },
    )
    prefix = f"index.options.{index.id}."
    base_settings = deepcopy(settings)
    configured_reader_mode = str(
        base_settings.get(f"{prefix}reader_mode", UPLOAD_INDEX_READER_MODE)
    ).strip() or UPLOAD_INDEX_READER_MODE
    remote_paddle_api_configured = bool(
        UPLOAD_PADDLEOCR_VL_API_ENABLED
        and str(UPLOAD_PADDLEOCR_VL_API_URL or "").strip()
        and str(UPLOAD_PADDLEOCR_VL_API_TOKEN or "").strip()
    )
    all_file_ids: list[str] = []
    all_errors: list[str] = []
    all_items: list[dict[str, Any]] = []
    all_debug: list[str] = []

    def _run_parser_or_reuse(
        *,
        file_path: Path,
        reader_mode: str,
        route: str,
        classification: dict[str, Any],
    ) -> dict[str, Any]:
        record_trace_event(
            "index.pipeline_started",
            {
                "file_name": file_path.name,
                "reader_mode": reader_mode,
                "route": route,
                "classification_route": str(classification.get("route") or ""),
            },
        )
        try:
            return _run_index_pipeline_for_file(
                index=index,
                user_id=user_id,
                source_path=file_path,
                target_path=file_path,
                reindex=reindex,
                base_settings=base_settings,
                prefix=prefix,
                reader_mode=reader_mode,
                uploaded_file_meta=uploaded_file_meta,
                should_cancel=should_cancel,
                route=route,
            )
        except IndexingCanceledError:
            raise
        except Exception as exc:
            if not reindex and _is_already_indexed_error(exc):
                reused_file_id = _resolve_existing_file_id_for_upload(
                    index=index,
                    user_id=user_id,
                    file_path=file_path,
                    uploaded_file_meta=uploaded_file_meta,
                )
                if reused_file_id and _source_ids_have_document_relations(
                    index=index,
                    source_ids=[reused_file_id],
                ):
                    all_debug.append(
                        f"{file_path.name}: already indexed; reusing existing file {reused_file_id}."
                    )
                    record_trace_event(
                        "index.duplicate_reused",
                        {
                            "file_name": file_path.name,
                            "file_id": reused_file_id,
                            "route": route,
                        },
                    )
                    return {
                        "file_ids": [reused_file_id],
                        "errors": [],
                        "items": [
                            {
                                "file_name": file_path.name,
                                "status": "success",
                                "message": "Already indexed; reused existing file.",
                                "file_id": reused_file_id,
                            }
                        ],
                        "debug": [],
                    }
                if reused_file_id:
                    all_debug.append(
                        f"{file_path.name}: duplicate source {reused_file_id} had no indexed document relations; fresh indexing will continue."
                    )
            raise

    def _normalize_duplicate_failure_response(
        *,
        file_path: Path,
        response: dict[str, Any],
    ) -> dict[str, Any]:
        if reindex:
            return response
        items = list(response.get("items") or [])
        errors = [str(err) for err in list(response.get("errors") or [])]
        if not items and not errors:
            return response
        duplicate_messages: list[str] = []
        for item in items:
            if str(item.get("status") or "").strip().lower() != "failed":
                continue
            message = str(item.get("message") or "").strip()
            if message and _is_already_indexed_error(ValueError(message)):
                duplicate_messages.append(message)
        for error in errors:
            if error and _is_already_indexed_error(ValueError(error)):
                duplicate_messages.append(error)
        if not duplicate_messages:
            return response

        reused_file_id = _resolve_existing_file_id_for_upload(
            index=index,
            user_id=user_id,
            file_path=file_path,
            uploaded_file_meta=uploaded_file_meta,
        )
        if not reused_file_id:
            return response
        if not _source_ids_have_document_relations(
            index=index,
            source_ids=[reused_file_id],
        ):
            all_debug.append(
                f"{file_path.name}: duplicate response pointed to source {reused_file_id} without indexed document relations; preserving failure so the source can be reindexed."
            )
            return response

        all_debug.append(
            f"{file_path.name}: already indexed response detected; reusing existing file {reused_file_id}."
        )
        record_trace_event(
            "index.duplicate_response_reused",
            {
                "file_name": file_path.name,
                "file_id": reused_file_id,
            },
        )
        return {
            "file_ids": [reused_file_id],
            "errors": [],
            "items": [
                {
                    "file_name": file_path.name,
                    "status": "success",
                    "message": "Already indexed; reused existing file.",
                    "file_id": reused_file_id,
                }
            ],
            "debug": list(response.get("debug") or []),
        }

    for file_path in file_paths:
        ext = str(file_path.suffix or "").lower()
        is_pdf = ext == ".pdf"
        classification: dict[str, Any] = {}
        record_trace_event(
            "index.file_started",
            {
                "file_name": file_path.name,
                "file_path": str(file_path),
                "extension": ext,
                "is_pdf": is_pdf,
            },
        )
        if is_pdf:
            content_hash = ""
            if uploaded_file_meta:
                try:
                    resolved_key = str(file_path.resolve())
                except Exception:
                    resolved_key = str(file_path)
                meta = uploaded_file_meta.get(resolved_key) or {}
                content_hash = str(meta.get("checksum") or "").strip()
            classification = _classify_pdf_ingestion_route(
                file_path,
                content_hash=content_hash,
            )
            record_trace_event(
                "index.route_selected",
                {
                    "file_name": file_path.name,
                    "route": str(classification.get("route") or "normal"),
                    "reason": str(classification.get("reason") or ""),
                    "image_ratio_all": classification.get("image_ratio_all"),
                    "low_text_ratio_sampled": classification.get("low_text_ratio_sampled"),
                    "content_hash": content_hash[:16] if content_hash else "",
                },
            )
            all_debug.append(
                (
                    f"{file_path.name}: pdf route={classification.get('route', 'normal')} "
                    f"(reason={classification.get('reason', 'n/a')}, "
                    f"image_ratio={float(classification.get('image_ratio_all', 0.0)):.3f}, "
                    f"low_text_ratio={float(classification.get('low_text_ratio_sampled', 0.0)):.3f})."
                )
            )

        route_to_paddle = is_pdf and _should_route_pdf_to_paddle(
            configured_mode=configured_reader_mode,
            classification=classification,
        )

        try:
            if route_to_paddle:
                record_trace_event(
                    "index.ocr_route_started",
                    {
                        "file_name": file_path.name,
                        "route": "heavy-pdf-paddleocr",
                    },
                )
                if not (UPLOAD_PADDLEOCR_ENABLED or remote_paddle_api_configured):
                    raise RuntimeError("PaddleOCR routing is disabled by configuration.")
                response = _index_pdf_with_paddleocr_route(
                    index=index,
                    user_id=user_id,
                    file_path=file_path,
                    reindex=reindex,
                    base_settings=base_settings,
                    prefix=prefix,
                    uploaded_file_meta=uploaded_file_meta,
                    should_cancel=should_cancel,
                )
            else:
                if is_pdf:
                    selected_mode = _fallback_reader_mode_for_pdf(
                        file_path,
                        configured_reader_mode,
                        classification=classification,
                    )
                    route_name = "normal-pdf"
                else:
                    selected_mode = _select_reader_mode_for_file(
                        configured_mode=configured_reader_mode,
                        file_path=file_path,
                    )
                    route_name = "normal"
                record_trace_event(
                    "index.pipeline_route_started",
                    {
                        "file_name": file_path.name,
                        "route": route_name,
                        "reader_mode": selected_mode,
                    },
                )
                response = _run_parser_or_reuse(
                    file_path=file_path,
                    reader_mode=selected_mode,
                    route=route_name,
                    classification=classification,
                )
        except IndexingCanceledError:
            raise
        except Exception as exc:
            if not route_to_paddle:
                record_trace_event(
                    "index.file_failed",
                    {
                        "file_name": file_path.name,
                        "route": "normal",
                        "error": str(exc),
                    },
                )
                raise
            fallback_mode = _fallback_reader_mode_for_pdf(
                file_path,
                configured_reader_mode,
                classification=classification,
            )
            error_text = str(exc)
            ssl_hint = ""
            if "CERTIFICATE_VERIFY_FAILED" in error_text or "certificate verify failed" in error_text.lower():
                ssl_hint = (
                    " Configure MAIA_UPLOAD_PADDLEOCR_VL_API_VERIFY_SSL=false for a trusted internal endpoint,"
                    " or set MAIA_UPLOAD_PADDLEOCR_VL_API_CA_BUNDLE to a custom CA bundle."
                )
            all_debug.append(
                f"{file_path.name}: PaddleOCR failed ({exc}); falling back to {fallback_mode}.{ssl_hint}"
            )
            record_trace_event(
                "index.ocr_route_failed",
                {
                    "file_name": file_path.name,
                    "error": str(exc),
                    "fallback_reader_mode": fallback_mode,
                },
            )
            response = _run_parser_or_reuse(
                file_path=file_path,
                reader_mode=fallback_mode,
                route="heavy-pdf-fallback",
                classification=classification,
            )

        response = _normalize_duplicate_failure_response(
            file_path=file_path,
            response=response,
        )

        file_ids = list(response.get("file_ids") or [])
        errors = list(response.get("errors") or [])
        items = list(response.get("items") or [])
        debug = [str(msg) for msg in list(response.get("debug") or [])]
        if is_pdf and file_ids:
            has_success = any(
                str(item.get("status") or "").strip().lower() == "success"
                for item in items
            )
            if has_success:
                try:
                    precompute_page_units_background(file_path)
                    all_debug.append(f"{file_path.name}: scheduled page-unit precompute.")
                    record_trace_event(
                        "index.precompute_scheduled",
                        {
                            "file_name": file_path.name,
                            "file_ids": list(file_ids),
                        },
                    )
                except Exception as exc:
                    all_debug.append(
                        f"{file_path.name}: page-unit precompute scheduling failed ({exc})."
                    )
                    record_trace_event(
                        "index.precompute_failed",
                        {
                            "file_name": file_path.name,
                            "error": str(exc),
                        },
                    )
        all_file_ids.extend(file_ids)
        all_errors.extend(errors)
        all_items.extend(items)
        all_debug.extend(debug)
        record_trace_event(
            "index.file_completed",
            {
                "file_name": file_path.name,
                "file_ids": list(file_ids),
                "error_count": len(errors),
                "item_count": len(items),
                "debug_count": len(debug),
            },
        )

    apply_upload_scope_to_sources(
        index=index,
        user_id=user_id,
        file_ids=all_file_ids,
        scope=scope,
    )
    return {
        "index_id": index.id,
        "file_ids": all_file_ids,
        "errors": all_errors,
        "items": all_items,
        "debug": all_debug,
    }

def index_urls(
    context: ApiContext,
    user_id: str,
    urls: list[str],
    index_id: int | None,
    reindex: bool,
    settings: dict[str, Any],
    web_crawl_depth: int,
    web_crawl_max_pages: int,
    web_crawl_same_domain_only: bool,
    include_pdfs: bool,
    include_images: bool,
    scope: str = "persistent",
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    return _ops_helpers.index_urls_impl(
        context=context,
        user_id=user_id,
        urls=urls,
        index_id=index_id,
        reindex=reindex,
        settings=settings,
        web_crawl_depth=web_crawl_depth,
        web_crawl_max_pages=web_crawl_max_pages,
        web_crawl_same_domain_only=web_crawl_same_domain_only,
        include_pdfs=include_pdfs,
        include_images=include_images,
        scope=scope,
        should_cancel=should_cancel,
        get_index_fn=get_index,
        collect_index_stream_fn=collect_index_stream,
        apply_upload_scope_to_sources_fn=apply_upload_scope_to_sources,
        upload_index_reader_mode=UPLOAD_INDEX_READER_MODE,
        upload_index_quick_mode=UPLOAD_INDEX_QUICK_MODE,
    )

def list_indexed_files(
    context: ApiContext,
    user_id: str,
    index_id: int | None,
    include_chat_temp: bool = False,
) -> dict[str, Any]:
    return _ops_helpers.list_indexed_files_impl(
        context=context,
        user_id=user_id,
        index_id=index_id,
        include_chat_temp=include_chat_temp,
        get_index_fn=get_index,
        normalize_upload_scope_fn=normalize_upload_scope,
    )

def resolve_indexed_file_path(
    context: ApiContext,
    user_id: str,
    file_id: str,
    index_id: int | None,
) -> tuple[Path, str]:
    return _ops_helpers.resolve_indexed_file_path_impl(
        context=context,
        user_id=user_id,
        file_id=file_id,
        index_id=index_id,
        get_index_fn=get_index,
    )
