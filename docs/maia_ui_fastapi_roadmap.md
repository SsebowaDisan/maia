# Maia UI + FastAPI Migration Roadmap

## Goal
- Replace the Gradio UI with the provided `user_interface` frontend.
- Keep Maia/KTEM Python RAG logic unchanged.
- Expose backend APIs for chat, conversations, uploads, and settings.
- Deliver step-by-step execution with completion tracking.

## Status
- Current phase: `Completed`
- Overall progress: `8/8 phases complete`

## Phase Checklist
- [x] Phase 1: Create roadmap and execution checklist
- [x] Phase 2: Move UI source into repo at `frontend/user_interface`
- [x] Phase 3: Add FastAPI app skeleton and shared backend context
- [x] Phase 4: Implement conversations API
- [x] Phase 5: Implement settings API
- [x] Phase 6: Implement uploads API (files + URLs + crawl depth/pages)
- [x] Phase 7: Implement chat API (sync + streaming) using existing reasoning pipelines
- [x] Phase 8: Wire frontend to backend APIs and run smoke tests

## Detailed Tasks

### Phase 1: Roadmap
- [x] Create this markdown roadmap file.
- [x] Define explicit completion criteria per phase.

### Phase 2: Move UI
- [x] Move `C:\Users\SBW\Downloads\user_interface` to `frontend/user_interface`.
- [x] Confirm folder structure and entrypoint files are present.

### Phase 3: FastAPI Foundation
- [x] Add `api/` package with app entrypoint.
- [x] Initialize shared Maia/KTEM app context once (indices/settings/reasonings).
- [x] Add common API response helpers and health endpoint.

### Phase 4: Conversations API
- [x] `GET /api/conversations`
- [x] `POST /api/conversations`
- [x] `GET /api/conversations/{conversation_id}`
- [x] `PATCH /api/conversations/{conversation_id}`
- [x] `DELETE /api/conversations/{conversation_id}`

### Phase 5: Settings API
- [x] `GET /api/settings`
- [x] `PATCH /api/settings`
- [x] Persist per-user settings in existing `Settings` table.

### Phase 6: Uploads API
- [x] `POST /api/uploads/files` (multipart)
- [x] `POST /api/uploads/urls`
- [x] `GET /api/uploads/files` list indexed files
- [x] Support crawl controls:
  - `web_crawl_depth` (`0` = unlimited)
  - `web_crawl_max_pages` (`0` = unlimited)
  - `web_crawl_same_domain_only`
- [x] Ensure PDF/image extraction path remains enabled via existing `WebReader`.

### Phase 7: Chat API
- [x] `POST /api/chat` (non-stream)
- [x] `POST /api/chat/stream` (SSE)
- [x] Reuse existing reasoning + retrieval pipelines (no RAG rewrite).
- [x] Persist chat outputs to existing `Conversation.data_source`.

### Phase 8: Frontend Wiring + Validation
- [x] Add frontend API client and env-based base URL.
- [x] Connect chat send/receive and conversation loading.
- [x] Connect quick upload to uploads API.
- [x] Run backend import/smoke checks.
- [x] Run frontend build/smoke checks.

## Completion Criteria
- Backend logic remains in `libs/maia` and `libs/ktem` (no architectural rewrite).
- FastAPI routes exist for chat/conversations/uploads/settings.
- URL ingestion supports deep crawling and unlimited mode via `0` controls.
- PDFs/images from URL crawling are included by existing loader pipeline.
- Frontend is placed under `frontend/user_interface` and wired to API.

## Execution Log
- 2026-02-23: Phase 1 completed (roadmap created).
- 2026-02-23: Phase 2 completed (`frontend/user_interface` created and verified).
- 2026-02-23: Phases 3-7 completed (FastAPI foundation + chat/conversations/uploads/settings APIs).
- 2026-02-23: Phase 8 completed (frontend wired, frontend build successful, API smoke checks executed).
