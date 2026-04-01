from __future__ import annotations

import logging
from mimetypes import guess_type
from pathlib import Path
from time import perf_counter
import uuid

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from api.auth import get_current_user, get_current_user_id, require_org_admin
from api.context import get_context
from api.models.user import User
from api.schemas import (
    BulkDeleteFilesRequest,
    BulkDeleteFilesResponse,
    BulkDeleteUrlsRequest,
    BulkDeleteUrlsResponse,
    CreateFileGroupRequest,
    DeleteFileGroupResponse,
    FileListResponse,
    FileGroupListResponse,
    FileGroupResponse,
    IngestionJobResponse,
    MoveFilesToGroupRequest,
    MoveFilesToGroupResponse,
    RenameFileGroupRequest,
    UploadResponse,
    UploadUrlsRequest,
)
from api.services.ingestion_service import (
    INGEST_WORKDIR,
    UPLOAD_MAX_FILE_SIZE_BYTES,
    UPLOAD_MAX_TOTAL_BYTES,
    UPLOAD_STREAM_CHUNK_BYTES,
    UPLOAD_USE_UNIFIED_PERSIST,
    get_ingestion_manager,
)
from api.services.settings_service import load_user_settings
from api.services.observability.citation_trace import begin_trace, end_trace, record_trace_event
from api.services.upload_service import (
    create_file_group,
    delete_file_group,
    delete_indexed_files,
    delete_indexed_urls,
    index_files,
    index_urls,
    list_file_groups,
    list_indexed_files,
    move_files_to_group,
    rename_file_group,
    resolve_indexed_file_path,
)
from api.services.upload.common import normalize_upload_scope
from decouple import config as decouple_config
from api.services.upload.pdf_highlight_locator import locate_pdf_highlight_target
from api.services.rag.bridge import get_highlight_target_bridge, resolve_registered_source_path

# New RAG pipeline (feature flag)
_USE_NEW_RAG = decouple_config("MAIA_USE_NEW_RAG", default="true", cast=str).lower() == "true"
from .uploads_support import (
    bytes_to_human,
    cleanup_persisted_uploads,
    enforce_upload_limits,
    persist_uploaded_files,
    store_upload_file,
)
from . import uploads_support as _uploads_support

router = APIRouter(prefix="/api/uploads", tags=["uploads"])
logger = logging.getLogger(__name__)


def _assert_upload_write_allowed(user: User, scope: str | None) -> None:
    """Allow user_temp uploads for all users; restrict library writes to admins."""
    normalized_scope = normalize_upload_scope(scope)
    if normalized_scope == "user_temp":
        return
    if user.role not in {"org_admin", "super_admin"}:
        raise HTTPException(
            status_code=403,
            detail="Admin privileges are required to upload to the file library.",
        )


async def _store_upload_file(upload: UploadFile, directory: Path) -> dict[str, object]:
    # Keep test and integration monkeypatch behavior compatible with previous in-module implementation.
    _uploads_support.UPLOAD_MAX_FILE_SIZE_BYTES = UPLOAD_MAX_FILE_SIZE_BYTES
    _uploads_support.UPLOAD_STREAM_CHUNK_BYTES = UPLOAD_STREAM_CHUNK_BYTES
    return await store_upload_file(upload, directory)
async def _persist_uploaded_files_sequential(files: list[UploadFile]) -> list[dict[str, object]]:
    if not files:
        raise HTTPException(status_code=400, detail="No files were provided.")

    # Validate file types before persisting
    _SUPPORTED_EXTENSIONS = {
        ".pdf", ".txt", ".md", ".csv", ".json", ".html", ".htm", ".xml",
        ".doc", ".docx", ".xls", ".xlsx", ".pptx", ".rtf", ".odt",
        ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp",
        ".py", ".js", ".ts", ".java", ".c", ".cpp", ".go", ".rs", ".rb",
    }
    for upload in files:
        name = str(upload.filename or "").strip()
        ext = name[name.rfind("."):].lower() if "." in name else ""
        if ext and ext not in _SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: '{ext}'. Supported: PDF, images, documents, text, code files.",
            )

    job_dir = INGEST_WORKDIR / "incoming" / uuid.uuid4().hex
    job_dir.mkdir(parents=True, exist_ok=True)
    persisted: list[dict[str, object]] = []
    for upload in files:
        persisted.append(await _store_upload_file(upload, job_dir))
    total_bytes = sum(int((item or {}).get("size") or 0) for item in persisted)
    if total_bytes > UPLOAD_MAX_TOTAL_BYTES:
        cleanup_persisted_uploads(persisted)
        raise HTTPException(
            status_code=413,
            detail=(
                "Combined file size exceeds max upload size. "
                f"Max total is {bytes_to_human(UPLOAD_MAX_TOTAL_BYTES)}."
            ),
        )
    return persisted


@router.post("/files", response_model=UploadResponse, deprecated=True)
async def upload_files(
    request: Request,
    response: Response,
    files: list[UploadFile] = File(default_factory=list),
    index_id: int | None = Form(default=None),
    reindex: bool = Form(default=True),
    scope: str = Form(default="persistent"),
    user: User = Depends(get_current_user),
):
    user_id = user.id
    _assert_upload_write_allowed(user, scope)
    logger.warning(
        "Deprecated sync file upload endpoint used",
        extra={"user_id": user_id, "index_id": index_id, "scope": scope},
    )
    response.headers["X-Maia-Deprecated"] = "true"
    response.headers["Warning"] = '299 - "Deprecated endpoint: use /api/uploads/files/jobs"'
    enforce_upload_limits(files, request)
    context = get_context()
    settings = load_user_settings(context=context, user_id=user_id)
    started_at = perf_counter()
    persisted_files: list[dict[str, object]] = []
    trace = begin_trace(
        kind="upload",
        user_id=user_id,
        metadata={
            "index_id": index_id,
            "reindex": bool(reindex),
            "scope": str(scope or "persistent"),
        },
    )
    response.headers["X-Maia-Trace-Id"] = trace.trace_id

    try:
        record_trace_event(
            "upload.received",
            {
                "file_count": len(files),
                "file_names": [str(item.filename or "") for item in files[:20]],
                "scope": str(scope or "persistent"),
                "index_id": index_id,
                "reindex": bool(reindex),
            },
        )
        if UPLOAD_USE_UNIFIED_PERSIST:
            persisted_files = await persist_uploaded_files(files)
        else:
            persisted_files = await _persist_uploaded_files_sequential(files)

        record_trace_event(
            "upload.persisted",
            {
                "persisted_file_count": len(persisted_files),
                "persisted_bytes": sum(int((item or {}).get("size") or 0) for item in persisted_files),
                "persisted_names": [str((item or {}).get("name") or "") for item in persisted_files[:20]],
            },
        )
        file_paths = [Path(str(item.get("path", ""))) for item in persisted_files]
        uploaded_file_meta: dict[str, dict[str, object]] = {}
        for item in persisted_files:
            raw_path = str((item or {}).get("path") or "").strip()
            if not raw_path:
                continue
            try:
                resolved = str(Path(raw_path).resolve())
            except Exception:
                resolved = raw_path
            uploaded_file_meta[resolved] = dict(item)
        upload_result = await run_in_threadpool(
            index_files,
            context=context,
            user_id=user_id,
            file_paths=file_paths,
            index_id=index_id,
            reindex=reindex,
            settings=settings,
            scope=scope,
            uploaded_file_meta=uploaded_file_meta,
        )
        if isinstance(upload_result, dict):
            debug_rows = upload_result.setdefault("debug", [])
            if isinstance(debug_rows, list):
                debug_rows.append(f"trace_id={trace.trace_id}")
            record_trace_event(
                "upload.index_completed",
                {
                    "index_id": upload_result.get("index_id"),
                    "file_ids": list(upload_result.get("file_ids") or []),
                    "error_count": len(upload_result.get("errors") or []),
                    "item_count": len(upload_result.get("items") or []),
                },
            )
        return upload_result
    except HTTPException as exc:
        record_trace_event(
            "upload.http_error",
            {"status_code": exc.status_code, "detail": str(exc.detail or "")[:500]},
        )
        raise
    except Exception as exc:
        record_trace_event("upload.exception", {"detail": str(exc)[:500]})
        raise
    finally:
        cleanup_persisted_uploads(persisted_files)
        elapsed_ms = int((perf_counter() - started_at) * 1000)
        record_trace_event("upload.completed", {"elapsed_ms": elapsed_ms})
        logger.info(
            "Sync file upload request completed",
            extra={
                "user_id": user_id,
                "index_id": index_id,
                "scope": scope,
                "file_count": len(files),
                "persisted_file_count": len(persisted_files),
                "persisted_bytes": sum(int((item or {}).get("size") or 0) for item in persisted_files),
                "elapsed_ms": elapsed_ms,
            },
        )
        end_trace(trace, level=logging.INFO)


@router.post("/files/jobs", response_model=IngestionJobResponse)
async def create_file_ingestion_job(
    request: Request,
    response: Response,
    files: list[UploadFile] = File(default_factory=list),
    index_id: int | None = Form(default=None),
    reindex: bool = Form(default=True),
    group_id: str | None = Form(default=None),
    scope: str = Form(default="persistent"),
    user: User = Depends(get_current_user),
):
    user_id = user.id
    _assert_upload_write_allowed(user, scope)
    enforce_upload_limits(files, request)
    started_at = perf_counter()
    trace = begin_trace(
        kind="upload_job",
        user_id=user_id,
        metadata={
            "index_id": index_id,
            "reindex": bool(reindex),
            "group_id": str(group_id or ""),
            "scope": str(scope or "persistent"),
        },
    )
    response.headers["X-Maia-Trace-Id"] = trace.trace_id
    try:
        persisted = (
            await persist_uploaded_files(files)
            if UPLOAD_USE_UNIFIED_PERSIST
            else await _persist_uploaded_files_sequential(files)
        )
        record_trace_event(
            "upload_job.persisted",
            {
                "file_count": len(persisted),
                "persisted_names": [str((item or {}).get("name") or "") for item in persisted[:20]],
            },
        )
        total_bytes = sum(int((item or {}).get("size") or 0) for item in persisted)

        # ── New RAG pipeline ingestion (background) ────────────────────
        from api.services.rag.bridge import run_rag_ingest_bridge
        import asyncio

        job_id = f"job_{uuid.uuid4().hex[:12]}"

        # Return job immediately — ingestion runs in background
        job = IngestionJobResponse(
            id=job_id,
            user_id=user_id,
            kind="file",
            status="running",
            index_id=index_id,
            reindex=reindex,
            total_items=len(persisted),
            processed_items=0,
            success_count=0,
            failure_count=0,
            bytes_total=total_bytes,
            bytes_persisted=total_bytes,
            bytes_indexed=0,
            items=_build_items_aligned(persisted, [], []),
            errors=[],
            file_ids=[],
            debug=[f"trace_id={trace.trace_id}", "pipeline=new_rag"],
            message=f"Ingesting {len(persisted)} file(s) — processing in background",
        )
        _store_new_pipeline_job(job)

        # Run ingestion in background task
        async def _run_background_ingestion():
            file_ids = []
            errors = []
            success_count = 0
            for pf in persisted:
                file_path = str(pf.get("path") or "")
                file_name = str(pf.get("name") or "")
                if not file_path:
                    errors.append(f"No path for {file_name}")
                    continue
                try:
                    logger.info("RAG ingest starting: file=%s path=%s", file_name, file_path)
                    is_composer_upload = str(scope or "").strip().lower() == "chat_temp"
                    result = await run_rag_ingest_bridge(
                        file_path=file_path,
                        group_id=str(group_id or ""),
                        owner_id=user_id,
                        metadata={"index_id": index_id, "scope": scope, "reindex": reindex},
                        fast=is_composer_upload,
                    )
                    logger.info("RAG ingest result: file=%s status=%s", file_name, result.get("status"))
                    if result.get("source_id"):
                        file_ids.append(result["source_id"])
                        success_count += 1
                    elif result.get("error"):
                        errors.append(f"{file_name}: {result['error']}")
                except Exception as exc:
                    logger.exception("RAG ingest exception: file=%s", file_name)
                    errors.append(f"{file_name}: {exc}")

            # Update job with final status
            completed_job = IngestionJobResponse(
                id=job_id,
                user_id=user_id,
                kind="file",
                status="completed" if not errors else "completed_with_errors",
                index_id=index_id,
                reindex=reindex,
                total_items=len(persisted),
                processed_items=len(persisted),
                success_count=success_count,
                failure_count=len(errors),
                bytes_total=total_bytes,
                bytes_persisted=total_bytes,
                bytes_indexed=total_bytes if success_count > 0 else 0,
                items=_build_items_aligned(persisted, file_ids, errors),
                errors=errors,
                file_ids=file_ids,
                debug=[f"trace_id={trace.trace_id}", "pipeline=new_rag"],
                message=f"Ingested {success_count}/{len(persisted)} files via new RAG pipeline",
            )
            _store_new_pipeline_job(completed_job)
            record_trace_event(
                "upload_job.completed_new_pipeline",
                {
                    "job_id": job_id,
                    "file_count": len(persisted),
                    "success_count": success_count,
                    "error_count": len(errors),
                },
            )
            logger.info(
                "Background ingestion completed",
                extra={
                    "user_id": user_id,
                    "job_id": job_id,
                    "success_count": success_count,
                    "elapsed_ms": int((perf_counter() - started_at) * 1000),
                },
            )

        asyncio.ensure_future(_run_background_ingestion())
        return job
    except HTTPException as exc:
        record_trace_event(
            "upload_job.http_error",
            {"status_code": exc.status_code, "detail": str(exc.detail or "")[:500]},
        )
        raise
    except Exception as exc:
        record_trace_event("upload_job.exception", {"detail": str(exc)[:500]})
        raise
    finally:
        record_trace_event("upload_job.completed", {"elapsed_ms": int((perf_counter() - started_at) * 1000)})
        end_trace(trace, level=logging.INFO)


@router.post("/urls", response_model=UploadResponse)
def upload_urls(
    payload: UploadUrlsRequest,
    user: User = Depends(require_org_admin),
):
    user_id = user.id
    context = get_context()
    settings = load_user_settings(context=context, user_id=user_id)
    return index_urls(
        context=context,
        user_id=user_id,
        urls=payload.urls,
        index_id=payload.index_id,
        reindex=payload.reindex,
        settings=settings,
        web_crawl_depth=payload.web_crawl_depth,
        web_crawl_max_pages=payload.web_crawl_max_pages,
        web_crawl_same_domain_only=payload.web_crawl_same_domain_only,
        include_pdfs=payload.include_pdfs,
        include_images=payload.include_images,
    )


@router.post("/urls/jobs", response_model=IngestionJobResponse)
async def create_url_ingestion_job(
    payload: UploadUrlsRequest,
    user: User = Depends(require_org_admin),
):
    user_id = user.id
    from api.services.rag.bridge import run_rag_ingest_url_bridge

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    file_ids = []
    errors = []
    success_count = 0

    for url in (payload.urls or []):
        try:
            result = await run_rag_ingest_url_bridge(
                url=url,
                group_id="",
                owner_id=user_id,
            )
            if result.get("source_id"):
                file_ids.append(result["source_id"])
                success_count += 1
            elif result.get("error"):
                errors.append(f"{url}: {result['error']}")
        except Exception as exc:
            errors.append(f"{url}: {exc}")

    job = IngestionJobResponse(
        id=job_id,
        user_id=user_id,
        kind="url",
        status="completed" if not errors else "completed_with_errors",
        index_id=payload.index_id,
        reindex=payload.reindex,
        total_items=len(payload.urls or []),
        processed_items=len(payload.urls or []),
        success_count=success_count,
        failure_count=len(errors),
        items=[],
        errors=errors,
        file_ids=file_ids,
        debug=["pipeline=new_rag"],
        message=f"Ingested {success_count}/{len(payload.urls or [])} URLs via new RAG pipeline",
    )
    _store_new_pipeline_job(job)
    return job


def _build_items_aligned(
    persisted: list[dict[str, object]],
    file_ids: list[str],
    errors: list[str],
) -> list[dict[str, Any]]:
    """Build items array aligned 1:1 with the original persisted files.

    The frontend maps results by index, so we must return one item per
    persisted file — even if that file failed. Uses "success" (not
    "completed") because the frontend checks `item.status === "success"`.
    """
    items: list[dict[str, Any]] = []
    fid_idx = 0
    error_idx = 0

    for pf in persisted:
        file_name = str(pf.get("name", ""))
        # Check if this file has a matching error
        file_errored = False
        for err in errors:
            if file_name in err:
                file_errored = True
                break

        if file_errored:
            items.append({
                "name": file_name,
                "source_id": "",
                "status": "failed",
                "rag_ready": False,
                "citation_ready": False,
            })
        elif fid_idx < len(file_ids):
            items.append({
                "name": file_name,
                "source_id": file_ids[fid_idx],
                "status": "success",
                "rag_ready": True,
                "citation_ready": True,
            })
            fid_idx += 1
        else:
            items.append({
                "name": file_name,
                "source_id": "",
                "status": "failed",
                "rag_ready": False,
                "citation_ready": False,
            })

    return items


# In-memory store for new pipeline jobs (so GET /jobs/{id} can find them)
_new_pipeline_jobs: dict[str, IngestionJobResponse] = {}


def _store_new_pipeline_job(job: IngestionJobResponse) -> None:
    """Store a completed new-pipeline job so the polling endpoint can find it."""
    _new_pipeline_jobs[job.id] = job
    # Keep only last 200 jobs in memory
    if len(_new_pipeline_jobs) > 200:
        oldest = list(_new_pipeline_jobs.keys())[:100]
        for k in oldest:
            _new_pipeline_jobs.pop(k, None)


@router.get("/jobs", response_model=list[IngestionJobResponse])
def list_ingestion_jobs(
    limit: int = 50,
    user_id: str = Depends(get_current_user_id),
):
    # Merge old manager jobs + new pipeline jobs
    try:
        manager = get_ingestion_manager()
        old_jobs = manager.list_jobs(user_id=user_id, limit=limit)
    except Exception:
        old_jobs = []
    new_jobs = [j for j in _new_pipeline_jobs.values() if j.user_id == user_id]
    all_jobs = list(old_jobs) + new_jobs
    return all_jobs[:limit]


@router.get("/jobs/{job_id}", response_model=IngestionJobResponse)
def get_ingestion_job(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
):
    # Check new pipeline jobs first
    if job_id in _new_pipeline_jobs:
        return _new_pipeline_jobs[job_id]
    # Fall back to old manager
    try:
        manager = get_ingestion_manager()
        return manager.get_job(user_id=user_id, job_id=job_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Ingestion job not found.")


@router.post("/jobs/{job_id}/cancel", response_model=IngestionJobResponse)
def cancel_ingestion_job(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
):
    if job_id in _new_pipeline_jobs:
        return _new_pipeline_jobs[job_id]  # Already completed, can't cancel
    try:
        manager = get_ingestion_manager()
        return manager.cancel_job(user_id=user_id, job_id=job_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Ingestion job not found.")


@router.get("/files", response_model=FileListResponse)
def list_files(
    index_id: int | None = None,
    include_chat_temp: bool = False,
    user_id: str = Depends(get_current_user_id),
):
    context = get_context()
    return list_indexed_files(
        context=context,
        user_id=user_id,
        index_id=index_id,
        include_chat_temp=include_chat_temp,
    )


@router.post("/files/delete", response_model=BulkDeleteFilesResponse)
def delete_files(
    payload: BulkDeleteFilesRequest,
    user: User = Depends(require_org_admin),
):
    user_id = user.id
    context = get_context()
    return delete_indexed_files(
        context=context,
        user_id=user_id,
        index_id=payload.index_id,
        file_ids=payload.file_ids,
    )


@router.post("/urls/delete", response_model=BulkDeleteUrlsResponse)
def delete_urls(
    payload: BulkDeleteUrlsRequest,
    user: User = Depends(require_org_admin),
):
    user_id = user.id
    context = get_context()
    return delete_indexed_urls(
        context=context,
        user_id=user_id,
        index_id=payload.index_id,
        urls=payload.urls,
    )


@router.get("/groups", response_model=FileGroupListResponse)
def list_groups(
    index_id: int | None = None,
    user_id: str = Depends(get_current_user_id),
):
    context = get_context()
    try:
        return list_file_groups(context=context, user_id=user_id, index_id=index_id)
    except HTTPException:
        # Index not found — return empty groups list instead of 404
        return FileGroupListResponse(index_id=index_id or 0, groups=[])


@router.post("/groups", response_model=MoveFilesToGroupResponse)
def create_group(
    payload: CreateFileGroupRequest,
    user: User = Depends(require_org_admin),
):
    user_id = user.id
    context = get_context()
    return create_file_group(
        context=context,
        user_id=user_id,
        index_id=payload.index_id,
        name=payload.name,
        file_ids=payload.file_ids,
    )


@router.put("/groups", response_model=MoveFilesToGroupResponse)
def create_group_put(
    payload: CreateFileGroupRequest,
    user: User = Depends(require_org_admin),
):
    user_id = user.id
    context = get_context()
    return create_file_group(
        context=context,
        user_id=user_id,
        index_id=payload.index_id,
        name=payload.name,
        file_ids=payload.file_ids,
    )


@router.get("/groups/create", response_model=MoveFilesToGroupResponse)
def create_group_compat(
    name: str = Query(..., min_length=1),
    index_id: int | None = None,
    file_ids: str | None = None,
    user: User = Depends(require_org_admin),
):
    user_id = user.id
    parsed_file_ids = []
    if file_ids:
        parsed_file_ids = [item.strip() for item in file_ids.split(",") if item and item.strip()]
    context = get_context()
    return create_file_group(
        context=context,
        user_id=user_id,
        index_id=index_id,
        name=name,
        file_ids=parsed_file_ids,
    )


@router.patch("/groups/{group_id}", response_model=FileGroupResponse)
def rename_group(
    group_id: str,
    payload: RenameFileGroupRequest,
    user: User = Depends(require_org_admin),
):
    user_id = user.id
    context = get_context()
    return rename_file_group(
        context=context,
        user_id=user_id,
        index_id=payload.index_id,
        group_id=group_id,
        name=payload.name,
    )


@router.delete("/groups/{group_id}", response_model=DeleteFileGroupResponse)
def remove_group(
    group_id: str,
    index_id: int | None = None,
    user: User = Depends(require_org_admin),
):
    user_id = user.id
    context = get_context()
    return delete_file_group(
        context=context,
        user_id=user_id,
        index_id=index_id,
        group_id=group_id,
    )


@router.post("/groups/move", response_model=MoveFilesToGroupResponse)
def move_files(
    payload: MoveFilesToGroupRequest,
    user: User = Depends(require_org_admin),
):
    user_id = user.id
    context = get_context()
    return move_files_to_group(
        context=context,
        user_id=user_id,
        index_id=payload.index_id,
        file_ids=payload.file_ids,
        group_id=payload.group_id,
        group_name=payload.group_name,
        mode=payload.mode,
    )


@router.put("/groups/move", response_model=MoveFilesToGroupResponse)
def move_files_put(
    payload: MoveFilesToGroupRequest,
    user: User = Depends(require_org_admin),
):
    user_id = user.id
    context = get_context()
    return move_files_to_group(
        context=context,
        user_id=user_id,
        index_id=payload.index_id,
        file_ids=payload.file_ids,
        group_id=payload.group_id,
        group_name=payload.group_name,
        mode=payload.mode,
    )


@router.get("/files/{file_id}/raw")
def get_file_raw(
    file_id: str,
    index_id: int | None = None,
    download: bool = False,
    user_id: str = Depends(get_current_user_id),
):
    context = get_context()
    try:
        file_path, file_name = resolve_indexed_file_path(
            context=context,
            user_id=user_id,
            file_id=file_id,
            index_id=index_id,
        )
    except HTTPException as exc:
        if index_id is None or exc.status_code != 404:
            raise
        file_path, file_name = resolve_indexed_file_path(
            context=context,
            user_id=user_id,
            file_id=file_id,
            index_id=None,
        )
    media_type = guess_type(file_name)[0] or "application/octet-stream"
    disposition_type = "attachment" if download else "inline"

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=file_name,
        content_disposition_type=disposition_type,
    )


@router.post("/files/{file_id}/highlight-target")
async def get_file_highlight_target(
    file_id: str,
    response: Response,
    payload: dict[str, object] = Body(default_factory=dict),
    user_id: str = Depends(get_current_user_id),
):
    trace = begin_trace(
        kind="highlight",
        user_id=user_id,
        metadata={
            "file_id": file_id,
            "page": payload.get("page"),
        },
    )
    response.headers["X-Maia-Trace-Id"] = trace.trace_id
    context = get_context()
    page_raw = payload.get("page")
    page: int | None
    if isinstance(page_raw, int):
        page = page_raw
    else:
        try:
            page = int(str(page_raw).strip()) if str(page_raw or "").strip() else None
        except Exception:
            page = None
    text = str(payload.get("text") or "").strip()
    claim_text = str(payload.get("claim_text") or "").strip()
    chunk_id = str(payload.get("chunk_id") or payload.get("unit_id") or "")
    index_id_value = payload.get("index_id")
    index_id = index_id_value if isinstance(index_id_value, int) else None
    bridge_result: dict[str, object] | None = None
    try:
        record_trace_event(
            "highlight.requested",
            {
                "file_id": file_id,
                "page": page,
                "text_length": len(text),
                "claim_text_length": len(claim_text),
                "index_id": index_id,
            },
        )
        if _USE_NEW_RAG:
            try:
                bridge_chunk_id = chunk_id or str(payload.get("index_id") or "")
                bridge_result = await get_highlight_target_bridge(file_id, bridge_chunk_id, page)
                bridge_result["file_id"] = file_id
                if bridge_result.get("highlight_boxes"):
                    return bridge_result
            except Exception as exc:
                logger.warning("New highlight bridge failed, falling back: %s", exc)
        # Fall through to old code
        file_path: Path | None = None
        try:
            file_path, _ = resolve_indexed_file_path(
                context=context,
                user_id=user_id,
                file_id=file_id,
                index_id=index_id,
            )
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            if index_id is not None:
                try:
                    file_path, _ = resolve_indexed_file_path(
                        context=context,
                        user_id=user_id,
                        file_id=file_id,
                        index_id=None,
                    )
                except HTTPException as fallback_exc:
                    if fallback_exc.status_code != 404:
                        raise
            if file_path is None:
                rag_path = resolve_registered_source_path(
                    source_id=file_id,
                    owner_id=user_id,
                    index_id=index_id,
                )
                if rag_path:
                    file_path = rag_path[0]
            if file_path is None and bridge_result is not None:
                return bridge_result
            if file_path is None:
                raise
        result = await run_in_threadpool(
            locate_pdf_highlight_target,
            file_path=file_path,
            page=page or 1,
            text=text,
            claim_text=claim_text,
        )
        result["file_id"] = file_id
        if bridge_result is not None and not result.get("highlight_boxes"):
            return bridge_result
        record_trace_event(
            "highlight.completed",
            {
                "file_id": file_id,
                "page": result.get("page"),
                "box_count": len(list(result.get("highlight_boxes") or [])),
                "unit_count": len(list(result.get("evidence_units") or [])),
            },
        )
        return result
    except HTTPException:
        record_trace_event("highlight.http_error", {"file_id": file_id})
        raise
    except Exception as exc:
        record_trace_event("highlight.exception", {"file_id": file_id, "error": str(exc)})
        raise
    finally:
        end_trace(trace)
