from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ktem.db.engine import engine

from api.context import ApiContext


def get_index(context: ApiContext, index_id: int | None):
    try:
        return context.get_index(index_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _collect_index_stream(output_stream) -> tuple[list[str], list[str], list[dict], list[str]]:
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


def _normalize_upload_scope(scope: str | None) -> str:
    value = str(scope or "persistent").strip().lower()
    return "chat_temp" if value == "chat_temp" else "persistent"


def _apply_upload_scope_to_sources(
    index: Any,
    user_id: str,
    file_ids: list[str],
    scope: str,
) -> None:
    normalized_ids = _normalize_ids(file_ids)
    if not normalized_ids:
        return

    Source = index._resources["Source"]
    is_private = bool(index.config.get("private", False))
    normalized_scope = _normalize_upload_scope(scope)

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
    file_ids, errors, items, debug = _collect_index_stream(stream)
    _apply_upload_scope_to_sources(
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
    file_ids, errors, items, debug = _collect_index_stream(stream)
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
        scope = _normalize_upload_scope(str(note.get("upload_scope", "persistent")))
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


def _normalize_ids(values: list[str]) -> list[str]:
    cleaned = [value.strip() for value in values if isinstance(value, str) and value.strip()]
    return list(dict.fromkeys(cleaned))


def _serialize_group_record(group: Any) -> dict[str, Any]:
    data = group.data or {}
    file_ids = data.get("files") or []
    return {
        "id": str(group.id),
        "name": str(group.name or ""),
        "file_ids": [str(file_id) for file_id in file_ids if str(file_id).strip()],
        "date_created": group.date_created,
    }


def _get_accessible_file_ids(
    session: Session,
    Source: Any,
    user_id: str,
    is_private: bool,
    file_ids: list[str],
) -> tuple[list[str], list[str]]:
    normalized = _normalize_ids(file_ids)
    if not normalized:
        return [], []

    statement = select(Source.id).where(Source.id.in_(normalized))
    if is_private:
        statement = statement.where(Source.user == user_id)
    accessible = {str(row[0]) for row in session.execute(statement).all()}
    kept = [file_id for file_id in normalized if file_id in accessible]
    skipped = [file_id for file_id in normalized if file_id not in accessible]
    return kept, skipped


def list_file_groups(
    context: ApiContext,
    user_id: str,
    index_id: int | None,
) -> dict[str, Any]:
    index = get_index(context, index_id)
    FileGroup = index._resources["FileGroup"]

    with Session(engine) as session:
        statement = select(FileGroup).where(FileGroup.user == user_id)
        rows = session.execute(statement).all()

    groups = [_serialize_group_record(row[0]) for row in rows]
    groups.sort(key=lambda item: item.get("date_created"), reverse=True)
    return {"index_id": index.id, "groups": groups}


def create_file_group(
    context: ApiContext,
    user_id: str,
    index_id: int | None,
    name: str,
    file_ids: list[str],
) -> dict[str, Any]:
    clean_name = (name or "").strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Group name is required.")

    index = get_index(context, index_id)
    Source = index._resources["Source"]
    FileGroup = index._resources["FileGroup"]
    is_private = bool(index.config.get("private", False))

    with Session(engine) as session:
        duplicate_row = session.execute(
            select(FileGroup).where(FileGroup.name == clean_name, FileGroup.user == user_id)
        ).first()
        kept_ids, skipped_ids = _get_accessible_file_ids(
            session=session,
            Source=Source,
            user_id=user_id,
            is_private=is_private,
            file_ids=file_ids,
        )
        if duplicate_row:
            group = duplicate_row[0]
            current_data = dict(group.data or {})
            current_files = [str(file_id) for file_id in list(current_data.get("files") or [])]
            next_files = list(dict.fromkeys(current_files + kept_ids))
            current_data["files"] = next_files
            group.data = current_data
            session.add(group)
            session.commit()
            session.refresh(group)
            moved_ids = [file_id for file_id in kept_ids if file_id not in current_files]
            serialized = _serialize_group_record(group)
            return {
                "index_id": index.id,
                "group": serialized,
                "moved_ids": moved_ids,
                "skipped_ids": skipped_ids,
            }

        group = FileGroup(name=clean_name, data={"files": kept_ids}, user=user_id)  # type: ignore[arg-type]
        session.add(group)
        session.commit()
        session.refresh(group)
        serialized = _serialize_group_record(group)

    return {
        "index_id": index.id,
        "group": serialized,
        "moved_ids": kept_ids,
        "skipped_ids": skipped_ids,
    }


def move_files_to_group(
    context: ApiContext,
    user_id: str,
    index_id: int | None,
    file_ids: list[str],
    group_id: str | None,
    group_name: str | None,
    mode: str = "append",
) -> dict[str, Any]:
    if not _normalize_ids(file_ids):
        raise HTTPException(status_code=400, detail="No file IDs were provided.")
    if not (group_id and group_id.strip()) and not (group_name and group_name.strip()):
        raise HTTPException(
            status_code=400,
            detail="Either group_id or group_name must be provided.",
        )

    mode_value = str(mode or "append").strip().lower()
    if mode_value not in {"append", "replace"}:
        raise HTTPException(status_code=400, detail="mode must be either 'append' or 'replace'.")

    index = get_index(context, index_id)
    Source = index._resources["Source"]
    FileGroup = index._resources["FileGroup"]
    is_private = bool(index.config.get("private", False))

    with Session(engine) as session:
        kept_ids, skipped_ids = _get_accessible_file_ids(
            session=session,
            Source=Source,
            user_id=user_id,
            is_private=is_private,
            file_ids=file_ids,
        )
        if not kept_ids:
            raise HTTPException(
                status_code=400,
                detail="No accessible files were found in the provided selection.",
            )

        group = None
        if group_id and group_id.strip():
            group = session.execute(
                select(FileGroup).where(FileGroup.id == group_id.strip(), FileGroup.user == user_id)
            ).first()
            if not group:
                raise HTTPException(status_code=404, detail="Target group not found.")
            group = group[0]
        else:
            clean_name = (group_name or "").strip()
            if not clean_name:
                raise HTTPException(status_code=400, detail="Group name is required.")
            existing = session.execute(
                select(FileGroup).where(FileGroup.name == clean_name, FileGroup.user == user_id)
            ).first()
            if existing:
                group = existing[0]
            else:
                group = FileGroup(
                    name=clean_name,
                    data={"files": []},  # type: ignore[arg-type]
                    user=user_id,
                )
                session.add(group)
                session.flush()

        current_data = dict(group.data or {})
        current_files = [str(file_id) for file_id in list(current_data.get("files") or [])]
        if mode_value == "replace":
            next_files = kept_ids
        else:
            next_files = list(dict.fromkeys(current_files + kept_ids))
        current_data["files"] = next_files
        group.data = current_data
        session.add(group)
        session.commit()
        session.refresh(group)
        serialized = _serialize_group_record(group)

    return {
        "index_id": index.id,
        "group": serialized,
        "moved_ids": kept_ids,
        "skipped_ids": skipped_ids,
    }


def rename_file_group(
    context: ApiContext,
    user_id: str,
    index_id: int | None,
    group_id: str,
    name: str,
) -> dict[str, Any]:
    clean_name = (name or "").strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Group name is required.")

    index = get_index(context, index_id)
    FileGroup = index._resources["FileGroup"]

    with Session(engine) as session:
        group_row = session.execute(
            select(FileGroup).where(FileGroup.id == group_id, FileGroup.user == user_id)
        ).first()
        if not group_row:
            raise HTTPException(status_code=404, detail="Target group not found.")

        duplicate = session.execute(
            select(FileGroup).where(
                FileGroup.name == clean_name,
                FileGroup.user == user_id,
                FileGroup.id != group_id,
            )
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="A group with this name already exists.")

        group = group_row[0]
        group.name = clean_name
        session.add(group)
        session.commit()
        session.refresh(group)
        serialized = _serialize_group_record(group)

    return {
        "index_id": index.id,
        "group": serialized,
    }


def delete_file_group(
    context: ApiContext,
    user_id: str,
    index_id: int | None,
    group_id: str,
) -> dict[str, Any]:
    index = get_index(context, index_id)
    FileGroup = index._resources["FileGroup"]

    with Session(engine) as session:
        group_row = session.execute(
            select(FileGroup).where(FileGroup.id == group_id, FileGroup.user == user_id)
        ).first()
        if not group_row:
            raise HTTPException(status_code=404, detail="Target group not found.")
        session.delete(group_row[0])
        session.commit()

    return {
        "index_id": index.id,
        "group_id": group_id,
        "status": "deleted",
    }


def delete_indexed_files(
    context: ApiContext,
    user_id: str,
    index_id: int | None,
    file_ids: list[str],
) -> dict[str, Any]:
    normalized_ids = _normalize_ids(file_ids)
    if not normalized_ids:
        raise HTTPException(status_code=400, detail="No file IDs were provided.")

    index = get_index(context, index_id)
    Source = index._resources["Source"]
    Index = index._resources["Index"]
    FileGroup = index._resources["FileGroup"]
    fs_path = Path(index._resources["FileStoragePath"]).resolve()
    vector_store = index._resources.get("VectorStore")
    doc_store = index._resources.get("DocStore")
    is_private = bool(index.config.get("private", False))

    deleted_ids: list[str] = []
    failed: list[dict[str, Any]] = []

    for file_id in normalized_ids:
        vector_ids: list[str] = []
        document_ids: list[str] = []
        stored_path_raw = ""
        try:
            with Session(engine) as session:
                source_row = session.execute(
                    select(Source).where(Source.id == file_id)
                ).first()
                if not source_row:
                    raise HTTPException(status_code=404, detail="File not found.")
                source = source_row[0]
                if is_private and str(source.user or "") != user_id:
                    raise HTTPException(status_code=403, detail="Access denied.")
                stored_path_raw = str(source.path or "").strip()

                rows = session.execute(select(Index).where(Index.source_id == file_id)).all()
                for row in rows:
                    rel = str(row[0].relation_type or "")
                    target_id = str(row[0].target_id or "")
                    if rel == "vector" and target_id:
                        vector_ids.append(target_id)
                    elif rel == "document" and target_id:
                        document_ids.append(target_id)
                    session.delete(row[0])

                groups = session.execute(
                    select(FileGroup).where(FileGroup.user == user_id)
                ).all()
                for group_row in groups:
                    group = group_row[0]
                    group_data = dict(group.data or {})
                    current_files = [str(fid) for fid in list(group_data.get("files") or [])]
                    if file_id in current_files:
                        group_data["files"] = [fid for fid in current_files if fid != file_id]
                        group.data = group_data
                        session.add(group)

                session.delete(source)
                session.commit()

            if vector_ids and vector_store is not None:
                try:
                    vector_store.delete(vector_ids)
                except Exception:
                    pass
            if document_ids and doc_store is not None:
                try:
                    doc_store.delete(document_ids)
                except Exception:
                    pass

            if stored_path_raw:
                candidate = Path(stored_path_raw)
                if not candidate.is_absolute():
                    candidate = fs_path / candidate
                candidate = candidate.resolve()
                if candidate.exists() and candidate.is_file():
                    candidate.unlink(missing_ok=True)

            deleted_ids.append(file_id)
        except HTTPException as exc:
            failed.append(
                {
                    "file_id": file_id,
                    "status": "failed",
                    "message": str(exc.detail),
                }
            )
        except Exception as exc:
            failed.append(
                {
                    "file_id": file_id,
                    "status": "failed",
                    "message": str(exc),
                }
            )

    return {"index_id": index.id, "deleted_ids": deleted_ids, "failed": failed}
