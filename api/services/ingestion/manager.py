from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
import logging
from queue import Empty, Queue
import threading
from time import perf_counter
from typing import Any

from fastapi import HTTPException
from sqlalchemy import inspect, text
from sqlmodel import SQLModel, Session, select

from api.context import get_context
from api.services.settings_service import load_user_settings
from ktem.db.engine import engine

from .config import (
    JOB_STATUS_CANCELED,
    INGEST_WORKERS,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    TERMINAL_JOB_STATUSES,
    INGEST_WORKDIR,
)
from .manager_api_helpers import (
    cancel_job as cancel_job_helper,
    create_file_job as create_file_job_helper,
    create_url_job as create_url_job_helper,
    get_job as get_job_helper,
    list_jobs as list_jobs_helper,
)
from .manager_execution_helpers import run_file_job, run_url_job
from .manager_state_helpers import (
    cleanup_file_payload,
    mark_canceled,
    mark_completed,
    mark_failed,
    update_progress,
)
from .models import IngestionJob
from .serialization import job_to_payload

logger = logging.getLogger(__name__)


class IngestionJobCanceledError(RuntimeError):
    pass


def _delete_indexed_files_api(*, context: Any, user_id: str, index_id: int | None, file_ids: list[str]) -> None:
    from api.services.upload_service import delete_indexed_files

    delete_indexed_files(
        context=context,
        user_id=user_id,
        index_id=index_id,
        file_ids=file_ids,
    )


def _index_files_api(
    *,
    context: Any,
    user_id: str,
    file_paths: list[Any],
    index_id: int | None,
    reindex: bool,
    settings: dict[str, Any],
    scope: str,
    uploaded_file_meta: dict[str, dict[str, Any]],
    should_cancel: Any,
) -> dict[str, Any]:
    from api.services.upload_service import index_files

    return index_files(
        context=context,
        user_id=user_id,
        file_paths=file_paths,
        index_id=index_id,
        reindex=reindex,
        settings=settings,
        scope=scope,
        uploaded_file_meta=uploaded_file_meta,
        should_cancel=should_cancel,
    )


def _index_urls_api(
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
    should_cancel: Any,
) -> dict[str, Any]:
    from api.services.upload_service import index_urls

    return index_urls(
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
        should_cancel=should_cancel,
    )


def _move_files_to_group_api(
    *,
    context: Any,
    user_id: str,
    index_id: int | None,
    file_ids: list[str],
    group_id: str,
) -> dict[str, Any]:
    from api.services.upload_service import move_files_to_group

    return move_files_to_group(
        context=context,
        user_id=user_id,
        index_id=index_id,
        file_ids=file_ids,
        group_id=group_id,
        group_name=None,
        mode="append",
    )


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
        self._logger = logger
        self._canceled_error_cls = IngestionJobCanceledError

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
        return create_file_job_helper(
            self,
            user_id,
            index_id=index_id,
            reindex=reindex,
            files=files,
            group_id=group_id,
            scope=scope,
        )

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
        return create_url_job_helper(
            self,
            user_id,
            index_id=index_id,
            reindex=reindex,
            urls=urls,
            web_crawl_depth=web_crawl_depth,
            web_crawl_max_pages=web_crawl_max_pages,
            web_crawl_same_domain_only=web_crawl_same_domain_only,
            include_pdfs=include_pdfs,
            include_images=include_images,
        )

    def enqueue(self, job_id: str) -> None:
        with self._enqueue_lock:
            self._queue.put_nowait(job_id)

    def list_jobs(self, user_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        return list_jobs_helper(user_id, limit=limit)

    def get_job(self, user_id: str, job_id: str) -> dict[str, Any]:
        return get_job_helper(user_id, job_id)

    def cancel_job(self, user_id: str, job_id: str) -> dict[str, Any]:
        return cancel_job_helper(self, user_id, job_id)

    def _is_job_canceled(self, job_id: str) -> bool:
        with Session(engine) as session:
            job = session.exec(select(IngestionJob).where(IngestionJob.id == job_id)).first()
            if job is None:
                return True
            return str(job.status or "").strip().lower() == JOB_STATUS_CANCELED

    def _assert_job_not_canceled(self, job_id: str) -> None:
        if self._is_job_canceled(job_id):
            raise IngestionJobCanceledError("Ingestion canceled by user.")

    def _build_cancel_checker(
        self,
        job_id: str,
        *,
        min_interval_seconds: float = 0.4,
    ):
        last_check_at = 0.0
        is_canceled = False

        def _check() -> bool:
            nonlocal last_check_at, is_canceled
            if is_canceled:
                return True
            now = perf_counter()
            if (now - last_check_at) < max(0.05, float(min_interval_seconds)):
                return False
            last_check_at = now
            is_canceled = self._is_job_canceled(job_id)
            return is_canceled

        return _check

    def _delete_indexed_files_best_effort(
        self,
        *,
        user_id: str,
        index_id: int | None,
        file_ids: list[str],
        job_id: str,
    ) -> None:
        dedup_ids = list(dict.fromkeys([str(fid) for fid in file_ids if fid]))
        if not dedup_ids:
            return
        try:
            _delete_indexed_files_api(
                context=get_context(),
                user_id=user_id,
                index_id=index_id,
                file_ids=dedup_ids,
            )
        except Exception as exc:
            logger.warning(
                "Failed to cleanup indexed files for canceled ingestion job",
                extra={
                    "job_id": job_id,
                    "user_id": user_id,
                    "index_id": index_id,
                    "file_count": len(dedup_ids),
                    "error": str(exc),
                },
            )

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
            if job is None or job.status in TERMINAL_JOB_STATUSES:
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
        except IngestionJobCanceledError as exc:
            self._mark_canceled(job_id, str(exc))
        except Exception as exc:
            self._mark_failed(job_id, str(exc))

    def _iterate_batches(self, values: list[Any], batch_size: int) -> Iterable[list[Any]]:
        for start in range(0, len(values), batch_size):
            yield values[start : start + batch_size]

    def _run_file_job(self, job_id: str) -> None:
        run_file_job(
            self,
            job_id,
            index_files_fn=_index_files_api,
            move_files_to_group_fn=_move_files_to_group_api,
        )

    def _run_url_job(self, job_id: str) -> None:
        run_url_job(self, job_id, index_urls_fn=_index_urls_api)

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
        message: str | None = None,
    ) -> None:
        update_progress(
            job_id=job_id,
            processed_items=processed_items,
            success_count=success_count,
            failure_count=failure_count,
            bytes_total=bytes_total,
            bytes_persisted=bytes_persisted,
            bytes_indexed=bytes_indexed,
            items=items,
            errors=errors,
            file_ids=file_ids,
            debug=debug,
            message=message,
        )

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
        mark_completed(
            self,
            job_id=job_id,
            processed_items=processed_items,
            success_count=success_count,
            failure_count=failure_count,
            bytes_total=bytes_total,
            bytes_persisted=bytes_persisted,
            bytes_indexed=bytes_indexed,
            items=items,
            errors=errors,
            file_ids=file_ids,
            debug=debug,
        )

    def _mark_failed(self, job_id: str, reason: str) -> None:
        mark_failed(self, job_id=job_id, reason=reason)

    def _mark_canceled(self, job_id: str, reason: str) -> None:
        mark_canceled(job_id=job_id, reason=reason)
        self._cleanup_file_payload(job_id)

    def _cleanup_file_payload(self, job_id: str) -> None:
        cleanup_file_payload(job_id=job_id)
