from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ktem.db.engine import engine


class IndexingCanceledError(RuntimeError):
    def __init__(
        self,
        message: str = "Ingestion canceled by user.",
        *,
        file_ids: list[str] | None = None,
        errors: list[str] | None = None,
        items: list[dict[str, Any]] | None = None,
        debug: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.file_ids = list(file_ids or [])
        self.errors = list(errors or [])
        self.items = list(items or [])
        self.debug = list(debug or [])


def collect_index_stream_impl(
    output_stream,
    *,
    should_cancel: Callable[[], bool] | None = None,
    indexing_canceled_error_cls: type[Exception] = IndexingCanceledError,
) -> tuple[list[str], list[str], list[dict], list[str]]:
    items: list[dict] = []
    debug: list[str] = []
    file_ids_raw: list[str | None] = []
    errors_raw: list[str | None] = []
    streamed_file_ids: list[str] = []

    def _raise_if_canceled() -> None:
        if not should_cancel or not should_cancel():
            return
        merged_file_ids = [
            file_id
            for file_id in [*streamed_file_ids, *file_ids_raw]
            if file_id
        ]
        dedup_file_ids = list(dict.fromkeys(merged_file_ids))
        raise indexing_canceled_error_cls(
            file_ids=dedup_file_ids,
            errors=[str(error) for error in errors_raw if error],
            items=[dict(item) for item in items],
            debug=[str(message) for message in debug],
        )

    try:
        while True:
            _raise_if_canceled()
            response = next(output_stream)
            if response is None or response.channel is None:
                continue
            if response.channel == "index":
                content = response.content or {}
                file_id = content.get("file_id")
                file_id_text = str(file_id).strip() if file_id else ""
                if file_id_text:
                    streamed_file_ids.append(file_id_text)
                items.append(
                    {
                        "file_name": str(content.get("file_name", "")),
                        "status": str(content.get("status", "unknown")),
                        "message": content.get("message"),
                        "file_id": content.get("file_id"),
                    }
                )
            elif response.channel == "debug":
                text = response.text if response.text else str(response.content)
                debug.append(text)
            _raise_if_canceled()
    except StopIteration as stop:
        file_ids_raw, errors_raw, _docs = stop.value

    file_ids = [file_id for file_id in [*streamed_file_ids, *file_ids_raw] if file_id]
    file_ids = list(dict.fromkeys(file_ids))
    errors = [error for error in errors_raw if error]
    return file_ids, errors, items, debug


def apply_upload_scope_to_sources_impl(
    *,
    index: Any,
    user_id: str,
    file_ids: list[str],
    scope: str,
    normalize_ids_fn: Callable[[list[str] | None], list[str]],
    normalize_upload_scope_fn: Callable[[str | None], str],
) -> None:
    normalized_ids = normalize_ids_fn(file_ids)
    if not normalized_ids:
        return

    Source = index._resources["Source"]
    is_private = bool(index.config.get("private", False))
    normalized_scope = normalize_upload_scope_fn(scope)

    with Session(engine) as session:
        statement = select(Source).where(Source.id.in_(normalized_ids))
        if is_private:
            statement = statement.where(Source.user == user_id)
        rows = session.execute(statement).all()
        for row in rows:
            source = row[0]
            note = dict(source.note or {})
            note["upload_scope"] = normalized_scope
            source.note = note
            session.add(source)
        session.commit()


def index_files_impl(
    *,
    context: Any,
    user_id: str,
    file_paths: list[Path],
    index_id: int | None,
    reindex: bool,
    settings: dict[str, Any],
    scope: str,
    uploaded_file_meta: dict[str, dict[str, Any]] | None,
    should_cancel: Callable[[], bool] | None,
    get_index_fn: Callable[..., Any],
    classify_pdf_ingestion_route_fn: Callable[[Path], dict[str, Any]],
    should_route_pdf_to_paddle_fn: Callable[..., bool],
    index_pdf_with_paddleocr_route_fn: Callable[..., dict[str, Any]],
    run_index_pipeline_for_file_fn: Callable[..., dict[str, Any]],
    fallback_reader_mode_for_pdf_fn: Callable[..., str],
    select_reader_mode_for_file_fn: Callable[..., str],
    apply_upload_scope_to_sources_fn: Callable[..., None],
    indexing_canceled_error_cls: type[Exception],
    upload_paddleocr_enabled: bool,
    upload_index_reader_mode: str,
) -> dict[str, Any]:
    if not file_paths:
        raise HTTPException(status_code=400, detail="No files were provided.")

    index = get_index_fn(context, index_id)
    prefix = f"index.options.{index.id}."
    base_settings = deepcopy(settings)
    configured_reader_mode = str(
        base_settings.get(f"{prefix}reader_mode", upload_index_reader_mode)
    ).strip() or upload_index_reader_mode
    all_file_ids: list[str] = []
    all_errors: list[str] = []
    all_items: list[dict[str, Any]] = []
    all_debug: list[str] = []
    for file_path in file_paths:
        ext = str(file_path.suffix or "").lower()
        is_pdf = ext == ".pdf"
        classification: dict[str, Any] = {}
        if is_pdf:
            classification = classify_pdf_ingestion_route_fn(file_path)
            all_debug.append(
                (
                    f"{file_path.name}: pdf route={classification.get('route', 'normal')} "
                    f"(reason={classification.get('reason', 'n/a')}, "
                    f"image_ratio={float(classification.get('image_ratio_all', 0.0)):.3f}, "
                    f"low_text_ratio={float(classification.get('low_text_ratio_sampled', 0.0)):.3f})."
                )
            )

        route_to_paddle = is_pdf and should_route_pdf_to_paddle_fn(
            configured_mode=configured_reader_mode,
            classification=classification,
        )

        response: dict[str, Any]
        try:
            if route_to_paddle:
                if not upload_paddleocr_enabled:
                    raise RuntimeError("PaddleOCR routing is disabled by configuration.")
                response = index_pdf_with_paddleocr_route_fn(
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
                    selected_mode = fallback_reader_mode_for_pdf_fn(
                        file_path,
                        configured_reader_mode,
                        classification=classification,
                    )
                    route_name = "normal-pdf"
                else:
                    selected_mode = select_reader_mode_for_file_fn(
                        configured_mode=configured_reader_mode,
                        file_path=file_path,
                    )
                    route_name = "normal"
                response = run_index_pipeline_for_file_fn(
                    index=index,
                    user_id=user_id,
                    source_path=file_path,
                    target_path=file_path,
                    reindex=reindex,
                    base_settings=base_settings,
                    prefix=prefix,
                    reader_mode=selected_mode,
                    uploaded_file_meta=uploaded_file_meta,
                    should_cancel=should_cancel,
                    route=route_name,
                )
        except indexing_canceled_error_cls:
            raise
        except Exception as exc:
            if not route_to_paddle:
                raise
            fallback_mode = fallback_reader_mode_for_pdf_fn(
                file_path,
                configured_reader_mode,
                classification=classification,
            )
            all_debug.append(
                f"{file_path.name}: PaddleOCR failed ({exc}); falling back to {fallback_mode}."
            )
            response = run_index_pipeline_for_file_fn(
                index=index,
                user_id=user_id,
                source_path=file_path,
                target_path=file_path,
                reindex=reindex,
                base_settings=base_settings,
                prefix=prefix,
                reader_mode=fallback_mode,
                uploaded_file_meta=uploaded_file_meta,
                should_cancel=should_cancel,
                route="heavy-pdf-fallback",
            )

        file_ids = list(response.get("file_ids") or [])
        errors = list(response.get("errors") or [])
        items = list(response.get("items") or [])
        debug = [str(msg) for msg in list(response.get("debug") or [])]
        all_file_ids.extend(file_ids)
        all_errors.extend(errors)
        all_items.extend(items)
        all_debug.extend(debug)
    apply_upload_scope_to_sources_fn(
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


def index_urls_impl(
    *,
    context: Any,
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
    scope: str,
    should_cancel: Callable[[], bool] | None,
    get_index_fn: Callable[..., Any],
    collect_index_stream_fn: Callable[..., tuple[list[str], list[str], list[dict], list[str]]],
    apply_upload_scope_to_sources_fn: Callable[..., None],
    upload_index_reader_mode: str,
    upload_index_quick_mode: bool,
) -> dict[str, Any]:
    cleaned_urls = [url.strip() for url in urls if url and url.strip()]
    if not cleaned_urls:
        raise HTTPException(status_code=400, detail="No URLs were provided.")

    for url in cleaned_urls:
        if not (url.startswith("http://") or url.startswith("https://")):
            raise HTTPException(status_code=400, detail=f"Invalid URL: {url}")

    index = get_index_fn(context, index_id)
    request_settings = deepcopy(settings)
    prefix = f"index.options.{index.id}."
    request_settings.setdefault(f"{prefix}reader_mode", upload_index_reader_mode)
    request_settings.setdefault(f"{prefix}quick_index_mode", upload_index_quick_mode)
    request_settings[f"{prefix}web_crawl_depth"] = max(0, int(web_crawl_depth))
    request_settings[f"{prefix}web_crawl_max_pages"] = max(0, int(web_crawl_max_pages))
    request_settings[f"{prefix}web_crawl_same_domain_only"] = bool(
        web_crawl_same_domain_only
    )
    request_settings[f"{prefix}web_crawl_include_pdfs"] = bool(include_pdfs)
    request_settings[f"{prefix}web_crawl_include_images"] = bool(include_images)

    indexing_pipeline = index.get_indexing_pipeline(request_settings, user_id)
    stream = indexing_pipeline.stream(cleaned_urls, reindex=reindex)
    file_ids, errors, items, debug = collect_index_stream_fn(
        stream,
        should_cancel=should_cancel,
    )
    apply_upload_scope_to_sources_fn(
        index=index,
        user_id=user_id,
        file_ids=file_ids,
        scope=scope,
    )
    return {
        "index_id": index.id,
        "file_ids": file_ids,
        "errors": errors,
        "items": items,
        "debug": debug,
    }


def list_indexed_files_impl(
    *,
    context: Any,
    user_id: str,
    index_id: int | None,
    include_chat_temp: bool,
    get_index_fn: Callable[..., Any],
    normalize_upload_scope_fn: Callable[[str | None], str],
) -> dict[str, Any]:
    index = get_index_fn(context, index_id)
    Source = index._resources["Source"]

    with Session(engine) as session:
        statement = select(Source)
        if index.config.get("private", False):
            statement = statement.where(Source.user == user_id)
        rows = session.execute(statement).all()

    files = []
    for row in rows:
        note = row[0].note or {}
        scope = normalize_upload_scope_fn(str(note.get("upload_scope", "persistent")))
        if not include_chat_temp and scope == "chat_temp":
            continue
        files.append(
            {
                "id": row[0].id,
                "name": row[0].name,
                "size": int(row[0].size or 0),
                "note": note,
                "date_created": row[0].date_created,
            }
        )

    files = sorted(files, key=lambda item: item["date_created"], reverse=True)
    return {"index_id": index.id, "files": files}


def resolve_indexed_file_path_impl(
    *,
    context: Any,
    user_id: str,
    file_id: str,
    index_id: int | None,
    get_index_fn: Callable[..., Any],
) -> tuple[Path, str]:
    index = get_index_fn(context, index_id)
    Source = index._resources["Source"]
    fs_path = Path(index._resources["FileStoragePath"])

    with Session(engine) as session:
        source = session.execute(select(Source).where(Source.id == file_id)).first()
        if not source:
            raise HTTPException(status_code=404, detail="File not found.")
        row = source[0]
        if index.config.get("private", False) and str(row.user or "") != user_id:
            raise HTTPException(status_code=403, detail="Access denied.")

        stored_name = str(row.name or "file")
        stored_path = str(row.path or "").strip()

    if not stored_path:
        raise HTTPException(status_code=404, detail="Indexed file path is missing.")

    candidate = Path(stored_path)
    if not candidate.is_absolute():
        candidate = fs_path / candidate
    candidate = candidate.resolve()

    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(
            status_code=404,
            detail="Stored file is not available on disk (likely URL-only source).",
        )

    return candidate, stored_name
