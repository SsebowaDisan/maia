# Maia Incremental PDF Knowledge Base Roadmap

This roadmap implements a production-style, incremental knowledge base where users can upload PDFs over time (including very large volumes) and continuously chat against indexed content with citations.

Status legend:
- `[ ]` Not started
- `[~]` In progress
- `[x]` Completed

---

## Phase 1 - Async Ingestion Foundation (Backend)
Status: `[x]`

Goal:
- Decouple upload requests from indexing runtime using background jobs.
- Support large batches without blocking API request threads.

Scope:
- Add ingestion job model (persistent status/state).
- Add ingestion queue manager + background worker(s).
- Add APIs:
  - Create file ingestion job.
  - Create URL ingestion job.
  - Get ingestion job by id.
  - List ingestion jobs.
- Persist uploaded files in a job work directory until processed.
- Keep existing sync upload endpoints for backward compatibility.

Acceptance criteria:
- File/URL ingestion job creation returns quickly with `job_id`.
- Job status transitions: `queued -> running -> completed/failed`.
- Job result includes per-item success/failure and produced file IDs.
- Jobs survive API route completion (not tied to request lifecycle).

---

## Phase 2 - Upload UX at Scale (Frontend Integration)
Status: `[x]`

Goal:
- Make Files workspace usable for large, step-by-step indexing.

Scope:
- Submit uploads/URLs as ingestion jobs from Files view.
- Show active/recent ingestion jobs with live polling.
- Show progress summary (queued/running/completed/failed item counts).
- Show failure details and allow retry by re-submit.
- Keep chat-bar quick upload behavior for immediate single-turn usage.

Acceptance criteria:
- User can upload large batches without page freeze.
- User sees progress updates without manual refresh.
- Completed jobs are visible with indexed counts and errors.

---

## Phase 3 - Corpus-Scale Retrieval and Answer Quality
Status: `[x]`

Goal:
- Ensure chat quality when corpus grows to thousands of PDFs.

Scope:
- Improve fast-path retrieval diversity across documents.
- Add limits per-source to avoid one document dominating context.
- Add retrieval/response config knobs for large corpora.
- Preserve and strengthen citation fidelity.

Acceptance criteria:
- Queries can pull evidence from multiple relevant PDFs.
- Responses are grounded and cite used evidence.
- Latency remains bounded with configurable limits.

---

## Phase 4 - End-to-End Hardening and Operations
Status: `[x]`

Goal:
- Make the workflow operationally reliable.

Scope:
- Add environment variables for ingestion worker behavior.
- Add operational docs for large-batch indexing and monitoring.
- Run end-to-end verification for:
  - upload -> job processing -> indexed files -> chat answer with citations

Acceptance criteria:
- Documented startup/runtime behavior.
- Verified end-to-end flow works with incremental uploads.

---

## Execution Rule

Work proceeds strictly phase-by-phase. A phase is marked completed only after its acceptance criteria are met in code and verified.

## Verification Summary

- Backend compile: `python -m compileall api`
- Frontend build: `npm run build` in `frontend/user_interface`
- Runtime smoke checks (via `.venv311` + `TestClient`):
  - `POST /api/uploads/files/jobs` -> `queued/running/completed`
  - `POST /api/uploads/urls/jobs` -> `queued/running/completed`
  - `GET /api/uploads/jobs` and `GET /api/uploads/jobs/{job_id}`
  - Existing sync upload path `POST /api/uploads/files` remains functional
