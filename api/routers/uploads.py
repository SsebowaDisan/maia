from __future__ import annotations

import asyncio
import hashlib
import logging
import shutil
from mimetypes import guess_type
from pathlib import Path
from time import perf_counter
import uuid

import anyio
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from api.auth import get_current_user_id
from api.context import get_context
from api.schemas import (
    BulkDeleteFilesRequest,
    BulkDeleteFilesResponse,
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
    INGEST_KEEP_WORKDIR,
    INGEST_WORKDIR,
    UPLOAD_MAX_FILE_SIZE_BYTES,
    UPLOAD_MAX_FILES_PER_REQUEST,
    UPLOAD_STREAM_CHUNK_BYTES,
    UPLOAD_MAX_TOTAL_BYTES,
    UPLOAD_SAVE_CONCURRENCY,
    UPLOAD_USE_UNIFIED_PERSIST,
    get_ingestion_manager,
)
from api.services.settings_service import load_user_settings
from api.services.upload_service import (
    create_file_group,
    delete_file_group,
    delete_indexed_files,
    index_files,
    index_urls,
    list_file_groups,
    list_indexed_files,
    move_files_to_group,
    rename_file_group,
    resolve_indexed_file_path,
)

router = APIRouter(prefix="/api/uploads", tags=["uploads"])
logger = logging.getLogger(__name__)


def _unique_target_path(directory: Path, original_name: str) -> Path:
    clean_name = Path(original_name or "upload.bin").name
    candidate = directory / clean_name
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    for attempt in range(1, 10000):
        next_candidate = directory / f"{stem}-{attempt}{suffix}"
        if not next_candidate.exists():
            return next_candidate
    return directory / f"{stem}-{uuid.uuid4().hex}{suffix}"


def _raise_file_too_large(*, file_name: str, file_size: int) -> None:
    raise HTTPException(
        status_code=413,
        detail=(
            f'File "{file_name}" exceeds max size '
            f"({_bytes_to_human(file_size)} > "
            f"{_bytes_to_human(UPLOAD_MAX_FILE_SIZE_BYTES)})."
        ),
    )


async def _store_upload_file(upload: UploadFile, directory: Path) -> dict[str, object]:
    target = _unique_target_path(directory, upload.filename or "upload.bin")
    file_name = Path(upload.filename or target.name).name
    total_size = 0
    digest = hashlib.sha256()
    try:
        async with await anyio.open_file(target, "wb") as handle:
            while True:
                chunk = await upload.read(UPLOAD_STREAM_CHUNK_BYTES)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > UPLOAD_MAX_FILE_SIZE_BYTES:
                    _raise_file_too_large(file_name=file_name, file_size=total_size)
                await handle.write(chunk)
                digest.update(chunk)
    except Exception:
        try:
            target.unlink(missing_ok=True)
        except Exception:
            pass
        raise
    finally:
        await upload.close()

    return {
        "name": file_name,
        "path": str(target.resolve()),
        "size": int(total_size),
        "checksum": digest.hexdigest(),
    }


def _bytes_to_human(value: int) -> str:
    size = float(max(0, int(value)))
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    unit_idx = 0
    while size >= 1024 and unit_idx < len(units) - 1:
        size /= 1024.0
        unit_idx += 1
    return f"{size:.1f} {units[unit_idx]}"


def _enforce_upload_limits(files: list[UploadFile], request: Request) -> None:
    if not files:
        raise HTTPException(status_code=400, detail="No files were provided.")

    if len(files) > UPLOAD_MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Too many files in one request ({len(files)}). "
                f"Max allowed is {UPLOAD_MAX_FILES_PER_REQUEST}."
            ),
        )

    raw_content_length = str((request.headers.get("content-length") if request else "") or "").strip()
    if raw_content_length:
        try:
            content_length = int(raw_content_length)
        except Exception:
            content_length = 0
        if content_length > UPLOAD_MAX_TOTAL_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    "Request payload is too large. "
                    f"Max total upload size is {_bytes_to_human(UPLOAD_MAX_TOTAL_BYTES)}."
                ),
            )


def _cleanup_persisted_uploads(saved_files: list[dict[str, object]]) -> None:
    if INGEST_KEEP_WORKDIR:
        return

    parent_dirs: set[Path] = set()
    for item in saved_files:
        raw_path = str((item or {}).get("path", "")).strip()
        if not raw_path:
            continue
        path_obj = Path(raw_path)
        try:
            if path_obj.exists() and path_obj.is_file():
                path_obj.unlink(missing_ok=True)
        except Exception:
            pass
        parent = path_obj.parent
        if str(parent).startswith(str(INGEST_WORKDIR)):
            parent_dirs.add(parent)

    for directory in parent_dirs:
        try:
            if directory.exists() and directory.is_dir():
                shutil.rmtree(directory, ignore_errors=True)
        except Exception:
            pass


async def _persist_uploaded_files(files: list[UploadFile]) -> list[dict[str, object]]:
    if not files:
        raise HTTPException(status_code=400, detail="No files were provided.")

    job_dir = INGEST_WORKDIR / "incoming" / uuid.uuid4().hex
    job_dir.mkdir(parents=True, exist_ok=True)

    semaphore = asyncio.Semaphore(UPLOAD_SAVE_CONCURRENCY)
    persisted: list[dict[str, object] | None] = [None] * len(files)

    async def _persist_one(position: int, upload: UploadFile) -> None:
        async with semaphore:
            persisted[position] = await _store_upload_file(upload, job_dir)

    tasks = [asyncio.create_task(_persist_one(idx, upload)) for idx, upload in enumerate(files)]
    try:
        await asyncio.gather(*tasks)
    except Exception:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        saved_so_far = [item for item in persisted if item is not None]
        _cleanup_persisted_uploads(saved_so_far)  # best-effort cleanup on partial failure
        raise

    saved = [item for item in persisted if item is not None]
    total_bytes = sum(int((item or {}).get("size") or 0) for item in saved)
    if total_bytes > UPLOAD_MAX_TOTAL_BYTES:
        _cleanup_persisted_uploads(saved)
        raise HTTPException(
            status_code=413,
            detail=(
                "Combined file size exceeds max upload size. "
                f"Max total is {_bytes_to_human(UPLOAD_MAX_TOTAL_BYTES)}."
            ),
        )
    return saved


async def _persist_uploaded_files_sequential(files: list[UploadFile]) -> list[dict[str, object]]:
    if not files:
        raise HTTPException(status_code=400, detail="No files were provided.")

    job_dir = INGEST_WORKDIR / "incoming" / uuid.uuid4().hex
    job_dir.mkdir(parents=True, exist_ok=True)
    persisted: list[dict[str, object]] = []
    for upload in files:
        persisted.append(await _store_upload_file(upload, job_dir))
    total_bytes = sum(int((item or {}).get("size") or 0) for item in persisted)
    if total_bytes > UPLOAD_MAX_TOTAL_BYTES:
        _cleanup_persisted_uploads(persisted)
        raise HTTPException(
            status_code=413,
            detail=(
                "Combined file size exceeds max upload size. "
                f"Max total is {_bytes_to_human(UPLOAD_MAX_TOTAL_BYTES)}."
            ),
        )
    return persisted


@router.post("/files", response_model=UploadResponse)
async def upload_files(
    request: Request,
    files: list[UploadFile] = File(default_factory=list),
    index_id: int | None = Form(default=None),
    reindex: bool = Form(default=True),
    scope: str = Form(default="persistent"),
    user_id: str = Depends(get_current_user_id),
):
    _enforce_upload_limits(files, request)
    context = get_context()
    settings = load_user_settings(context=context, user_id=user_id)
    started_at = perf_counter()
    persisted_files: list[dict[str, object]] = []

    try:
        if UPLOAD_USE_UNIFIED_PERSIST:
            persisted_files = await _persist_uploaded_files(files)
        else:
            persisted_files = await _persist_uploaded_files_sequential(files)

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
        response = await run_in_threadpool(
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
        return response
    finally:
        _cleanup_persisted_uploads(persisted_files)
        elapsed_ms = int((perf_counter() - started_at) * 1000)
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


@router.post("/files/jobs", response_model=IngestionJobResponse)
async def create_file_ingestion_job(
    request: Request,
    files: list[UploadFile] = File(default_factory=list),
    index_id: int | None = Form(default=None),
    reindex: bool = Form(default=True),
    group_id: str | None = Form(default=None),
    scope: str = Form(default="persistent"),
    user_id: str = Depends(get_current_user_id),
):
    _enforce_upload_limits(files, request)
    started_at = perf_counter()
    persisted = (
        await _persist_uploaded_files(files)
        if UPLOAD_USE_UNIFIED_PERSIST
        else await _persist_uploaded_files_sequential(files)
    )
    total_bytes = sum(int((item or {}).get("size") or 0) for item in persisted)
    manager = get_ingestion_manager()
    job = manager.create_file_job(
        user_id=user_id,
        index_id=index_id,
        reindex=reindex,
        files=persisted,
        group_id=group_id,
        scope=scope,
    )
    logger.info(
        "Queued file ingestion job",
        extra={
            "user_id": user_id,
            "index_id": index_id,
            "group_id": group_id,
            "scope": scope,
            "file_count": len(persisted),
            "persisted_bytes": total_bytes,
            "elapsed_ms": int((perf_counter() - started_at) * 1000),
        },
    )
    return job


@router.post("/urls", response_model=UploadResponse)
def upload_urls(
    payload: UploadUrlsRequest,
    user_id: str = Depends(get_current_user_id),
):
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
def create_url_ingestion_job(
    payload: UploadUrlsRequest,
    user_id: str = Depends(get_current_user_id),
):
    manager = get_ingestion_manager()
    return manager.create_url_job(
        user_id=user_id,
        index_id=payload.index_id,
        reindex=payload.reindex,
        urls=payload.urls,
        web_crawl_depth=payload.web_crawl_depth,
        web_crawl_max_pages=payload.web_crawl_max_pages,
        web_crawl_same_domain_only=payload.web_crawl_same_domain_only,
        include_pdfs=payload.include_pdfs,
        include_images=payload.include_images,
    )


@router.get("/jobs", response_model=list[IngestionJobResponse])
def list_ingestion_jobs(
    limit: int = 50,
    user_id: str = Depends(get_current_user_id),
):
    manager = get_ingestion_manager()
    return manager.list_jobs(user_id=user_id, limit=limit)


@router.get("/jobs/{job_id}", response_model=IngestionJobResponse)
def get_ingestion_job(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
):
    manager = get_ingestion_manager()
    return manager.get_job(user_id=user_id, job_id=job_id)


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
    user_id: str = Depends(get_current_user_id),
):
    context = get_context()
    return delete_indexed_files(
        context=context,
        user_id=user_id,
        index_id=payload.index_id,
        file_ids=payload.file_ids,
    )


@router.get("/groups", response_model=FileGroupListResponse)
def list_groups(
    index_id: int | None = None,
    user_id: str = Depends(get_current_user_id),
):
    context = get_context()
    return list_file_groups(context=context, user_id=user_id, index_id=index_id)


@router.post("/groups", response_model=MoveFilesToGroupResponse)
def create_group(
    payload: CreateFileGroupRequest,
    user_id: str = Depends(get_current_user_id),
):
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
    user_id: str = Depends(get_current_user_id),
):
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
    user_id: str = Depends(get_current_user_id),
):
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
    user_id: str = Depends(get_current_user_id),
):
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
    user_id: str = Depends(get_current_user_id),
):
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
    user_id: str = Depends(get_current_user_id),
):
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
    user_id: str = Depends(get_current_user_id),
):
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
    file_path, file_name = resolve_indexed_file_path(
        context=context,
        user_id=user_id,
        file_id=file_id,
        index_id=index_id,
    )
    media_type = guess_type(file_name)[0] or "application/octet-stream"
    disposition_type = "attachment" if download else "inline"

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=file_name,
        content_disposition_type=disposition_type,
    )
