# Slice Execution Tracker

Use this file as the live tracker for the active slice only.

## Status Legend
- `todo` not started
- `in_progress` currently active
- `done` complete and validated
- `blocked` needs decision or prerequisite

## Active Slice
- Name: `React UI Unification (Gradio Sunset Program)`
- Status: `in_progress`

## Checklist
- [x] roadmap section added with final phase = full Gradio deletion (`done`)
- [x] migration inventory for dual UI stack entrypoints captured (`done`)
- [x] React-first local dev scripts added (`done`)
- [x] README updated to make React UI the primary local workflow (`done`)
- [x] frontend env template for API base URL and user identity added (`done`)
- [x] deployment/runtime cutover implemented (`done`)
- [x] Gradio runtime entrypoints deleted (`done`)
- [x] CI guard added to block legacy Gradio entrypoint reintroduction (`done`)
- [x] remaining docs/CI references to legacy runtime cleaned up (`done`)
- [ ] React UI auth/session error states (401/403) surfaced in UX (`todo`)

## Verification Evidence
- Commands run:
- `rg -n "python app.py|sso_app|sso_app_demo|localhost:7860|GRADIO_SERVER_PORT" README.md launch.sh fly.toml scripts docs`
- `rg -n "app.py|sso_app.py|sso_app_demo.py" .github/workflows/unit-test.yaml`
- `rg -n "port: 5173|proxy|/api" frontend/user_interface/vite.config.ts frontend/user_interface/package.json`
- `rg -n "createRoot|App" frontend/user_interface/src/main.tsx frontend/user_interface/src/app/App.tsx frontend/user_interface/src/app/appShell/app.tsx`
- `.venv311\Scripts\python.exe -m pytest -q api/tests/test_auth_identity.py`
- `npm run build` (from `frontend/user_interface`)
- `Invoke-WebRequest http://127.0.0.1:8000/api/health`
- Test output summary:
- Targeted auth identity suite passed (`4 passed`).
- Frontend production build passed.
- API health endpoint responded with `{"status":"ok"}`.
- LOC gate:
- N/A for this slice.

## Handoff Notes
- Completed in this step:
- Implemented React-first startup scripts and docs.
- Cut runtime/deploy defaults to FastAPI + React (`launch.sh`, `fly.toml`, Docker frontend build stage).
- Added explicit user identity propagation from React client to API plus strict-mode backend guard.
- Deleted legacy Gradio runtime entrypoints (`app.py`, `sso_app.py`, `sso_app_demo.py`).
- Added CI guard to fail if legacy Gradio runtime entrypoints are reintroduced.
- Overall status:
- React unification is mostly complete; remaining work is documentation/CI hardening for full legacy reference cleanup.
