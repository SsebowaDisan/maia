"""RAG Pipeline Phase 1: Upload — create SourceRecord from file, URL, or chat attachment."""

from __future__ import annotations

import mimetypes
import os
import uuid
from datetime import datetime, timezone

from api.services.rag.types import (
    IngestionStatus,
    SourceRecord,
    SourceType,
)

# ── Extension to SourceType mapping ─────────────────────────────────────────

_EXT_MAP: dict[str, SourceType] = {
    ".pdf": SourceType.PDF,
    ".docx": SourceType.DOCX,
    ".doc": SourceType.DOCX,
    ".xlsx": SourceType.XLSX,
    ".xls": SourceType.XLSX,
    ".pptx": SourceType.PPTX,
    ".ppt": SourceType.PPTX,
    ".txt": SourceType.TXT,
    ".md": SourceType.TXT,
    ".csv": SourceType.TXT,
    ".tsv": SourceType.TXT,
    ".json": SourceType.TXT,
    ".png": SourceType.IMAGE,
    ".jpg": SourceType.IMAGE,
    ".jpeg": SourceType.IMAGE,
    ".gif": SourceType.IMAGE,
    ".bmp": SourceType.IMAGE,
    ".tiff": SourceType.IMAGE,
    ".tif": SourceType.IMAGE,
    ".webp": SourceType.IMAGE,
    ".svg": SourceType.IMAGE,
}


def _detect_source_type(filename: str) -> SourceType:
    """Detect SourceType from filename extension."""
    ext = os.path.splitext(filename)[1].lower()
    return _EXT_MAP.get(ext, SourceType.UNKNOWN)


def _detect_mime(filename: str) -> str:
    """Best-effort MIME type from filename."""
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Public API ──────────────────────────────────────────────────────────────


async def upload_file(
    file_path: str,
    group_id: str = "",
    owner_id: str = "",
    metadata: dict | None = None,
) -> SourceRecord:
    """Upload a local file into the RAG pipeline.

    Reads file bytes, creates a SourceRecord with status UPLOADED.
    Does NOT set rag_ready or citation_ready.
    """
    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)

    record = SourceRecord(
        id=str(uuid.uuid4()),
        filename=filename,
        source_type=_detect_source_type(filename),
        file_size=file_size,
        mime_type=_detect_mime(filename),
        group_id=group_id,
        owner_id=owner_id,
        upload_url=file_path,
        status=IngestionStatus.UPLOADED,
        metadata=metadata or {},
        created_at=_now_iso(),
        updated_at=_now_iso(),
        rag_ready=False,
        citation_ready=False,
    )
    return record


async def upload_url(
    url: str,
    group_id: str = "",
    owner_id: str = "",
    metadata: dict | None = None,
) -> SourceRecord:
    """Upload a URL into the RAG pipeline.

    Creates a SourceRecord pointing at the URL with status UPLOADED.
    Does NOT set rag_ready or citation_ready.
    """
    # Derive a human-readable filename from the URL
    from urllib.parse import urlparse

    parsed = urlparse(url)
    path_tail = parsed.path.rstrip("/").rsplit("/", 1)[-1] or parsed.netloc
    filename = path_tail if "." in path_tail else f"{path_tail}.html"

    record = SourceRecord(
        id=str(uuid.uuid4()),
        filename=filename,
        source_type=SourceType.URL,
        file_size=0,
        mime_type="text/html",
        group_id=group_id,
        owner_id=owner_id,
        upload_url=url,
        status=IngestionStatus.UPLOADED,
        metadata=metadata or {},
        created_at=_now_iso(),
        updated_at=_now_iso(),
        rag_ready=False,
        citation_ready=False,
    )
    return record


async def upload_from_chat(
    file_data: bytes,
    filename: str,
    chat_id: str,
    owner_id: str = "",
) -> SourceRecord:
    """Upload a file attachment from a chat message.

    Writes bytes to USER_TEMP_DIR so the file survives server restarts.
    Sets expires_at = now + USER_TEMP_TTL_DAYS so the cleanup job can
    auto-delete it. The raw bytes are also kept in metadata for the
    pipeline phases that need them; bridge.py strips file_data before
    persisting the registry so the JSON stays small.
    """
    from datetime import datetime, timezone, timedelta
    from api.services.upload.storage_config import USER_TEMP_DIR, USER_TEMP_TTL_DAYS

    source_id = str(uuid.uuid4())
    safe_filename = os.path.basename(filename) or "upload"

    # Write to disk: user_temp/{owner_id}/{source_id}_{filename}
    owner_dir = USER_TEMP_DIR / (owner_id or "anonymous")
    owner_dir.mkdir(parents=True, exist_ok=True)
    file_path = owner_dir / f"{source_id}_{safe_filename}"
    file_path.write_bytes(file_data)

    expires_at = (
        datetime.now(timezone.utc) + timedelta(days=USER_TEMP_TTL_DAYS)
    ).isoformat()

    record = SourceRecord(
        id=source_id,
        filename=filename,
        source_type=_detect_source_type(filename),
        file_size=len(file_data),
        mime_type=_detect_mime(filename),
        group_id="",
        owner_id=owner_id,
        upload_url=str(file_path),
        status=IngestionStatus.UPLOADED,
        metadata={
            "chat_id": chat_id,
            "file_data": file_data,  # kept in-memory for pipeline phases; stripped before registry save
        },
        created_at=_now_iso(),
        updated_at=_now_iso(),
        rag_ready=False,
        citation_ready=False,
        scope="user_temp",
        expires_at=expires_at,
    )
    return record
