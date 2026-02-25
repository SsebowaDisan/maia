# Maia Incremental Knowledge Base Operations

This document describes how to run Maia as an incremental PDF/URL knowledge base at scale.

## Overview

Maia now supports two ingestion paths:

1. `Synchronous upload` (existing)
- Endpoint: `POST /api/uploads/files`
- Best for quick chat-bar uploads and immediate usage.

2. `Asynchronous ingestion jobs` (new)
- Endpoints:
  - `POST /api/uploads/files/jobs`
  - `POST /api/uploads/urls/jobs`
  - `GET /api/uploads/jobs`
  - `GET /api/uploads/jobs/{job_id}`
- Best for large batches (thousands of files over time).

## Recommended Workflow for 10k+ PDFs

1. Upload in batches using job endpoints.
2. Poll job status until `completed`.
3. Continue uploading next batches incrementally.
4. Chat normally against indexed corpus.
5. Use citations to inspect evidence in the information panel.

## Job Status Lifecycle

- `queued`: accepted and waiting in worker queue.
- `running`: worker is indexing content.
- `completed`: indexing finished (check `success_count` / `failure_count`).
- `failed`: ingestion aborted due an error.
- `canceled`: reserved state for future cancel support.

## Key Environment Variables

```env
# Worker/process behavior
MAIA_INGEST_WORKERS=1
MAIA_INGEST_FILE_BATCH_SIZE=25
MAIA_INGEST_URL_BATCH_SIZE=25
MAIA_INGEST_WORKDIR=.maia_ingestion_jobs
MAIA_INGEST_KEEP_WORKDIR=false

# Fast QA retrieval tuning for larger corpora
MAIA_FAST_QA_SOURCE_SCAN=120
MAIA_FAST_QA_MAX_SOURCES=18
MAIA_FAST_QA_MAX_CHUNKS_PER_SOURCE=3
MAIA_FAST_QA_TEMPERATURE=0.2
```

## Scaling Notes

1. Increase `MAIA_INGEST_WORKERS` gradually (watch CPU/RAM/IO).
2. Keep batch sizes moderate to avoid long single-batch failures.
3. Use asynchronous job upload from Files workspace for large operations.
4. Keep chat-bar upload for small ad-hoc files.
5. If OCR-heavy PDFs are common, plan additional CPU time during ingestion windows.

## Frontend Behavior

- Files workspace now creates ingestion jobs and shows live job cards with progress.
- Active jobs are auto-polled; file count refreshes during processing.
- Chat-bar quick upload path remains available for immediate, per-turn attachments.
