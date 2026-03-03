from __future__ import annotations

import shutil
from mimetypes import guess_type
import tempfile
from pathlib import Path
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
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
from api.services.ingestion_service import INGEST_WORKDIR, get_ingestion_manager
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


def _copy_upload_file(upload: UploadFile, target: Path) -> None:
    upload.file.seek(0)
    with target.open("wb") as handle:
        shutil.copyfileobj(upload.file, handle, length=8 * 1024 * 1024)


async def _store_upload_file(upload: UploadFile, directory: Path) -> Path:
    target = _unique_target_path(directory, upload.filename or "upload.bin")
    try:
        await run_in_threadpool(_copy_upload_file, upload, target)
    finally:
        await upload.close()
    return target


async def _persist_uploaded_files(files: list[UploadFile]) -> list[dict[str, object]]:
    if not files:
        raise HTTPException(status_code=400, detail="No files were provided.")

    job_dir = INGEST_WORKDIR / "incoming" / uuid.uuid4().hex
    job_dir.mkdir(parents=True, exist_ok=True)
    saved: list[dict[str, object]] = []
    for upload in files:
        target = await _store_upload_file(upload, job_dir)
        saved.append(
            {
                "name": Path(upload.filename or target.name).name,
                "path": str(target.resolve()),
                "size": int(target.stat().st_size),
            }
        )
    return saved


@router.post("/files", response_model=UploadResponse)
async def upload_files(
    files: list[UploadFile] = File(default_factory=list),
    index_id: int | None = Form(default=None),
    reindex: bool = Form(default=True),
    scope: str = Form(default="persistent"),
    user_id: str = Depends(get_current_user_id),
):
    context = get_context()
    settings = load_user_settings(context=context, user_id=user_id)

    with tempfile.TemporaryDirectory(prefix="maia_upload_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        file_paths: list[Path] = []
        for upload in files:
            target = await _store_upload_file(upload, tmp_path)
            file_paths.append(target)

        response = await run_in_threadpool(
            index_files,
            context=context,
            user_id=user_id,
            file_paths=file_paths,
            index_id=index_id,
            reindex=reindex,
            settings=settings,
            scope=scope,
        )

    return response


@router.post("/files/jobs", response_model=IngestionJobResponse)
async def create_file_ingestion_job(
    files: list[UploadFile] = File(default_factory=list),
    index_id: int | None = Form(default=None),
    reindex: bool = Form(default=True),
    user_id: str = Depends(get_current_user_id),
):
    persisted = await _persist_uploaded_files(files)
    manager = get_ingestion_manager()
    return manager.create_file_job(
        user_id=user_id,
        index_id=index_id,
        reindex=reindex,
        files=persisted,
    )


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
