from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ktem.db.engine import engine

from api.context import ApiContext

from .common import get_index, normalize_ids, normalize_upload_scope


def collect_index_stream(output_stream) -> tuple[list[str], list[str], list[dict], list[str]]:
    items: list[dict] = []
    debug: list[str] = []
    file_ids_raw: list[str | None] = []
    errors_raw: list[str | None] = []

    try:
        while True:
            response = next(output_stream)
            if response is None or response.channel is None:
                continue
            if response.channel == "index":
                content = response.content or {}
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
    except StopIteration as stop:
        file_ids_raw, errors_raw, _docs = stop.value

    file_ids = [file_id for file_id in file_ids_raw if file_id]
    errors = [error for error in errors_raw if error]
    return file_ids, errors, items, debug


def apply_upload_scope_to_sources(
    index: Any,
    user_id: str,
    file_ids: list[str],
    scope: str,
) -> None:
    normalized_ids = normalize_ids(file_ids)
    if not normalized_ids:
        return

    Source = index._resources["Source"]
    is_private = bool(index.config.get("private", False))
    normalized_scope = normalize_upload_scope(scope)

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


def index_files(
    context: ApiContext,
    user_id: str,
    file_paths: list[Path],
    index_id: int | None,
    reindex: bool,
    settings: dict[str, Any],
    scope: str = "persistent",
) -> dict[str, Any]:
    if not file_paths:
        raise HTTPException(status_code=400, detail="No files were provided.")

    index = get_index(context, index_id)
    request_settings = deepcopy(settings)
    prefix = f"index.options.{index.id}."
    request_settings[f"{prefix}reader_mode"] = "ocr"
    request_settings[f"{prefix}quick_index_mode"] = True
    indexing_pipeline = index.get_indexing_pipeline(request_settings, user_id)
    stream = indexing_pipeline.stream(file_paths, reindex=reindex)
    file_ids, errors, items, debug = collect_index_stream(stream)
    apply_upload_scope_to_sources(
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
) -> dict[str, Any]:
    cleaned_urls = [url.strip() for url in urls if url and url.strip()]
    if not cleaned_urls:
        raise HTTPException(status_code=400, detail="No URLs were provided.")

    for url in cleaned_urls:
        if not (url.startswith("http://") or url.startswith("https://")):
            raise HTTPException(status_code=400, detail=f"Invalid URL: {url}")

    index = get_index(context, index_id)
    request_settings = deepcopy(settings)
    prefix = f"index.options.{index.id}."
    request_settings[f"{prefix}reader_mode"] = "ocr"
    request_settings[f"{prefix}quick_index_mode"] = True
    request_settings[f"{prefix}web_crawl_depth"] = max(0, int(web_crawl_depth))
    request_settings[f"{prefix}web_crawl_max_pages"] = max(0, int(web_crawl_max_pages))
    request_settings[f"{prefix}web_crawl_same_domain_only"] = bool(
        web_crawl_same_domain_only
    )
    request_settings[f"{prefix}web_crawl_include_pdfs"] = bool(include_pdfs)
    request_settings[f"{prefix}web_crawl_include_images"] = bool(include_images)

    indexing_pipeline = index.get_indexing_pipeline(request_settings, user_id)
    stream = indexing_pipeline.stream(cleaned_urls, reindex=reindex)
    file_ids, errors, items, debug = collect_index_stream(stream)
    return {
        "index_id": index.id,
        "file_ids": file_ids,
        "errors": errors,
        "items": items,
        "debug": debug,
    }


def list_indexed_files(
    context: ApiContext,
    user_id: str,
    index_id: int | None,
    include_chat_temp: bool = False,
) -> dict[str, Any]:
    index = get_index(context, index_id)
    Source = index._resources["Source"]

    with Session(engine) as session:
        statement = select(Source)
        if index.config.get("private", False):
            statement = statement.where(Source.user == user_id)
        rows = session.execute(statement).all()

    files = []
    for row in rows:
        note = row[0].note or {}
        scope = normalize_upload_scope(str(note.get("upload_scope", "persistent")))
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


def resolve_indexed_file_path(
    context: ApiContext,
    user_id: str,
    file_id: str,
    index_id: int | None,
) -> tuple[Path, str]:
    index = get_index(context, index_id)
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
