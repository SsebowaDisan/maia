# Maia Frontend Execution Roadmap (Wiring Phase)

Updated: 2026-03-14  
Source of truth: `docs/frontend_tasks.md`

## Principles
1. Frontend work only; backend is treated as available unless an endpoint is truly missing.
2. One phase completes before the next begins.
3. Every slice must be end-to-end wired (no mock fallback left in production paths).
4. No component should exceed 500 LOC.
5. Do not change theatre layout, structure, or design while implementing these tasks.
6. Move automatically from one completed slice to the next until phase completion.

## Status Legend
- `done` wired to real API and verified
- `in_progress` partially wired, not yet end-to-end
- `todo` not wired yet
- `blocked` waiting on missing backend contract

## Current Snapshot
- Current phase: `P1`
- Current slice: `F-09 Observability`
- Overall progress: `3/13 done` (strictly end-to-end)

## Area Status (from report)
| Area | Status |
|---|---|
| Agent Run SSE | done |
| Gate approvals (approve/reject actions) | done |
| Connector credentials/plugins CRUD | done |
| Agent CRUD | done |
| Computer Use / BrowserScene | todo |
| Marketplace (agents) | done |
| Marketplace (connectors) | in_progress |
| Webhooks UI | todo |
| Workflow Builder | todo |
| Observability | todo |
| Feedback / improvement | todo |
| Scheduled/event triggers UI | todo |
| Memory config UI | todo |
| Developer portal/docs deep content | todo |

---

## Phase P0 (Critical Wiring)
Goal: remove the highest-impact blockers first.

### Sidebar navigation extension
- status: `done`
- files:
  - `frontend/user_interface/src/app/components/chatSidebar/ProjectsPane.tsx`
  - `frontend/user_interface/src/app/components/ChatSidebar.tsx`
  - `frontend/user_interface/src/app/appShell/app.tsx`
- acceptance:
  - new entries (Marketplace, Workflows, Operations) are rendered in the same section as Connectors/Agents
  - entries route through app shell navigation without full-page reload
  - completed 2026-03-14

### F-01 Agent CRUD
- status: `done`
- files:
  - `frontend/user_interface/src/app/pages/AgentBuilderPage.tsx`
  - `frontend/user_interface/src/app/pages/AgentDetailPage.tsx`
  - `frontend/user_interface/src/api/client/agent.ts`
- required APIs:
  - `POST /api/agents`
  - `GET /api/agents`
  - `GET /api/agents/{id}`
  - `PUT /api/agents/{id}`
  - `DELETE /api/agents/{id}`
- acceptance:
  - create/edit/delete agent works from UI
  - detail page loads real definition/version data
  - no mock agent list in CRUD flows
  - completed 2026-03-14

### F-04 Computer Use / BrowserScene
- status: `todo`
- files:
  - `frontend/user_interface/src/app/components/agentDesktopScene/BrowserScene.tsx`
  - `frontend/user_interface/src/app/components/agentDesktopScene/api_scene_state.ts`
  - `frontend/user_interface/src/api/client/computerUse.ts` (new)
- required APIs:
  - `POST /api/computer-use/sessions`
  - `GET /api/computer-use/sessions`
  - `GET /api/computer-use/sessions/{id}/stream` (SSE)
  - `DELETE /api/computer-use/sessions/{id}`
- acceptance:
  - BrowserScene updates live from screenshot stream
  - session status + step count visible
  - cancel action works
  - theatre auto-opens BrowserScene when computer-use tool appears

---

## Phase P1 (Core Product Loop)
Goal: complete daily operational loop for agents.

### F-02 Agent Run History
- status: `todo`
- files:
  - `frontend/user_interface/src/app/components/agents/AgentRunHistory.tsx`
  - `frontend/user_interface/src/app/pages/AgentDetailPage.tsx`
  - `frontend/user_interface/src/api/client/agent.ts`
- required APIs:
  - `GET /api/agents/{agentId}/runs`
  - `GET /api/agents/runs/{runId}`
  - `POST /api/agents/{agentId}/run`
- acceptance:
  - run list loads from API with real statuses
  - run detail opens replay/theatre
  - "Run now" launches real run stream

### F-05 Marketplace (Agents)
- status: `done`
- files:
  - `frontend/user_interface/src/app/pages/MarketplacePage.tsx`
  - `frontend/user_interface/src/app/pages/MarketplaceAgentDetailPage.tsx`
  - `frontend/user_interface/src/app/components/marketplace/AgentInstallModal.tsx`
  - `frontend/user_interface/src/api/client/marketplace.ts` (new)
- required APIs:
  - `GET /api/marketplace/agents`
  - `GET /api/marketplace/agents/{agentId}`
  - `POST /api/marketplace/install`
- acceptance:
  - marketplace list/detail from API (no `agentOsData.ts` mocks)
  - install flow handles `missing_connectors` path
  - completed 2026-03-14

### F-09 Observability
- status: `todo`
- files:
  - `frontend/user_interface/src/app/pages/OperationsDashboardPage.tsx`
  - `frontend/user_interface/src/app/components/observability/LiveRunMonitor.tsx`
  - `frontend/user_interface/src/app/components/observability/RunErrorLog.tsx`
  - `frontend/user_interface/src/app/components/workspace/BudgetSettings.tsx`
  - `frontend/user_interface/src/api/client/observability.ts` (new)
- required APIs:
  - `GET /api/observability/runs`
  - `GET /api/observability/runs/aggregate`
  - `GET /api/observability/cost`
  - `POST /api/observability/budget`
- acceptance:
  - dashboard metrics from API
  - live runs refresh every 5 seconds (or SSE)
  - error log and budget settings fully wired

---

## Phase P2 (Workflow + HITL Quality)
Goal: complete orchestration and approval ergonomics.

### F-03 Gate Pending List
- status: `in_progress`
- files:
  - `frontend/user_interface/src/app/components/chatMain/GateApprovalCard.tsx`
  - `frontend/user_interface/src/app/components/chatMain/app.tsx`
  - `frontend/user_interface/src/api/client/agent.ts`
- required API:
  - `GET /api/agents/runs/{runId}/gates`
- acceptance:
  - pending gates surface automatically via polling or SSE
  - toast displayed when a new gate becomes pending
  - no manual refresh needed

### F-08 Workflow Builder
- status: `todo`
- files:
  - `frontend/user_interface/src/app/pages/WorkflowBuilderPage.tsx`
  - `frontend/user_interface/src/api/client/agent.ts`
- required APIs:
  - `POST /api/agents/workflows`
  - `GET /api/agents/workflows`
  - `POST /api/agents/workflows/{id}/run` (SSE)
- acceptance:
  - save/load workflows from backend
  - run workflow streams to theatre
  - step agent picker driven by real `listAgents()`

### F-11 Scheduled & Event Triggers UI
- status: `todo`
- files:
  - `frontend/user_interface/src/app/components/agentBuilder/TriggerConfigEditor.tsx` (new)
  - `frontend/user_interface/src/app/pages/AgentBuilderPage.tsx`
- acceptance:
  - conversational/scheduled/on_event trigger editors present
  - cron preview readable (via `cronstrue`)
  - connector/event binding serialized correctly into agent schema

---

## Phase P3 (Ecosystem Completion)
Goal: finish connector/event ecosystem and quality loops.

### F-06 Marketplace (Connectors)
- status: `in_progress`
- files:
  - `frontend/user_interface/src/app/pages/ConnectorMarketplacePage.tsx`
  - `frontend/user_interface/src/api/client/marketplace.ts` (new)
- required APIs:
  - `GET /api/marketplace/connectors`
  - `POST /api/marketplace/connectors/{id}/install`
- acceptance:
  - connector cards + filters use live connector catalog API
  - install redirects to connector credential setup
  - remaining: move from `/api/connectors` fallback to `/api/marketplace/connectors` once backend route exists

### F-07 Webhooks UI
- status: `todo`
- files:
  - `frontend/user_interface/src/app/components/connectors/WebhookManager.tsx`
  - `frontend/user_interface/src/api/client/connectors.ts` (new or extend agent client)
- required APIs:
  - `GET /api/connectors/webhooks`
  - `POST /api/connectors/{id}/webhooks`
  - `DELETE /api/connectors/webhooks/{id}`
- acceptance:
  - list/register/delete fully wired
  - per-webhook status shown

### F-10 Agent Feedback & Improvement
- status: `todo`
- files:
  - `frontend/user_interface/src/app/components/agents/ImprovementSuggestion.tsx`
  - `frontend/user_interface/src/app/pages/AgentDetailPage.tsx`
  - `frontend/user_interface/src/api/client/agent.ts`
- required APIs:
  - `POST /api/agents/{id}/feedback`
  - `GET /api/agents/{id}/improvement`
  - `PUT /api/agents/{id}` (apply suggestion)
- acceptance:
  - feedback collection in run history
  - improvement suggestion loads from backend
  - apply updates system prompt successfully

### F-12 Memory Config UI
- status: `todo`
- files:
  - `frontend/user_interface/src/app/components/agentBuilder/MemoryConfigEditor.tsx` (new)
  - `frontend/user_interface/src/app/pages/AgentBuilderPage.tsx`
- acceptance:
  - working memory TTL, episodic controls, semantic controls available
  - state serializes into agent definition save payload

---

## Phase P4 (Developer Surfaces)
Goal: finish publisher/developer experience.

### F-13 Developer Portal
- status: `todo`
- files:
  - `frontend/user_interface/src/app/pages/DeveloperPortalPage.tsx`
  - `frontend/user_interface/src/app/pages/DeveloperDocsPage.tsx`
- acceptance:
  - portal has SDK/API key/webhook-signing sections
  - docs page includes production docs links or embedded content

---

## Client File Plan
1. Extend: `frontend/user_interface/src/api/client/agent.ts`
2. New: `frontend/user_interface/src/api/client/marketplace.ts`
3. New: `frontend/user_interface/src/api/client/observability.ts`
4. New: `frontend/user_interface/src/api/client/computerUse.ts`
5. Optional split: `frontend/user_interface/src/api/client/connectors.ts`

## Exit Criteria
1. No production page reads from `agentOsData.ts` for runtime data.
2. All F-01 to F-13 slices are `done`.
3. All route surfaces run against real backend APIs with error/loading states.
4. Build and tests pass after each phase, with no theatre layout/design regressions.
