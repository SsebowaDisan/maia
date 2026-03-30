from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from api.context import get_context
from api.services.settings_service import load_user_settings
from ktem.db.engine import engine

from .config import JOB_STATUS_CANCELED, JOB_STATUS_QUEUED, TERMINAL_JOB_STATUSES
from .models import IngestionJob
from .serialization import as_json_safe, job_to_payload


def _normalize_file_signature(file_item: dict[str, Any]) -> tuple[str, int, str]:
    item = dict(file_item or {})
    checksum = str(item.get("checksum") or "").strip().lower()
    name = str(item.get("name") or "").strip().lower()
    size = int(item.get("size") or 0)
    path = str(item.get("path") or "").strip().lower()
    identity = checksum or path or name
    return (identity, size, name)


def _cleanup_persisted_uploads(saved_files: list[dict[str, Any]]) -> None:
    parent_dirs: set[Path] = set()
    for item in saved_files:
        raw_path = str((item or {}).get("path") or "").strip()
        if not raw_path:
            continue
        candidate = Path(raw_path)
        if candidate.exists() and candidate.is_file():
            try:
                candidate.unlink(missing_ok=True)
            except Exception:
                pass
        parent = candidate.parent
        if "incoming" in parent.parts:
            parent_dirs.add(parent)

    for directory in parent_dirs:
        if directory.exists() and directory.is_dir():
            try:
                shutil.rmtree(directory, ignore_errors=True)
            except Exception:
                pass


def _get_upload_index(context: Any, index_id: int | None) -> Any:
    from api.services.upload.common import get_index

    return get_index(context, index_id)


def _normalize_upload_ids(values: list[str] | None) -> list[str]:
    from api.services.upload.common import normalize_ids

    return normalize_ids(values or [])


def _normalize_upload_scope_value(scope: str | None) -> str:
    from api.services.upload.common import normalize_upload_scope

    return normalize_upload_scope(scope)


def _resolve_existing_upload_file_id(
    *,
    index: Any,
    user_id: str,
    file_path: Path,
    uploaded_file_meta: dict[str, dict[str, Any]] | None,
) -> str | None:
    from api.services.upload.indexing_ops_helpers import (
        resolve_existing_file_id_for_upload_impl,
    )

    return resolve_existing_file_id_for_upload_impl(
        index=index,
        user_id=user_id,
        file_path=file_path,
        uploaded_file_meta=uploaded_file_meta,
    )


def _apply_upload_scope_to_reserved_sources(
    *,
    index: Any,
    user_id: str,
    file_ids: list[str],
    scope: str,
) -> None:
    from api.services.upload.indexing_ops_helpers import (
        apply_upload_scope_to_sources_impl,
    )

    apply_upload_scope_to_sources_impl(
        index=index,
        user_id=user_id,
        file_ids=file_ids,
        scope=scope,
        normalize_ids_fn=_normalize_upload_ids,
        normalize_upload_scope_fn=_normalize_upload_scope_value,
    )


def _find_matching_active_file_job(
    *,
    session: Session,
    user_id: str,
    index_id: int | None,
    reindex: bool,
    scope: str,
    files: list[dict[str, Any]],
) -> IngestionJob | None:
    incoming_signatures = sorted(_normalize_file_signature(item) for item in files)
    if not incoming_signatures:
        return None

    jobs = session.exec(
        select(IngestionJob)
        .where(
            IngestionJob.user_id == user_id,
            IngestionJob.kind == "files",
        )
        .order_by(IngestionJob.date_created.desc())  # type: ignore[attr-defined]
        .limit(20)
    ).all()

    normalized_scope = str(scope or "persistent").strip() or "persistent"
    for job in jobs:
        if str(job.status or "").strip().lower() in TERMINAL_JOB_STATUSES:
            continue
        if job.index_id != index_id or bool(job.reindex) != bool(reindex):
            continue
        payload = dict(job.payload or {})
        if (str(payload.get("scope") or "persistent").strip() or "persistent") != normalized_scope:
            continue
        existing_files = [dict(item or {}) for item in list(payload.get("files") or [])]
        existing_signatures = sorted(_normalize_file_signature(item) for item in existing_files)
        if existing_signatures == incoming_signatures:
            return job
    return None


def _prepare_file_sources_for_job(
    *,
    user_id: str,
    index_id: int | None,
    scope: str,
    files: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    if not files:
        return [], []

    context = get_context()
    settings = load_user_settings(context=context, user_id=user_id)
    index = _get_upload_index(context, index_id)
    indexing_pipeline = index.get_indexing_pipeline(settings, user_id)

    prepared_files: list[dict[str, Any]] = []
    source_ids: list[str] = []

    for item in files:
        entry = dict(item or {})
        raw_path = str(entry.get("path") or "").strip()
        if not raw_path:
            prepared_files.append(as_json_safe(entry))
            continue

        file_path = Path(raw_path)
        if not file_path.exists() or not file_path.is_file():
            prepared_files.append(as_json_safe(entry))
            continue

        try:
            resolved_key = str(file_path.resolve())
        except Exception:
            resolved_key = raw_path

        uploaded_file_meta = {resolved_key: entry}
        source_id = _resolve_existing_upload_file_id(
            index=index,
            user_id=user_id,
            file_path=file_path,
            uploaded_file_meta=uploaded_file_meta,
        )

        if not source_id:
            checksum = str(entry.get("checksum") or "").strip().lower() or None
            raw_size = entry.get("size")
            precomputed_size: int | None
            try:
                precomputed_size = int(raw_size) if raw_size is not None else None
            except Exception:
                precomputed_size = None
            source_id = indexing_pipeline.store_file(
                file_path,
                precomputed_sha256=checksum,
                precomputed_size=precomputed_size,
            )

        stored_path = indexing_pipeline.get_stored_file_path(source_id)
        entry["source_id"] = str(source_id)
        if stored_path is not None:
            try:
                entry["stored_path"] = str(stored_path.resolve())
            except Exception:
                entry["stored_path"] = str(stored_path)
        prepared_files.append(as_json_safe(entry))
        source_ids.append(str(source_id))

    _apply_upload_scope_to_reserved_sources(
        index=index,
        user_id=user_id,
        file_ids=source_ids,
        scope=scope,
    )
    return prepared_files, list(dict.fromkeys(source_ids))


def create_file_job(
    manager: Any,
    user_id: str,
    *,
    index_id: int | None,
    reindex: bool,
    files: list[dict[str, Any]],
    group_id: str | None,
    scope: str,
) -> dict[str, Any]:
    if not files:
        raise HTTPException(status_code=400, detail="No files were provided.")

    bytes_total = sum(int((item or {}).get("size") or 0) for item in files)
    now = datetime.utcnow()
    payload = {
        "files": [as_json_safe(item) for item in files],
        "target_group_id": str(group_id or "").strip() or None,
        "scope": str(scope or "persistent"),
    }
    with Session(engine) as session:
        existing = _find_matching_active_file_job(
            session=session,
            user_id=user_id,
            index_id=index_id,
            reindex=reindex,
            scope=scope,
            files=payload["files"],
        )
        if existing is not None:
            _cleanup_persisted_uploads(payload["files"])
            return job_to_payload(existing)

        prepared_files, source_ids = _prepare_file_sources_for_job(
            user_id=user_id,
            index_id=index_id,
            scope=scope,
            files=payload["files"],
        )
        payload["files"] = prepared_files

        job = IngestionJob(
            user_id=user_id,
            kind="files",
            status=JOB_STATUS_QUEUED,
            index_id=index_id,
            reindex=bool(reindex),
            total_items=len(files),
            bytes_total=bytes_total,
            bytes_persisted=bytes_total,
            bytes_indexed=0,
            payload=payload,
            file_ids=source_ids,
            date_created=now,
            date_updated=now,
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        created = job_to_payload(job)

    manager.enqueue(job.id)
    manager._inc_metric("jobs_created_files")
    return created


def create_url_job(
    manager: Any,
    user_id: str,
    *,
    index_id: int | None,
    reindex: bool,
    urls: list[str],
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

    now = datetime.utcnow()
    job = IngestionJob(
        user_id=user_id,
        kind="urls",
        status=JOB_STATUS_QUEUED,
        index_id=index_id,
        reindex=bool(reindex),
        total_items=len(cleaned_urls),
        bytes_total=0,
        bytes_persisted=0,
        bytes_indexed=0,
        payload={
            "urls": cleaned_urls,
            "web_crawl_depth": int(web_crawl_depth),
            "web_crawl_max_pages": int(web_crawl_max_pages),
            "web_crawl_same_domain_only": bool(web_crawl_same_domain_only),
            "include_pdfs": bool(include_pdfs),
            "include_images": bool(include_images),
        },
        date_created=now,
        date_updated=now,
    )
    with Session(engine) as session:
        session.add(job)
        session.commit()
        session.refresh(job)
        created = job_to_payload(job)

    manager.enqueue(job.id)
    manager._inc_metric("jobs_created_urls")
    return created


def list_jobs(user_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit), 1), 200)
    with Session(engine) as session:
        jobs = session.exec(
            select(IngestionJob)
            .where(IngestionJob.user_id == user_id)
            .order_by(IngestionJob.date_created.desc())  # type: ignore[attr-defined]
            .limit(safe_limit)
        ).all()
    return [job_to_payload(job) for job in jobs]


def get_job(user_id: str, job_id: str) -> dict[str, Any]:
    with Session(engine) as session:
        job = session.exec(select(IngestionJob).where(IngestionJob.id == job_id)).first()
        if job is None:
            raise HTTPException(status_code=404, detail="Ingestion job not found.")
        if job.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied.")
        return job_to_payload(job)


def cancel_job(manager: Any, user_id: str, job_id: str) -> dict[str, Any]:
    file_ids: list[str] = []
    index_id: int | None = None
    kind = ""
    should_cleanup = False

    with Session(engine) as session:
        job = session.exec(select(IngestionJob).where(IngestionJob.id == job_id)).first()
        if job is None:
            raise HTTPException(status_code=404, detail="Ingestion job not found.")
        if job.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied.")

        kind = str(job.kind or "")
        index_id = job.index_id
        file_ids = list(dict.fromkeys([str(fid) for fid in list(job.file_ids or []) if fid]))
        if job.status not in TERMINAL_JOB_STATUSES:
            should_cleanup = True
            job.status = JOB_STATUS_CANCELED
            job.message = "Ingestion canceled."
            if "Canceled by user." not in list(job.errors or []):
                job.errors = [*list(job.errors or []), "Canceled by user."]
            now = datetime.utcnow()
            job.date_finished = now
            job.date_updated = now
            session.add(job)
            session.commit()
            session.refresh(job)
        elif str(job.status or "").strip().lower() == JOB_STATUS_CANCELED:
            should_cleanup = True

        payload = job_to_payload(job)

    if should_cleanup:
        manager._delete_indexed_files_best_effort(
            user_id=user_id,
            index_id=index_id,
            file_ids=file_ids,
            job_id=job_id,
        )
        if kind == "files":
            manager._cleanup_file_payload(job_id)
    return payload
