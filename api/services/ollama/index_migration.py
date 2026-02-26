from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.context import ApiContext
from api.services.ingestion_service import IngestionJobManager
from ktem.db.engine import engine


def _is_http_url(value: str) -> bool:
    lowered = str(value or "").strip().lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def _normalize_upload_scope(note: dict[str, Any] | None) -> str:
    raw_scope = str((note or {}).get("upload_scope", "persistent") or "").strip().lower()
    return "chat_temp" if raw_scope == "chat_temp" else "persistent"


def _resolve_source_file_path(*, source_path: str, storage_root: Path) -> Path | None:
    raw_path = str(source_path or "").strip()
    if not raw_path:
        return None

    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = storage_root / candidate
    candidate = candidate.resolve()
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate


def collect_reindex_targets_for_index(
    *,
    index: Any,
    user_id: str,
) -> dict[str, Any]:
    Source = index._resources["Source"]
    storage_root = Path(index._resources["FileStoragePath"]).resolve()
    is_private = bool(index.config.get("private", False))

    with Session(engine) as session:
        statement = select(Source)
        if is_private:
            statement = statement.where(Source.user == user_id)
        rows = session.execute(statement).all()

    files: list[dict[str, Any]] = []
    urls: list[str] = []
    skipped = 0
    dedupe_paths: set[str] = set()
    dedupe_urls: set[str] = set()

    for row in rows:
        source = row[0]
        note = dict(source.note or {})
        if _normalize_upload_scope(note) == "chat_temp":
            continue

        source_name = str(source.name or "").strip()
        if not source_name:
            skipped += 1
            continue

        if _is_http_url(source_name):
            if source_name not in dedupe_urls:
                dedupe_urls.add(source_name)
                urls.append(source_name)
            continue

        resolved = _resolve_source_file_path(
            source_path=str(source.path or ""),
            storage_root=storage_root,
        )
        if resolved is None:
            skipped += 1
            continue

        path_key = str(resolved).casefold()
        if path_key in dedupe_paths:
            continue
        dedupe_paths.add(path_key)

        size = int(source.size or 0)
        if size <= 0:
            try:
                size = int(resolved.stat().st_size)
            except Exception:
                size = 0

        files.append(
            {
                "name": Path(source_name).name or resolved.name,
                "path": str(resolved),
                "size": size,
            }
        )

    return {
        "files": files,
        "urls": urls,
        "skipped_sources": skipped,
        "total_sources": len(rows),
    }


def apply_embedding_to_all_indices(
    *,
    context: ApiContext,
    user_id: str,
    embedding_name: str,
    ingestion_manager: IngestionJobManager,
) -> dict[str, Any]:
    indexes = list(context.app.index_manager.indices)
    index_summaries: list[dict[str, Any]] = []
    queued_jobs: list[dict[str, Any]] = []
    indexes_updated = 0

    for index in indexes:
        current_config = dict(index.config or {})
        previous_embedding = str(current_config.get("embedding") or "").strip()
        embedding_updated = previous_embedding != embedding_name
        if embedding_updated:
            next_config = dict(current_config)
            next_config["embedding"] = embedding_name
            context.app.index_manager.update_index(index.id, index.name, next_config)
            indexes_updated += 1

        targets = collect_reindex_targets_for_index(index=index, user_id=user_id)
        file_job_id: str | None = None
        url_job_id: str | None = None

        files_payload = list(targets["files"])
        if files_payload:
            file_job = ingestion_manager.create_file_job(
                user_id=user_id,
                index_id=index.id,
                reindex=True,
                files=files_payload,
            )
            file_job_id = str(file_job["id"])
            queued_jobs.append(
                {
                    "job_id": file_job_id,
                    "index_id": index.id,
                    "index_name": index.name,
                    "kind": "files",
                    "total_items": int(file_job.get("total_items", len(files_payload))),
                }
            )

        urls_payload = list(targets["urls"])
        if urls_payload:
            url_job = ingestion_manager.create_url_job(
                user_id=user_id,
                index_id=index.id,
                reindex=True,
                urls=urls_payload,
                web_crawl_depth=0,
                web_crawl_max_pages=0,
                web_crawl_same_domain_only=True,
                include_pdfs=True,
                include_images=True,
            )
            url_job_id = str(url_job["id"])
            queued_jobs.append(
                {
                    "job_id": url_job_id,
                    "index_id": index.id,
                    "index_name": index.name,
                    "kind": "urls",
                    "total_items": int(url_job.get("total_items", len(urls_payload))),
                }
            )

        index_summaries.append(
            {
                "index_id": index.id,
                "index_name": index.name,
                "embedding_updated": embedding_updated,
                "previous_embedding": previous_embedding or None,
                "embedding": embedding_name,
                "files_queued": len(files_payload),
                "urls_queued": len(urls_payload),
                "file_job_id": file_job_id,
                "url_job_id": url_job_id,
                "skipped_sources": int(targets["skipped_sources"]),
                "total_sources": int(targets["total_sources"]),
            }
        )

    return {
        "indexes_total": len(indexes),
        "indexes_updated": indexes_updated,
        "jobs_total": len(queued_jobs),
        "jobs": queued_jobs,
        "indexes": index_summaries,
    }
