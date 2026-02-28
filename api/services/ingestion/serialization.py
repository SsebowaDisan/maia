from __future__ import annotations

import json
from typing import Any

from .models import IngestionJob


def as_json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except Exception:
        return str(value)


def job_to_payload(job: IngestionJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "user_id": job.user_id,
        "kind": job.kind,
        "status": job.status,
        "index_id": job.index_id,
        "reindex": job.reindex,
        "total_items": int(job.total_items or 0),
        "processed_items": int(job.processed_items or 0),
        "success_count": int(job.success_count or 0),
        "failure_count": int(job.failure_count or 0),
        "items": list(job.items or []),
        "errors": list(job.errors or []),
        "file_ids": list(job.file_ids or []),
        "debug": list(job.debug or []),
        "message": str(job.message or ""),
        "date_created": job.date_created.isoformat() if job.date_created else None,
        "date_updated": job.date_updated.isoformat() if job.date_updated else None,
        "date_started": job.date_started.isoformat() if job.date_started else None,
        "date_finished": job.date_finished.isoformat() if job.date_finished else None,
    }
