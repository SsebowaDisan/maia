from __future__ import annotations

# Deprecated shim: moved to `api/services/ingestion/`.
from api.services.ingestion import (
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
    IngestionJob,
    IngestionJobManager,
    as_json_safe as _as_json_safe,
    get_ingestion_manager,
    job_to_payload as _job_to_payload,
)

_ingestion_manager = get_ingestion_manager()

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
    "_as_json_safe",
    "_job_to_payload",
    "_ingestion_manager",
    "get_ingestion_manager",
]
