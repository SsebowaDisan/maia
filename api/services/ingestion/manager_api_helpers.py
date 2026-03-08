from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from ktem.db.engine import engine

from .config import JOB_STATUS_CANCELED, JOB_STATUS_QUEUED, TERMINAL_JOB_STATUSES
from .models import IngestionJob
from .serialization import as_json_safe, job_to_payload


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
        payload={
            "files": [as_json_safe(item) for item in files],
            "target_group_id": str(group_id or "").strip() or None,
            "scope": str(scope or "persistent"),
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
