from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ktem.db.engine import engine

from api.context import ApiContext

from .common import get_index, normalize_ids, serialize_group_record


def _normalize_url_for_match(value: str, *, keep_query: bool = True) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
    except Exception:
        return ""
    scheme = str(parsed.scheme or "").strip().lower()
    if scheme not in {"http", "https"}:
        return ""
    host = str(parsed.hostname or "").strip().lower()
    if not host:
        return ""
    try:
        port = parsed.port
    except Exception:
        port = None
    default_port = 80 if scheme == "http" else 443
    netloc = host if not port or port == default_port else f"{host}:{port}"
    path = str(parsed.path or "/").strip() or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    query = str(parsed.query or "").strip() if keep_query else ""
    normalized = urlunparse((scheme, netloc, path, "", query, ""))
    if normalized.endswith("/") and path == "/" and not query:
        return normalized[:-1]
    return normalized


def _url_signatures(value: str) -> set[str]:
    full = _normalize_url_for_match(value, keep_query=True)
    if not full:
        return set()
    parsed = urlparse(full)
    base = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    if base.endswith("/") and parsed.path == "/":
        base = base[:-1]
    signatures = {full.lower(), base.lower()}
    if parsed.path in {"", "/"} and not parsed.query:
        signatures.add(f"{parsed.scheme}://{parsed.netloc}/".lower())
    return {item for item in signatures if item}


def _source_url_candidates(source: Any) -> list[str]:
    values: list[str] = []
    name_value = str(getattr(source, "name", "") or "").strip()
    if name_value:
        values.append(name_value)
    path_value = str(getattr(source, "path", "") or "").strip()
    if path_value.startswith("http://") or path_value.startswith("https://"):
        values.append(path_value)
    note = getattr(source, "note", None)
    if isinstance(note, dict):
        for key in (
            "source_url",
            "url",
            "page_url",
            "canonical_url",
            "original_url",
            "link",
        ):
            value = str(note.get(key, "") or "").strip()
            if value:
                values.append(value)
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _match_requested_urls_to_sources(
    requested_urls: list[str],
    source_rows: list[Any],
) -> tuple[dict[str, list[str]], list[str]]:
    ordered_urls: list[str] = []
    requested_signatures: dict[str, set[str]] = {}
    for raw_url in requested_urls:
        value = str(raw_url or "").strip()
        if not value or value in requested_signatures:
            continue
        signatures = _url_signatures(value)
        if not signatures:
            continue
        requested_signatures[value] = signatures
        ordered_urls.append(value)

    matched: dict[str, set[str]] = {url: set() for url in ordered_urls}
    for source in source_rows:
        source_id = str(getattr(source, "id", "") or "").strip()
        if not source_id:
            continue
        source_signatures: set[str] = set()
        for candidate in _source_url_candidates(source):
            source_signatures.update(_url_signatures(candidate))
        if not source_signatures:
            continue
        for raw_url, signatures in requested_signatures.items():
            if signatures.intersection(source_signatures):
                matched[raw_url].add(source_id)

    unresolved = [url for url in ordered_urls if not matched[url]]
    resolved = {
        url: sorted(source_ids)
        for url, source_ids in matched.items()
        if source_ids
    }
    return resolved, unresolved


def get_accessible_file_ids(
    session: Session,
    Source: Any,
    user_id: str,
    is_private: bool,
    file_ids: list[str],
) -> tuple[list[str], list[str]]:
    normalized = normalize_ids(file_ids)
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

    groups = [serialize_group_record(row[0]) for row in rows]
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
        kept_ids, skipped_ids = get_accessible_file_ids(
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
            serialized = serialize_group_record(group)
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
        serialized = serialize_group_record(group)

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
    if not normalize_ids(file_ids):
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
        kept_ids, skipped_ids = get_accessible_file_ids(
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
        serialized = serialize_group_record(group)

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
        serialized = serialize_group_record(group)

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
    normalized_ids = normalize_ids(file_ids)
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


def delete_indexed_urls(
    context: ApiContext,
    user_id: str,
    index_id: int | None,
    urls: list[str],
) -> dict[str, Any]:
    cleaned_urls = normalize_ids(urls)
    if not cleaned_urls:
        raise HTTPException(status_code=400, detail="No URLs were provided.")

    index = get_index(context, index_id)
    Source = index._resources["Source"]
    is_private = bool(index.config.get("private", False))

    with Session(engine) as session:
        statement = select(Source)
        if is_private:
            statement = statement.where(Source.user == user_id)
        source_rows = [row[0] for row in session.execute(statement).all()]

    url_to_source_ids, unresolved_urls = _match_requested_urls_to_sources(
        requested_urls=cleaned_urls,
        source_rows=source_rows,
    )
    source_ids = sorted(
        {
            source_id
            for mapped_ids in url_to_source_ids.values()
            for source_id in mapped_ids
            if source_id
        }
    )

    failed: list[dict[str, Any]] = [
        {
            "url": url,
            "status": "failed",
            "message": "No indexed source matched this URL.",
        }
        for url in unresolved_urls
    ]

    if not source_ids:
        return {
            "index_id": index.id,
            "deleted_ids": [],
            "deleted_urls": [],
            "failed": failed,
        }

    delete_result = delete_indexed_files(
        context=context,
        user_id=user_id,
        index_id=index.id,
        file_ids=source_ids,
    )
    deleted_set = {str(file_id) for file_id in delete_result.get("deleted_ids", [])}
    failed_by_id: dict[str, str] = {}
    for row in delete_result.get("failed", []):
        file_id = str(row.get("file_id", "") or "").strip()
        if not file_id:
            continue
        failed_by_id[file_id] = str(row.get("message", "") or "").strip() or "Delete failed."

    deleted_urls: list[str] = []
    for url in cleaned_urls:
        mapped_ids = url_to_source_ids.get(url, [])
        if not mapped_ids:
            continue
        if any(source_id in deleted_set for source_id in mapped_ids):
            deleted_urls.append(url)
            continue
        messages = [
            failed_by_id[source_id]
            for source_id in mapped_ids
            if source_id in failed_by_id and failed_by_id[source_id]
        ]
        failed.append(
            {
                "url": url,
                "status": "failed",
                "message": "; ".join(dict.fromkeys(messages))
                if messages
                else "Delete failed for matched URL sources.",
            }
        )

    deduped_failed: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for row in failed:
        url = str(row.get("url", "") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        deduped_failed.append(row)

    return {
        "index_id": int(delete_result.get("index_id", index.id)),
        "deleted_ids": [str(file_id) for file_id in delete_result.get("deleted_ids", [])],
        "deleted_urls": deleted_urls,
        "failed": deduped_failed,
    }
