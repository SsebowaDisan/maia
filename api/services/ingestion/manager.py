from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
import logging
from pathlib import Path
from queue import Empty, Queue
import shutil
import threading
from time import perf_counter
from typing import Any

from fastapi import HTTPException
from sqlalchemy import inspect, text
from sqlmodel import SQLModel, Session, select

from api.context import get_context
from api.services.settings_service import load_user_settings
from api.services.upload_service import index_files, index_urls, move_files_to_group
from ktem.db.engine import engine

from .config import (
    INGEST_FILE_BATCH_SIZE,
    INGEST_KEEP_WORKDIR,
    INGEST_URL_BATCH_SIZE,
    INGEST_WORKDIR,
    INGEST_WORKERS,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    TERMINAL_JOB_STATUSES,
)
from .models import IngestionJob
from .serialization import as_json_safe, job_to_payload

logger = logging.getLogger(__name__)


class IngestionJobManager:
    def __init__(self) -> None:
        SQLModel.metadata.create_all(engine)
        self._ensure_schema_columns()
        self._queue: Queue[str] = Queue()
        self._workers: list[threading.Thread] = []
        self._stop_event = threading.Event()
        self._started = False
        self._enqueue_lock = threading.Lock()
        self._metrics_lock = threading.Lock()
        self._metrics: dict[str, int] = {
            "jobs_created_files": 0,
            "jobs_created_urls": 0,
            "jobs_completed": 0,
            "jobs_failed": 0,
            "files_moved_to_group": 0,
        }

    def _ensure_schema_columns(self) -> None:
        required_int_columns = {
            "bytes_total": 0,
            "bytes_persisted": 0,
            "bytes_indexed": 0,
        }
        try:
            inspector = inspect(engine)
            existing_columns = {
                str(column.get("name", "")).strip().lower()
                for column in inspector.get_columns("maia_ingestion_job")
            }
        except Exception:
            return

        missing = [
            (name, default)
            for name, default in required_int_columns.items()
            if name.lower() not in existing_columns
        ]
        if not missing:
            return

        for column_name, default_value in missing:
            statement = text(
                f"ALTER TABLE maia_ingestion_job "
                f"ADD COLUMN {column_name} INTEGER NOT NULL DEFAULT {int(default_value)}"
            )
            try:
                with engine.begin() as connection:
                    connection.execute(statement)
            except Exception as exc:
                logger.warning(
                    "Unable to add ingestion schema column '%s': %s",
                    column_name,
                    exc,
                )

    def _inc_metric(self, key: str, amount: int = 1) -> None:
        if not key:
            return
        with self._metrics_lock:
            self._metrics[key] = int(self._metrics.get(key, 0)) + int(amount)

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._stop_event.clear()
        INGEST_WORKDIR.mkdir(parents=True, exist_ok=True)
        self._rehydrate_pending_jobs()
        for idx in range(INGEST_WORKERS):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"maia-ingestion-worker-{idx + 1}",
                daemon=True,
            )
            worker.start()
            self._workers.append(worker)

    def stop(self) -> None:
        if not self._started:
            return
        self._stop_event.set()
        for _ in self._workers:
            self._queue.put_nowait("")
        for worker in self._workers:
            worker.join(timeout=2)
        self._workers = []
        self._started = False

    def _rehydrate_pending_jobs(self) -> None:
        with Session(engine) as session:
            jobs = session.exec(
                select(IngestionJob).where(
                    IngestionJob.status.in_([JOB_STATUS_QUEUED, JOB_STATUS_RUNNING])
                )
            ).all()
            for job in jobs:
                # On process restart, previously running jobs are resumed from queue.
                job.status = JOB_STATUS_QUEUED
                job.message = "Recovered after service restart."
                job.date_updated = datetime.utcnow()
                session.add(job)
            session.commit()
            for job in jobs:
                self._queue.put_nowait(job.id)

    def create_file_job(
        self,
        user_id: str,
        *,
        index_id: int | None,
        reindex: bool,
        files: list[dict[str, Any]],
        group_id: str | None = None,
        scope: str = "persistent",
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

        self.enqueue(job.id)
        self._inc_metric("jobs_created_files")
        return created

    def create_url_job(
        self,
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

        self.enqueue(job.id)
        self._inc_metric("jobs_created_urls")
        return created

    def enqueue(self, job_id: str) -> None:
        with self._enqueue_lock:
            self._queue.put_nowait(job_id)

    def list_jobs(self, user_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        safe_limit = min(max(int(limit), 1), 200)
        with Session(engine) as session:
            jobs = session.exec(
                select(IngestionJob)
                .where(IngestionJob.user_id == user_id)
                .order_by(IngestionJob.date_created.desc())  # type: ignore[attr-defined]
                .limit(safe_limit)
            ).all()
        return [job_to_payload(job) for job in jobs]

    def get_job(self, user_id: str, job_id: str) -> dict[str, Any]:
        with Session(engine) as session:
            job = session.exec(select(IngestionJob).where(IngestionJob.id == job_id)).first()
            if job is None:
                raise HTTPException(status_code=404, detail="Ingestion job not found.")
            if job.user_id != user_id:
                raise HTTPException(status_code=403, detail="Access denied.")
            return job_to_payload(job)

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                job_id = self._queue.get(timeout=0.5)
            except Empty:
                continue
            if not job_id:
                self._queue.task_done()
                continue
            try:
                self._process_job(job_id)
            finally:
                self._queue.task_done()

    def _process_job(self, job_id: str) -> None:
        job_kind = ""
        with Session(engine) as session:
            job = session.exec(select(IngestionJob).where(IngestionJob.id == job_id)).first()
            if job is None:
                return
            if job.status in TERMINAL_JOB_STATUSES:
                return
            job_kind = str(job.kind or "")

            job.status = JOB_STATUS_RUNNING
            job.message = "Indexing in progress."
            job.date_started = datetime.utcnow()
            job.date_updated = datetime.utcnow()
            session.add(job)
            session.commit()

        try:
            if job_kind == "files":
                self._run_file_job(job_id)
            elif job_kind == "urls":
                self._run_url_job(job_id)
            else:
                raise RuntimeError(f"Unsupported ingestion job kind: {job_kind}")
        except Exception as exc:
            self._mark_failed(job_id, str(exc))

    def _iterate_batches(self, values: list[Any], batch_size: int) -> Iterable[list[Any]]:
        for start in range(0, len(values), batch_size):
            yield values[start : start + batch_size]

    def _run_file_job(self, job_id: str) -> None:
        started_at = perf_counter()
        with Session(engine) as session:
            job = session.exec(select(IngestionJob).where(IngestionJob.id == job_id)).first()
            if job is None:
                return
            payload = job.payload or {}
            files_payload = list(payload.get("files") or [])
            target_group_id = str(payload.get("target_group_id") or "").strip() or None
            scope = str(payload.get("scope") or "persistent")
            user_id = job.user_id
            index_id = job.index_id
            reindex = bool(job.reindex)
            bytes_total = int(getattr(job, "bytes_total", 0) or 0)
            bytes_persisted = int(getattr(job, "bytes_persisted", 0) or 0)
            if bytes_total <= 0:
                bytes_total = sum(int((entry or {}).get("size") or 0) for entry in files_payload)
                bytes_persisted = max(bytes_persisted, bytes_total)

        context = get_context()
        settings = load_user_settings(context=context, user_id=user_id)
        all_items: list[dict[str, Any]] = []
        all_errors: list[str] = []
        all_file_ids: list[str] = []
        all_debug: list[str] = []
        processed = 0
        success_count = 0
        failure_count = 0
        indexed_bytes = 0

        for batch in self._iterate_batches(files_payload, INGEST_FILE_BATCH_SIZE):
            batch_paths: list[Path] = []
            batch_meta: dict[str, dict[str, Any]] = {}
            batch_bytes = 0
            for entry in batch:
                raw_path = str((entry or {}).get("path", "")).strip()
                if not raw_path:
                    continue
                candidate = Path(raw_path)
                if candidate.exists() and candidate.is_file():
                    batch_paths.append(candidate)
                    try:
                        resolved = str(candidate.resolve())
                    except Exception:
                        resolved = raw_path
                    batch_meta[resolved] = dict(entry or {})
                    file_size = int((entry or {}).get("size") or 0)
                    if file_size <= 0:
                        try:
                            file_size = int(candidate.stat().st_size)
                        except Exception:
                            file_size = 0
                    batch_bytes += max(0, file_size)

            if not batch_paths:
                processed += len(batch)
                failure_count += len(batch)
                all_errors.append("File batch had no readable files on disk.")
                indexed_bytes = min(bytes_total, indexed_bytes + batch_bytes)
                self._update_progress(
                    job_id=job_id,
                    processed_items=processed,
                    success_count=success_count,
                    failure_count=failure_count,
                    bytes_total=bytes_total,
                    bytes_persisted=bytes_persisted,
                    bytes_indexed=indexed_bytes,
                    items=all_items,
                    errors=all_errors,
                    file_ids=all_file_ids,
                    debug=all_debug,
                )
                continue

            response = index_files(
                context=context,
                user_id=user_id,
                file_paths=batch_paths,
                index_id=index_id,
                reindex=reindex,
                settings=settings,
                scope=scope,
                uploaded_file_meta=batch_meta,
            )
            batch_items = list(response.get("items") or [])
            batch_errors = [str(err) for err in list(response.get("errors") or [])]
            batch_file_ids = [str(fid) for fid in list(response.get("file_ids") or []) if fid]
            batch_debug = [str(msg) for msg in list(response.get("debug") or [])]

            all_items.extend(batch_items)
            all_errors.extend(batch_errors)
            all_file_ids.extend(batch_file_ids)
            all_debug.extend(batch_debug)

            processed += len(batch)
            batch_successes = sum(
                1 for item in batch_items if str(item.get("status", "")).lower() == "success"
            )
            # Include implicit failures for files that do not emit item status.
            unmatched = max(0, len(batch) - len(batch_items))
            batch_failures = max(0, len(batch_items) - batch_successes) + unmatched
            success_count += batch_successes
            failure_count += batch_failures
            indexed_bytes = min(bytes_total, indexed_bytes + batch_bytes)

            self._update_progress(
                job_id=job_id,
                processed_items=processed,
                success_count=success_count,
                failure_count=failure_count,
                bytes_total=bytes_total,
                bytes_persisted=bytes_persisted,
                bytes_indexed=indexed_bytes,
                items=all_items,
                errors=all_errors,
                file_ids=all_file_ids,
                debug=all_debug,
            )

        if target_group_id and all_file_ids:
            try:
                move_result = move_files_to_group(
                    context=context,
                    user_id=user_id,
                    index_id=index_id,
                    file_ids=all_file_ids,
                    group_id=target_group_id,
                    group_name=None,
                    mode="append",
                )
                moved_ids = list(move_result.get("moved_ids") or [])
                self._inc_metric("files_moved_to_group", amount=len(moved_ids))
                all_debug.append(
                    f"Moved {len(moved_ids)} indexed file(s) to group {target_group_id}."
                )
            except Exception as exc:
                all_errors.append(f"Indexed files could not be moved to group: {exc}")

        self._mark_completed(
            job_id=job_id,
            processed_items=processed,
            success_count=success_count,
            failure_count=failure_count,
            bytes_total=bytes_total,
            bytes_persisted=bytes_persisted,
            bytes_indexed=min(bytes_total, max(0, indexed_bytes)),
            items=all_items,
            errors=all_errors,
            file_ids=all_file_ids,
            debug=all_debug,
        )
        self._cleanup_file_payload(job_id)
        logger.info(
            "Ingestion file job completed",
            extra={
                "job_id": job_id,
                "user_id": user_id,
                "index_id": index_id,
                "processed_items": processed,
                "success_count": success_count,
                "failure_count": failure_count,
                "bytes_total": bytes_total,
                "elapsed_ms": int((perf_counter() - started_at) * 1000),
            },
        )

    def _run_url_job(self, job_id: str) -> None:
        with Session(engine) as session:
            job = session.exec(select(IngestionJob).where(IngestionJob.id == job_id)).first()
            if job is None:
                return
            payload = job.payload or {}
            urls = list(payload.get("urls") or [])
            user_id = job.user_id
            index_id = job.index_id
            reindex = bool(job.reindex)
            web_crawl_depth = int(payload.get("web_crawl_depth", 0) or 0)
            web_crawl_max_pages = int(payload.get("web_crawl_max_pages", 0) or 0)
            web_crawl_same_domain_only = bool(
                payload.get("web_crawl_same_domain_only", True)
            )
            include_pdfs = bool(payload.get("include_pdfs", True))
            include_images = bool(payload.get("include_images", True))

        context = get_context()
        settings = load_user_settings(context=context, user_id=user_id)
        all_items: list[dict[str, Any]] = []
        all_errors: list[str] = []
        all_file_ids: list[str] = []
        all_debug: list[str] = []
        processed = 0
        success_count = 0
        failure_count = 0

        for batch in self._iterate_batches(urls, INGEST_URL_BATCH_SIZE):
            response = index_urls(
                context=context,
                user_id=user_id,
                urls=batch,
                index_id=index_id,
                reindex=reindex,
                settings=settings,
                web_crawl_depth=web_crawl_depth,
                web_crawl_max_pages=web_crawl_max_pages,
                web_crawl_same_domain_only=web_crawl_same_domain_only,
                include_pdfs=include_pdfs,
                include_images=include_images,
            )
            batch_items = list(response.get("items") or [])
            batch_errors = [str(err) for err in list(response.get("errors") or [])]
            batch_file_ids = [str(fid) for fid in list(response.get("file_ids") or []) if fid]
            batch_debug = [str(msg) for msg in list(response.get("debug") or [])]

            all_items.extend(batch_items)
            all_errors.extend(batch_errors)
            all_file_ids.extend(batch_file_ids)
            all_debug.extend(batch_debug)

            processed += len(batch)
            batch_successes = sum(
                1 for item in batch_items if str(item.get("status", "")).lower() == "success"
            )
            unmatched = max(0, len(batch) - len(batch_items))
            batch_failures = max(0, len(batch_items) - batch_successes) + unmatched
            success_count += batch_successes
            failure_count += batch_failures

            self._update_progress(
                job_id=job_id,
                processed_items=processed,
                success_count=success_count,
                failure_count=failure_count,
                bytes_total=0,
                bytes_persisted=0,
                bytes_indexed=0,
                items=all_items,
                errors=all_errors,
                file_ids=all_file_ids,
                debug=all_debug,
            )

        self._mark_completed(
            job_id=job_id,
            processed_items=processed,
            success_count=success_count,
            failure_count=failure_count,
            bytes_total=0,
            bytes_persisted=0,
            bytes_indexed=0,
            items=all_items,
            errors=all_errors,
            file_ids=all_file_ids,
            debug=all_debug,
        )

    def _update_progress(
        self,
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
            # Preserve insertion order while deduplicating.
            dedup_ids = list(dict.fromkeys([str(file_id) for file_id in file_ids if file_id]))
            job.file_ids = dedup_ids
            job.debug = [str(msg) for msg in debug][-200:]
            job.date_updated = datetime.utcnow()
            session.add(job)
            session.commit()

    def _mark_completed(
        self,
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
        self._inc_metric("jobs_completed")

    def _mark_failed(self, job_id: str, reason: str) -> None:
        with Session(engine) as session:
            job = session.exec(select(IngestionJob).where(IngestionJob.id == job_id)).first()
            if job is None:
                return
            job.status = JOB_STATUS_FAILED
            job.errors = [*(job.errors or []), str(reason)]
            job.message = "Ingestion failed."
            job.date_finished = datetime.utcnow()
            job.date_updated = datetime.utcnow()
            session.add(job)
            session.commit()
        self._inc_metric("jobs_failed")
        self._cleanup_file_payload(job_id)

    def _cleanup_file_payload(self, job_id: str) -> None:
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
