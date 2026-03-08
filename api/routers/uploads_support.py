from __future__ import annotations

import asyncio
import hashlib
import shutil
import uuid
from pathlib import Path

import anyio
from fastapi import HTTPException, Request, UploadFile

from api.services.ingestion_service import (
    INGEST_KEEP_WORKDIR,
    INGEST_WORKDIR,
    UPLOAD_MAX_FILE_SIZE_BYTES,
    UPLOAD_MAX_FILES_PER_REQUEST,
    UPLOAD_MAX_TOTAL_BYTES,
    UPLOAD_SAVE_CONCURRENCY,
    UPLOAD_STREAM_CHUNK_BYTES,
)


def unique_target_path(directory: Path, original_name: str) -> Path:
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


def bytes_to_human(value: int) -> str:
    size = float(max(0, int(value)))
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    unit_idx = 0
    while size >= 1024 and unit_idx < len(units) - 1:
        size /= 1024.0
        unit_idx += 1
    return f"{size:.1f} {units[unit_idx]}"


def raise_file_too_large(*, file_name: str, file_size: int) -> None:
    raise HTTPException(
        status_code=413,
        detail=(
            f'File "{file_name}" exceeds max size '
            f"({bytes_to_human(file_size)} > "
            f"{bytes_to_human(UPLOAD_MAX_FILE_SIZE_BYTES)})."
        ),
    )


async def store_upload_file(upload: UploadFile, directory: Path) -> dict[str, object]:
    target = unique_target_path(directory, upload.filename or "upload.bin")
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
                    raise_file_too_large(file_name=file_name, file_size=total_size)
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


def enforce_upload_limits(files: list[UploadFile], request: Request) -> None:
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
                    f"Max total upload size is {bytes_to_human(UPLOAD_MAX_TOTAL_BYTES)}."
                ),
            )


def cleanup_persisted_uploads(saved_files: list[dict[str, object]]) -> None:
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


async def persist_uploaded_files(files: list[UploadFile]) -> list[dict[str, object]]:
    if not files:
        raise HTTPException(status_code=400, detail="No files were provided.")

    job_dir = INGEST_WORKDIR / "incoming" / uuid.uuid4().hex
    job_dir.mkdir(parents=True, exist_ok=True)

    semaphore = asyncio.Semaphore(UPLOAD_SAVE_CONCURRENCY)
    persisted: list[dict[str, object] | None] = [None] * len(files)

    async def _persist_one(position: int, upload: UploadFile) -> None:
        async with semaphore:
            persisted[position] = await store_upload_file(upload, job_dir)

    tasks = [asyncio.create_task(_persist_one(idx, upload)) for idx, upload in enumerate(files)]
    try:
        await asyncio.gather(*tasks)
    except Exception:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        saved_so_far = [item for item in persisted if item is not None]
        cleanup_persisted_uploads(saved_so_far)
        raise

    saved = [item for item in persisted if item is not None]
    total_bytes = sum(int((item or {}).get("size") or 0) for item in saved)
    if total_bytes > UPLOAD_MAX_TOTAL_BYTES:
        cleanup_persisted_uploads(saved)
        raise HTTPException(
            status_code=413,
            detail=(
                f"Total upload size exceeds limit ({bytes_to_human(total_bytes)} > "
                f"{bytes_to_human(UPLOAD_MAX_TOTAL_BYTES)})."
            ),
        )

    return saved
