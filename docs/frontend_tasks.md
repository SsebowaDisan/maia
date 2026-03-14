# Maia Frontend - Task Status
**Updated:** 2026-03-14
**Scope:** Former open frontend tasks from this file, now implementation status.

---

## Status Legend
- `done` - implemented in frontend and wired to client calls
- `backend-route-dependent` - frontend is wired, but runtime success depends on route availability

---

## Quick Reference

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| F-04 | Computer Use theatre integration | done | Prop threading, session fallback bootstrap, stop action, gate polling at 3s + new-gate toast |
| F-07 | Webhook Manager | backend-route-dependent | UI now calls list/register/delete webhook APIs and renders status badges |
| F-08 | Workflow Builder - save & run | backend-route-dependent | Save/update/run wiring is in place with streamed theatre updates |
| F-10 | Agent Feedback & Improvement | backend-route-dependent | Run feedback submission + suggestion fetch/apply flow wired |
| F-13 | Developer Portal | done | Mock data removed; uses listAgents/listAgentApiRuns + API key settings section |

---

## Implemented Frontend Changes

### F-04 - Computer Use theatre integration
- Added missing client APIs in `computerUse.ts`:
  - `listComputerUseSessions()`
  - `navigateComputerUseSession(sessionId, url)`
- Added Computer Use prop threading through:
  - `DesktopViewer` -> `AgentDesktopScene` -> `BrowserScene`
- Added fallback session bootstrap:
  - If a `computer_use` tool event is detected with no session id, frontend creates a session and starts streaming.
- Added stop control:
  - Browser scene now has a `Stop` action that calls `cancelComputerUseSession`.
- Gate polling and UX:
  - Pending gates now poll every 3 seconds.
  - Toast appears when a new pending gate appears.

### F-07 - Webhook Manager
- Replaced local mock state with API-backed load/register/delete flow.
- Added status badges: `active`, `inactive`, `error`.
- Added normalization logic for server payload variants (`event_types`, `event_types_json`).

### F-08 - Workflow Builder save/run
- Added workflow client calls and SSE run stream handling.
- Wired:
  - Save workflow (`create`/`update`)
  - Run workflow (`runWorkflow`)
  - Streamed step status/log updates into `MultiAgentTheatre`.

### F-10 - Agent Feedback & Self-Improvement
- Added feedback/improvement client calls.
- Run history now supports:
  - approve/reject feedback
  - correction text submission
- Improvement tab now:
  - fetches suggestion
  - displays current vs suggested prompt + reasoning
  - applies suggestion via `updateAgent`.

### F-13 - Developer Portal
- Removed `AGENT_OS_MARKETPLACE` mock usage.
- Uses real API data:
  - `listAgents()`
  - `listAgentApiRuns()`
- Added API key management section using settings API (`getSettings`, `patchSettings`).

---

## Validation
- Frontend production build passes:
  - `npm run build` in `frontend/user_interface`

