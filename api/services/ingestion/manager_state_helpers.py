from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
from typing import Any

from sqlmodel import Session, select

from ktem.db.engine import engine

from .config import (
    INGEST_KEEP_WORKDIR,
    INGEST_WORKDIR,
    JOB_STATUS_CANCELED,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_RUNNING,
    TERMINAL_JOB_STATUSES,
)
from .models import IngestionJob
from .serialization import as_json_safe


def update_progress(
    *,
    job_id: str,
    processed_items: int,
    success_count: int,
    failure_count: int,
    bytes_total: int,
    bytes_persisted: int,
    bytes_indexed: int,
    items: list[dict[str, Any]],
    errors: list[str],
    file_ids: list[str],
    debug: list[str],
) -> None:
    with Session(engine) as session:
        job = session.exec(select(IngestionJob).where(IngestionJob.id == job_id)).first()
        if job is None:
            return
        if job.status in TERMINAL_JOB_STATUSES:
            return
        job.processed_items = int(processed_items)
        job.success_count = int(success_count)
        job.failure_count = int(failure_count)
        job.bytes_total = int(max(0, bytes_total))
        job.bytes_persisted = int(max(0, bytes_persisted))
        job.bytes_indexed = int(max(0, bytes_indexed))
        job.items = [as_json_safe(item) for item in items]
        job.errors = [str(err) for err in errors]
        dedup_ids = list(dict.fromkeys([str(file_id) for file_id in file_ids if file_id]))
        job.file_ids = dedup_ids
        job.debug = [str(msg) for msg in debug][-200:]
        job.date_updated = datetime.utcnow()
        session.add(job)
        session.commit()


def mark_completed(
    manager: Any,
    *,
    job_id: str,
    processed_items: int,
    success_count: int,
    failure_count: int,
    bytes_total: int,
    bytes_persisted: int,
    bytes_indexed: int,
    items: list[dict[str, Any]],
    errors: list[str],
    file_ids: list[str],
    debug: list[str],
) -> None:
    with Session(engine) as session:
        job = session.exec(select(IngestionJob).where(IngestionJob.id == job_id)).first()
        if job is None:
            return
        if str(job.status or "").strip().lower() == JOB_STATUS_CANCELED:
            return
        if job.status in TERMINAL_JOB_STATUSES and job.status != JOB_STATUS_RUNNING:
            return
        job.status = JOB_STATUS_COMPLETED
        job.processed_items = int(processed_items)
        job.success_count = int(success_count)
        job.failure_count = int(failure_count)
        job.bytes_total = int(max(0, bytes_total))
        job.bytes_persisted = int(max(0, bytes_persisted))
        job.bytes_indexed = int(max(0, bytes_indexed))
        job.items = [as_json_safe(item) for item in items]
        job.errors = [str(err) for err in errors]
        job.file_ids = list(dict.fromkeys([str(fid) for fid in file_ids if fid]))
        job.debug = [str(msg) for msg in debug][-200:]
        job.message = "Ingestion completed."
        job.date_finished = datetime.utcnow()
        job.date_updated = datetime.utcnow()
        session.add(job)
        session.commit()
    manager._inc_metric("jobs_completed")


def mark_failed(manager: Any, *, job_id: str, reason: str) -> None:
    with Session(engine) as session:
        job = session.exec(select(IngestionJob).where(IngestionJob.id == job_id)).first()
        if job is None:
            return
        if str(job.status or "").strip().lower() == JOB_STATUS_CANCELED:
            return
        if job.status in TERMINAL_JOB_STATUSES and job.status != JOB_STATUS_RUNNING:
            return
        job.status = JOB_STATUS_FAILED
        job.errors = [*(job.errors or []), str(reason)]
        job.message = "Ingestion failed."
        job.date_finished = datetime.utcnow()
        job.date_updated = datetime.utcnow()
        session.add(job)
        session.commit()
    manager._inc_metric("jobs_failed")
    manager._cleanup_file_payload(job_id)


def mark_canceled(*, job_id: str, reason: str) -> None:
    with Session(engine) as session:
        job = session.exec(select(IngestionJob).where(IngestionJob.id == job_id)).first()
        if job is None:
            return
        if job.status in TERMINAL_JOB_STATUSES and job.status != JOB_STATUS_RUNNING:
            return
        job.status = JOB_STATUS_CANCELED
        clean_reason = str(reason or "").strip() or "Canceled by user."
        if clean_reason not in list(job.errors or []):
            job.errors = [*list(job.errors or []), clean_reason]
        job.message = "Ingestion canceled."
        job.date_finished = datetime.utcnow()
        job.date_updated = datetime.utcnow()
        session.add(job)
        session.commit()


def cleanup_file_payload(*, job_id: str) -> None:
    if INGEST_KEEP_WORKDIR:
        return
    with Session(engine) as session:
        job = session.exec(select(IngestionJob).where(IngestionJob.id == job_id)).first()
        if job is None or job.kind != "files":
            return
        files_payload = list((job.payload or {}).get("files") or [])

    dirs_to_cleanup: set[Path] = set()
    for entry in files_payload:
        raw_path = str((entry or {}).get("path", "")).strip()
        if not raw_path:
            continue
        candidate = Path(raw_path)
        if candidate.exists() and candidate.is_file():
            try:
                candidate.unlink(missing_ok=True)
            except Exception:
                pass
        parent = candidate.parent
        if str(parent).startswith(str(INGEST_WORKDIR)):
            dirs_to_cleanup.add(parent)

    for directory in dirs_to_cleanup:
        if directory.exists() and directory.is_dir():
            try:
                shutil.rmtree(directory, ignore_errors=True)
            except Exception:
                pass
