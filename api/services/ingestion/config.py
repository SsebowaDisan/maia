from __future__ import annotations

from pathlib import Path

from decouple import config

JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_FAILED = "failed"
JOB_STATUS_CANCELED = "canceled"
TERMINAL_JOB_STATUSES = {
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_CANCELED,
}

INGEST_WORKERS = max(1, int(config("MAIA_INGEST_WORKERS", default=1, cast=int)))
INGEST_FILE_BATCH_SIZE = max(
    1, int(config("MAIA_INGEST_FILE_BATCH_SIZE", default=25, cast=int))
)
INGEST_URL_BATCH_SIZE = max(
    1, int(config("MAIA_INGEST_URL_BATCH_SIZE", default=25, cast=int))
)
INGEST_WORKDIR = Path(
    str(config("MAIA_INGEST_WORKDIR", default=".maia_ingestion_jobs"))
).resolve()
INGEST_KEEP_WORKDIR = bool(config("MAIA_INGEST_KEEP_WORKDIR", default=False, cast=bool))

UPLOAD_USE_UNIFIED_PERSIST = bool(
    config("MAIA_UPLOAD_USE_UNIFIED_PERSIST", default=True, cast=bool)
)
UPLOAD_SAVE_CONCURRENCY = max(
    1, int(config("MAIA_UPLOAD_SAVE_CONCURRENCY", default=3, cast=int))
)
UPLOAD_MAX_FILES_PER_REQUEST = max(
    1, int(config("MAIA_UPLOAD_MAX_FILES_PER_REQUEST", default=60, cast=int))
)
UPLOAD_MAX_FILE_SIZE_BYTES = max(
    1,
    int(
        config(
            "MAIA_UPLOAD_MAX_FILE_SIZE_BYTES",
            default=1024 * 1024 * 512,  # 512 MiB
            cast=int,
        )
    ),
)
UPLOAD_MAX_TOTAL_BYTES = max(
    1,
    int(
        config(
            "MAIA_UPLOAD_MAX_TOTAL_BYTES",
            default=1024 * 1024 * 1024,  # 1 GiB
            cast=int,
        )
    ),
)
UPLOAD_STREAM_CHUNK_BYTES = max(
    64 * 1024,
    int(
        config(
            "MAIA_UPLOAD_STREAM_CHUNK_BYTES",
            default=1024 * 1024,  # 1 MiB
            cast=int,
        )
    ),
)

_raw_upload_reader_mode = str(
    config("MAIA_UPLOAD_INDEX_READER_MODE", default="default")
).strip()
UPLOAD_INDEX_READER_MODE = (
    _raw_upload_reader_mode
    if _raw_upload_reader_mode
    in {"default", "ocr", "adobe", "azure-di", "docling", "paddleocr"}
    else "default"
)
UPLOAD_INDEX_QUICK_MODE = bool(
    config("MAIA_UPLOAD_INDEX_QUICK_MODE", default=True, cast=bool)
)
