from __future__ import annotations

from .app import get_ingestion_manager
from .config import (
    INGEST_FILE_BATCH_SIZE,
    INGEST_KEEP_WORKDIR,
    INGEST_URL_BATCH_SIZE,
    INGEST_WORKDIR,
    INGEST_WORKERS,
    JOB_STATUS_CANCELED,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    TERMINAL_JOB_STATUSES,
)
from .manager import IngestionJobManager
from .models import IngestionJob
from .serialization import as_json_safe, job_to_payload

__all__ = [
    "JOB_STATUS_QUEUED",
    "JOB_STATUS_RUNNING",
    "JOB_STATUS_COMPLETED",
    "JOB_STATUS_FAILED",
    "JOB_STATUS_CANCELED",
    "TERMINAL_JOB_STATUSES",
    "INGEST_WORKERS",
    "INGEST_FILE_BATCH_SIZE",
    "INGEST_URL_BATCH_SIZE",
    "INGEST_WORKDIR",
    "INGEST_KEEP_WORKDIR",
    "IngestionJob",
    "IngestionJobManager",
    "as_json_safe",
    "job_to_payload",
    "get_ingestion_manager",
]
