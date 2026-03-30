from __future__ import annotations

from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from sqlmodel import Session, select

from api.context import get_context
from api.services.settings_service import load_user_settings
from ktem.db.engine import engine

from .config import INGEST_FILE_BATCH_SIZE, INGEST_URL_BATCH_SIZE
from .models import IngestionJob


def run_file_job(
    manager: Any,
    job_id: str,
    *,
    index_files_fn: Callable[..., dict[str, Any]],
    move_files_to_group_fn: Callable[..., dict[str, Any]],
) -> None:
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
    cancel_checker = manager._build_cancel_checker(job_id)

    try:
        for batch in manager._iterate_batches(files_payload, INGEST_FILE_BATCH_SIZE):
            manager._assert_job_not_canceled(job_id)

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
                manager._update_progress(
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
                    message="Unable to read the uploaded file batch.",
                )
                continue

            batch_names = [str(path.name or "file").strip() or "file" for path in batch_paths]
            batch_message = (
                f"Preparing {batch_names[0]} for indexing."
                if len(batch_names) == 1
                else f"Preparing {len(batch_names)} files for indexing."
            )
            batch_debug = [
                *all_debug,
                *[
                    f"Preparing {name} for indexing analysis."
                    for name in batch_names[:5]
                ],
            ]
            manager._update_progress(
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
                debug=batch_debug,
                message=batch_message,
            )

            try:
                response = index_files_fn(
                    context=context,
                    user_id=user_id,
                    file_paths=batch_paths,
                    index_id=index_id,
                    reindex=reindex,
                    settings=settings,
                    scope=scope,
                    uploaded_file_meta=batch_meta,
                    should_cancel=cancel_checker,
                )
            except Exception as exc:
                if exc.__class__.__name__ == "IndexingCanceledError":
                    canceled = exc
                    canceled_items = getattr(canceled, "items", None)
                    canceled_errors = getattr(canceled, "errors", None)
                    canceled_file_ids = getattr(canceled, "file_ids", None)
                    canceled_debug = getattr(canceled, "debug", None)
                    if isinstance(canceled_items, list) and canceled_items:
                        all_items.extend([dict(item) for item in canceled_items])
                    if isinstance(canceled_errors, list) and canceled_errors:
                        all_errors.extend([str(err) for err in canceled_errors])
                    if isinstance(canceled_file_ids, list) and canceled_file_ids:
                        all_file_ids.extend([str(fid) for fid in canceled_file_ids if fid])
                    if isinstance(canceled_debug, list) and canceled_debug:
                        all_debug.extend([str(msg) for msg in canceled_debug])
                    raise manager._canceled_error_cls(str(canceled)) from canceled
                raise

            batch_items = list(response.get("items") or [])
            batch_errors = [str(err) for err in list(response.get("errors") or [])]
            batch_file_ids = [str(fid) for fid in list(response.get("file_ids") or []) if fid]
            batch_debug = [str(msg) for msg in list(response.get("debug") or [])]

            all_items.extend(batch_items)
            all_errors.extend(batch_errors)
            all_file_ids.extend(batch_file_ids)
            all_debug.extend(batch_debug)

            processed += len(batch)
            batch_successes = sum(1 for item in batch_items if str(item.get("status", "")).lower() == "success")
            unmatched = max(0, len(batch) - len(batch_items))
            batch_failures = max(0, len(batch_items) - batch_successes) + unmatched
            success_count += batch_successes
            failure_count += batch_failures
            indexed_bytes = min(bytes_total, indexed_bytes + batch_bytes)

            manager._update_progress(
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
                message=(
                    "Indexing completed." if processed >= len(files_payload) else "Continuing file indexing."
                ),
            )

        manager._assert_job_not_canceled(job_id)
        if target_group_id and all_file_ids:
            try:
                move_result = move_files_to_group_fn(
                    context=context,
                    user_id=user_id,
                    index_id=index_id,
                    file_ids=all_file_ids,
                    group_id=target_group_id,
                )
                moved_ids = list(move_result.get("moved_ids") or [])
                manager._inc_metric("files_moved_to_group", amount=len(moved_ids))
                all_debug.append(f"Moved {len(moved_ids)} indexed file(s) to group {target_group_id}.")
            except Exception as exc:
                all_errors.append(f"Indexed files could not be moved to group: {exc}")

        manager._assert_job_not_canceled(job_id)
        manager._mark_completed(
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
        manager._cleanup_file_payload(job_id)
        manager._logger.info(
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
    except manager._canceled_error_cls:
        manager._delete_indexed_files_best_effort(
            user_id=user_id,
            index_id=index_id,
            file_ids=all_file_ids,
            job_id=job_id,
        )
        manager._cleanup_file_payload(job_id)
        raise


def run_url_job(
    manager: Any,
    job_id: str,
    *,
    index_urls_fn: Callable[..., dict[str, Any]],
) -> None:
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
        web_crawl_same_domain_only = bool(payload.get("web_crawl_same_domain_only", True))
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
    cancel_checker = manager._build_cancel_checker(job_id)

    try:
        for batch in manager._iterate_batches(urls, INGEST_URL_BATCH_SIZE):
            manager._assert_job_not_canceled(job_id)
            try:
                response = index_urls_fn(
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
                    should_cancel=cancel_checker,
                )
            except Exception as exc:
                if exc.__class__.__name__ == "IndexingCanceledError":
                    canceled = exc
                    canceled_items = getattr(canceled, "items", None)
                    canceled_errors = getattr(canceled, "errors", None)
                    canceled_file_ids = getattr(canceled, "file_ids", None)
                    canceled_debug = getattr(canceled, "debug", None)
                    if isinstance(canceled_items, list) and canceled_items:
                        all_items.extend([dict(item) for item in canceled_items])
                    if isinstance(canceled_errors, list) and canceled_errors:
                        all_errors.extend([str(err) for err in canceled_errors])
                    if isinstance(canceled_file_ids, list) and canceled_file_ids:
                        all_file_ids.extend([str(fid) for fid in canceled_file_ids if fid])
                    if isinstance(canceled_debug, list) and canceled_debug:
                        all_debug.extend([str(msg) for msg in canceled_debug])
                    raise manager._canceled_error_cls(str(canceled)) from canceled
                raise

            batch_items = list(response.get("items") or [])
            batch_errors = [str(err) for err in list(response.get("errors") or [])]
            batch_file_ids = [str(fid) for fid in list(response.get("file_ids") or []) if fid]
            batch_debug = [str(msg) for msg in list(response.get("debug") or [])]

            all_items.extend(batch_items)
            all_errors.extend(batch_errors)
            all_file_ids.extend(batch_file_ids)
            all_debug.extend(batch_debug)

            processed += len(batch)
            batch_successes = sum(1 for item in batch_items if str(item.get("status", "")).lower() == "success")
            unmatched = max(0, len(batch) - len(batch_items))
            batch_failures = max(0, len(batch_items) - batch_successes) + unmatched
            success_count += batch_successes
            failure_count += batch_failures

            manager._update_progress(
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

        manager._assert_job_not_canceled(job_id)
        manager._mark_completed(
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
    except manager._canceled_error_cls:
        manager._delete_indexed_files_best_effort(
            user_id=user_id,
            index_id=index_id,
            file_ids=all_file_ids,
            job_id=job_id,
        )
        raise
