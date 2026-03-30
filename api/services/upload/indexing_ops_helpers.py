from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ktem.db.engine import engine
from .pdf_highlight_locator import get_pdf_citation_cache_state


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


def is_already_indexed_error_impl(exc: Exception) -> bool:
    normalized = " ".join(str(exc or "").split()).strip().lower()
    return "already indexed" in normalized


def resolve_existing_file_id_for_upload_impl(
    *,
    index: Any,
    user_id: str,
    file_path: Path,
    uploaded_file_meta: dict[str, dict[str, Any]] | None,
) -> str | None:
    Source = index._resources["Source"]
    is_private = bool(index.config.get("private", False))

    checksum = ""
    try:
        resolved_key = str(file_path.resolve())
    except Exception:
        resolved_key = str(file_path)
    if isinstance(uploaded_file_meta, dict):
        meta = uploaded_file_meta.get(resolved_key) or {}
        checksum = str(meta.get("checksum") or "").strip().lower()

    with Session(engine) as session:
        if checksum:
            statement = select(Source.id).where(Source.path == checksum)
            if is_private:
                statement = statement.where(Source.user == user_id)
            row = session.execute(statement).first()
            if row and row[0]:
                return str(row[0]).strip() or None

        statement = select(Source.id).where(Source.name == file_path.name)
        if is_private:
            statement = statement.where(Source.user == user_id)
        row = session.execute(statement).first()
        if row and row[0]:
            return str(row[0]).strip() or None

    return None


def source_ids_have_document_relations_impl(
    *,
    index: Any,
    source_ids: list[str] | None,
) -> bool:
    cleaned_ids = [str(item).strip() for item in (source_ids or []) if str(item).strip()]
    if not cleaned_ids:
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
            has_document_relations = source_ids_have_document_relations_impl(
                index=index,
                source_ids=[str(source.id)],
            )
            note["upload_scope"] = normalized_scope
            note["rag_ready"] = bool(has_document_relations)
            note.setdefault("citation_ready", bool(has_document_relations))
            note.setdefault(
                "citation_status",
                "ready" if has_document_relations else "pending",
            )
            source.note = note
            session.add(source)
        session.commit()


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

    fs_path = Path(index._resources["FileStoragePath"])
    files = []
    for row in rows:
        note = dict(row[0].note or {})
        scope = normalize_upload_scope_fn(str(note.get("upload_scope", "persistent")))
        if not include_chat_temp and scope == "chat_temp":
            continue
        has_document_relations = source_ids_have_document_relations_impl(
            index=index,
            source_ids=[str(row[0].id)],
        )
        note["rag_ready"] = bool(has_document_relations)
        stored_path = str(row[0].path or "").strip()
        source_name = str(row[0].name or "").strip()
        candidate: Path | None = None
        if stored_path:
            candidate = Path(stored_path)
            if not candidate.is_absolute():
                candidate = fs_path / candidate
            try:
                candidate = candidate.resolve()
            except Exception:
                candidate = candidate
        original_pdf_storage_name = str(note.get("source_original_pdf_storage_name") or "").strip()
        if original_pdf_storage_name:
            candidate = (fs_path / original_pdf_storage_name).resolve()

        is_pdf = source_name.lower().endswith(".pdf") or bool(original_pdf_storage_name)
        if is_pdf and candidate and candidate.exists() and candidate.is_file():
            citation_state = get_pdf_citation_cache_state(candidate)
            note["citation_ready"] = bool(has_document_relations and citation_state.get("citation_ready"))
            note["citation_status"] = str(
                citation_state.get("citation_status")
                or ("refining" if has_document_relations else "pending")
            )
        else:
            note["citation_ready"] = bool(has_document_relations)
            note["citation_status"] = "ready" if has_document_relations else "pending"
        rag_ready = bool(note.get("rag_ready"))
        citation_ready = bool(note.get("citation_ready"))
        citation_status = str(note.get("citation_status") or "").strip() or None
        files.append(
            {
                "id": row[0].id,
                "name": row[0].name,
                "size": int(row[0].size or 0),
                "scope": scope,
                "rag_ready": rag_ready,
                "citation_ready": citation_ready,
                "citation_status": citation_status,
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
        stored_note = row.note

    if not stored_path:
        raise HTTPException(status_code=404, detail="Indexed file path is missing.")

    note_dict: dict[str, Any] = {}
    if isinstance(stored_note, dict):
        note_dict = dict(stored_note)
    elif isinstance(stored_note, str):
        try:
            parsed_note = json.loads(stored_note)
            if isinstance(parsed_note, dict):
                note_dict = parsed_note
        except Exception:
            note_dict = {}

    candidate = Path(stored_path)
    if not candidate.is_absolute():
        candidate = fs_path / candidate
    candidate = candidate.resolve()

    if candidate.exists() and candidate.is_file():
        original_pdf_storage_name = str(note_dict.get("source_original_pdf_storage_name") or "").strip()
        original_pdf_name = str(note_dict.get("source_original_pdf_name") or "").strip()
        fallback_pdf_candidate: Path | None = None
        if original_pdf_storage_name:
            fallback_pdf_candidate = fs_path / original_pdf_storage_name
        elif not candidate.suffix and len(candidate.name) == 64:
            fallback_pdf_candidate = candidate.with_name(f"{candidate.name}.pdf")
        if fallback_pdf_candidate is not None:
            fallback_pdf_candidate = fallback_pdf_candidate.resolve()
            if fallback_pdf_candidate.exists() and fallback_pdf_candidate.is_file():
                return fallback_pdf_candidate, (original_pdf_name or stored_name)

    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(
            status_code=404,
            detail="Stored file is not available on disk (likely URL-only source).",
        )

    return candidate, stored_name


