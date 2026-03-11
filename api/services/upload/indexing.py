from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import threading
from typing import Any, Callable

import httpx

from api.context import ApiContext

from .common import get_index, normalize_ids, normalize_upload_scope
from .indexing_config import *
from . import indexing_ops_helpers as _ops_helpers
from . import indexing_paddle_helpers as _paddle_helpers
from . import indexing_pdf_page_helpers as _page_helpers
from . import indexing_pdf_route_helpers as _route_helpers
from . import indexing_startup_helpers as _startup_helpers

_PADDLE_OCR_ENGINE: Any | None = None
_PADDLE_OCR_LOCK = threading.Lock()
_PADDLE_OCR_REF: dict[str, Any] = {"engine": None}

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
        logger_warning=logger.warning,
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
        get_paddle_ocr_engine_fn=_get_paddle_ocr_engine,
        logger_warning=logger.warning,
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
    )


IndexingCanceledError = _ops_helpers.IndexingCanceledError

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
    return _ops_helpers.index_files_impl(
        context=context,
        user_id=user_id,
        file_paths=file_paths,
        index_id=index_id,
        reindex=reindex,
        settings=settings,
        scope=scope,
        uploaded_file_meta=uploaded_file_meta,
        should_cancel=should_cancel,
        get_index_fn=get_index,
        classify_pdf_ingestion_route_fn=_classify_pdf_ingestion_route,
        should_route_pdf_to_paddle_fn=_should_route_pdf_to_paddle,
        index_pdf_with_paddleocr_route_fn=_index_pdf_with_paddleocr_route,
        run_index_pipeline_for_file_fn=_run_index_pipeline_for_file,
        fallback_reader_mode_for_pdf_fn=_fallback_reader_mode_for_pdf,
        select_reader_mode_for_file_fn=_select_reader_mode_for_file,
        apply_upload_scope_to_sources_fn=apply_upload_scope_to_sources,
        indexing_canceled_error_cls=IndexingCanceledError,
        upload_paddleocr_enabled=UPLOAD_PADDLEOCR_ENABLED,
        upload_index_reader_mode=UPLOAD_INDEX_READER_MODE,
    )

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
