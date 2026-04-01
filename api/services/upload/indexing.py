"""Stub — old indexing module replaced by api.services.rag.pipeline.

These functions are kept as thin shims so existing imports don't break.
They delegate to the new RAG pipeline where possible.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from api.schemas import FileListResponse, FileRecord
from api.services.rag.bridge import list_registered_sources, resolve_registered_source_path
from api.services.rag.types import IngestionStatus

logger = logging.getLogger(__name__)


def run_upload_startup_checks() -> list[str]:
    """Startup check — no longer needed (new pipeline has no global state to init).
    Returns an empty list of notices (caller iterates this).
    """
    logger.info("Upload startup checks: skipped (new RAG pipeline active)")
    return []


def index_files(*, context, user_id: str, files: list, index_id=None, reindex=True, scope="persistent", group_id=None, **kwargs) -> dict:
    """Stub — file indexing now handled by api.services.rag.pipeline.ingest_file."""
    logger.warning("index_files called on deprecated stub — use api.services.rag.pipeline.ingest_file")
    return {"indexed": 0, "errors": [], "message": "Deprecated — use new RAG pipeline"}


def index_urls(*, context, user_id: str, urls: list, index_id=None, reindex=True, scope="persistent", group_id=None, **kwargs) -> dict:
    """Stub — URL indexing now handled by api.services.rag.pipeline.ingest_url."""
    logger.warning("index_urls called on deprecated stub — use api.services.rag.pipeline.ingest_url")
    return {"indexed": 0, "errors": [], "message": "Deprecated — use new RAG pipeline"}


def list_indexed_files(*, context, user_id: str, include_chat_temp: bool = False, index_id=None, **kwargs):
    """List files from the active RAG source registry."""
    sources = list_registered_sources(
        owner_id=user_id,
        include_chat_temp=bool(include_chat_temp),
        index_id=index_id,
    )

    def _parse_created_at(raw_value: Any) -> datetime:
        if isinstance(raw_value, datetime):
            return raw_value
        raw_text = str(raw_value or "").strip()
        if raw_text:
            try:
                return datetime.fromisoformat(raw_text.replace("Z", "+00:00"))
            except Exception:
                pass
        return datetime.now(timezone.utc)

    files: list[FileRecord] = []
    for source in sources:
        metadata = source.metadata if isinstance(source.metadata, dict) else {}
        scope = str(metadata.get("scope") or "").strip().lower()
        if not scope:
            scope = "chat_temp" if metadata.get("chat_id") else "persistent"
        note: dict[str, Any] = {
            "source_type": source.source_type.value if source.source_type else "unknown",
            "group_id": str(source.group_id or ""),
        }
        # Preserve compact metadata used by the frontend file list columns.
        for key in (
            "tokens",
            "token",
            "n_tokens",
            "num_tokens",
            "token_count",
            "loader",
            "reader",
            "doc_loader",
            "processing_route",
            "upload_scope",
            "index_id",
        ):
            value = metadata.get(key)
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            note[key] = value
        raw_url = str(source.upload_url or "").strip()
        if raw_url.startswith(("http://", "https://")):
            note["url"] = raw_url
            note["source_url"] = raw_url

        status_text = source.status.value if isinstance(source.status, IngestionStatus) else str(source.status or "")
        if source.citation_ready:
            citation_status = "ready"
        elif source.rag_ready:
            citation_status = "preparing"
        else:
            citation_status = status_text or "pending"

        files.append(
            FileRecord(
                id=str(source.id or ""),
                name=str(source.filename or source.id or "Indexed file"),
                size=int(source.file_size or 0),
                scope=scope,
                rag_ready=bool(source.rag_ready),
                citation_ready=bool(source.citation_ready),
                citation_status=citation_status,
                note=note,
                date_created=_parse_created_at(source.created_at),
            )
        )

    files.sort(key=lambda row: row.date_created, reverse=True)
    return FileListResponse(index_id=index_id or 0, files=files)


def resolve_indexed_file_path(*, context, user_id: str, file_id: str, index_id=None, **kwargs) -> tuple:
    """Resolve stored file path for a source ID."""
    resolved = resolve_registered_source_path(
        source_id=file_id,
        owner_id=user_id,
        index_id=index_id,
    )
    if not resolved:
        raise HTTPException(status_code=404, detail="File not found.")
    file_path, file_name = resolved
    if not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="File not found.")
    return file_path, file_name
