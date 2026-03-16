# Maia Execution Roadmap

Updated: 2026-03-15

## Rules
1. Tasks move in strict sequence from highest priority to lowest.
2. No slice is considered complete until it is wired end-to-end.
3. Keep each slice small, testable, and production-safe.

---

## Phase Status Summary

| Phase | Description | Status |
|---|---|---|
| P1â€“P4 | Frontend critical/high/medium/hardening (F-01 â†’ F-20) | **done** |
| B1â€“B7 | Backend Agent OS (scheduler, workflow, chat, marketplace, auth, metering, budget) | **done** |
| P5 | Proactive Intelligence Engine | todo |
| P6 | Natural Language Workflow Builder | todo |
| P7 | Agent Memory Network | todo |
| P8 | Agent Simulation / Replay Mode | todo |
| P9 | Automated Business Reviews | todo |
| P10 | ROI / Savings Tracker | todo |

---

## Frontend Integration Slice (F-21 -> F-30)

**Goal**: close wiring gaps where feature components already exist in `src/app/components/...` but are not mounted in primary app surfaces.

**Verification outcome**: all items below are real integration work (not false alarms). Most components exist; wiring is missing.

| ID | Task | Status | Verified state in repo | Target surface(s) |
|---|---|---|---|---|
| F-21 | Wire `InsightsFeedPanel` into app-shell nav | done | Insights quick link + unread badge now wired; count fetched from `/api/insights/count` and refreshed after run completion | left nav + right drawer overlay |
| F-22 | Add `AgentMemoryTab` to Agent Builder/Detail | done | `AgentBuilderPage` now mounts `AgentMemoryTab` in a dedicated Memory tab with `agentId` | Agent Builder tabs |
| F-23 | Add `WorkflowBuilderTab` to Workflow Builder page | done | Workflow page now includes "Build from description" tab and refreshes workflow list after save callback | Workflow Builder tabs |
| F-24 | Add `SimulationPanel` as "Test Run" tab | done | `AgentBuilderPage` now mounts `SimulationPanel` in a Test Run tab with `agentId` | Agent Builder tabs |
| F-25 | Wire `ReplayControls` into activity panel | done | `ReplayControls` now mounted when run is available and stream has completed; step changes sync cursor/phase state | activity theatre footer |
| F-26 | Add `ROIDashboard` as route or Operations tab | done | Operations dashboard now exposes an ROI tab rendering `ROIDashboard` | Operations page |
| F-27 | Add `ScheduledReviewsPanel` to Operations | done | Operations dashboard now exposes a Business Reviews tab rendering `ScheduledReviewsPanel` | Operations tabs |
| F-28 | Add ROI summary widget to empty state | done | Empty state now fetches `/api/roi?days=30` and shows compact ROI card with navigation action | Chat empty state |
| F-29 | Wire `canvas.create_document` tool events to `canvasStore` | done | Live `tool_completed` events for `canvas.create_document` now parse document payload and auto-open in canvas | streaming event handling |
| F-30 | Preload `/api/documents` into `canvasStore` on app load | done | App bootstrap now fetches recent documents and hydrates canvas store immediately | app bootstrap |

### Priority order (execution)
1. F-25 `ReplayControls` in ActivityPanel
2. F-22 `AgentMemoryTab` in Agent Builder
3. F-24 `SimulationPanel` in Agent Builder
4. F-21 `InsightsFeedPanel` nav + badge count
5. F-29 `canvas.create_document` -> `canvasStore` auto-open
6. F-30 app-load document preload into `canvasStore`
7. F-23 `WorkflowBuilderTab` in Workflow page
8. F-27 `ScheduledReviewsPanel` in Operations
9. F-26 `ROIDashboard` in Operations tab or `/roi` route
10. F-28 ROI summary card in chat empty state

### Acceptance checkpoints
1. Insights bell shows unread count and opens/updates feed drawer.
2. Agent Builder exposes both `Memory` and `Test Run` tabs with valid `agentId`.
3. Activity panel shows replay controls after stream completion and highlights selected replay step.
4. Tool completion for `canvas.create_document` opens created document automatically.
5. Previously created docs appear in Canvas panel immediately after app load.
6. Operations exposes both ROI and Business Reviews surfaces.

---
## P5 â€” Proactive Intelligence Engine

**Goal**: Maia surfaces insights to users without being asked â€” monitoring connected data sources, detecting anomalies, and pushing actionable briefings.

| ID | Task | File(s) | Status | Notes |
|---|---|---|---|---|
| P5-01 | Signal detector | `api/services/proactive/signal_detector.py` | todo | Polls connector data on a cron schedule; emits `SignalEvent` when thresholds/anomalies trigger. |
| P5-02 | Insight store | `api/services/proactive/insight_store.py` | todo | Persists generated insights per tenant with `read`/`unread` state, severity, and source ref. |
| P5-03 | Feed router | `api/services/proactive/feed_router.py` | todo | Aggregates `SignalEvent` objects, runs LLM summary pass, writes to insight store. |
| P5-04 | Monitor orchestrator | `api/services/proactive/monitor.py` | todo | Entry point; registers per-tenant monitors, wires into APScheduler alongside existing agent scheduler. |
| P5-05 | REST endpoints | `api/routers/proactive.py` | todo | `GET /api/insights` (paginated), `POST /api/insights/{id}/read`, `DELETE /api/insights/{id}`. |
| P5-06 | Insights feed panel | `frontend/.../InsightsFeedPanel.tsx` | todo | Right-side panel; badge count on app shell nav; click-to-expand per insight with action button. |

**Key design notes**:
- Reuse `EventSubscription` pattern from `event_triggers.py` for connector hooks.
- Feed router calls `run_agent_task()` with a compact summarisation prompt, billable via `record_token_cost()`.
- Frontend panel subscribes to SSE `/api/insights/stream` for live push.

---

## P6 â€” Natural Language Workflow Builder

**Goal**: Users describe a multi-step automation in plain English; Maia generates a validated workflow YAML and lets the user review/edit before activating.

| ID | Task | File(s) | Status | Notes |
|---|---|---|---|---|
| P6-01 | NL â†’ YAML generator | `api/services/agents/nl_workflow_builder.py` | todo | Accepts a free-text description, calls LLM with structured output schema, returns `WorkflowDefinition`. |
| P6-02 | Workflow router | `api/routers/workflows.py` | todo | `POST /api/workflows/generate` (NL â†’ YAML), `POST /api/workflows/validate`, `GET/PUT/DELETE /api/workflows/{id}`. |
| P6-03 | NL builder tab | `frontend/.../AgentBuilderPage.tsx` | todo | New "Build from description" tab; text area â†’ "Generate" â†’ YAML preview with inline edit before save. |
| P6-04 | Validation feedback UI | `frontend/.../WorkflowValidationPanel.tsx` | todo | Shows per-step errors from `/validate`; red/yellow inline markers on YAML editor. |

**Key design notes**:
- Generator prompt uses existing `workflow_executor.py` step schema as the output contract so generated YAMLs are immediately executable.
- Extend existing YAML mode in `AgentBuilderPage` rather than adding a separate page.

---

## P7 â€” Agent Memory Network

**Goal**: Agents accumulate long-term memory across runs â€” facts, user preferences, learned patterns â€” and recall relevant context automatically at task start.

| ID | Task | File(s) | Status | Notes |
|---|---|---|---|---|
| P7-01 | Long-term memory store | `api/services/agents/long_term_memory.py` | todo | Vector-backed store per `(tenant_id, agent_id)`; `store(fact, tags)` + `recall(query, k=5)`. |
| P7-02 | memory.store tool | `api/services/agents/tools/memory_store.py` | todo | Agent-callable tool that writes a fact string to the long-term store. |
| P7-03 | memory.recall tool | `api/services/agents/tools/memory_recall.py` | todo | Agent-callable tool that retrieves top-k relevant memories and injects them as context. |
| P7-04 | Task-preparation hook | `api/services/agents/runner.py` | todo | Before every run, automatically recall top-5 memories and prepend to system context. |
| P7-05 | Memory tab in Agent Builder | `frontend/.../AgentBuilderPage.tsx` | todo | Read-only list of stored memories per agent; delete individual entries; clear all button. |

**Key design notes**:
- Use existing embeddings infrastructure (or fallback to keyword BM25) for the recall step.
- Memory is scoped per `(tenant_id, agent_id)` â€” never crosses tenants.
- Long-term memory store persists in SQLite with a `maia_agent_memory` table.

---

## P8 â€” Agent Simulation / Replay Mode

**Goal**: Developers test an agent against a canned scenario before deploying it live, and can replay any past run step-by-step to debug failures.

| ID | Task | File(s) | Status | Notes |
|---|---|---|---|---|
| P8-01 | Simulation runner | `api/services/agents/simulation.py` | todo | Accepts a `scenario` dict (mocked tool responses), runs agent against it in dry-run mode, returns step trace. |
| P8-02 | Simulation endpoint | `api/routers/agent_api/runs.py` | todo | `POST /api/agents/{id}/simulate` â€” returns `{ run_id, steps[] }`. |
| P8-03 | "Test Run" button | `frontend/.../AgentBuilderPage.tsx` | todo | Opens simulation config drawer (scenario YAML); "Run simulation" calls endpoint; results shown in existing `AgentActivityPanel`. |
| P8-04 | Replay controls | `frontend/.../DesktopViewer.tsx` | todo | Step-forward / step-back controls over a past run's event stream; highlights current step in activity panel. |

**Key design notes**:
- Dry-run mode intercepts all outbound tool calls and returns mocked responses from the scenario dict â€” no real side effects.
- Replay reuses existing `/runs/{run_id}/events` endpoint; the frontend just replays the stored event array with a time controller.

---

## P9 â€” Automated Business Reviews

**Goal**: Maia auto-generates a structured weekly/monthly business review document by pulling from all connected sources and running a summary agent.

| ID | Task | File(s) | Status | Notes |
|---|---|---|---|---|
| P9-01 | Review skill YAML | `skills/weekly-business-review.yaml` | todo | Defines data gathering steps (CRM pipeline, support tickets, revenue, ops metrics) and output document template. |
| P9-02 | Skill runner hook | `api/services/agents/scheduler.py` | todo | Add `skill_id` to scheduled run trigger; skill YAML loaded as the agent's workflow definition. |
| P9-03 | Review canvas document | `api/services/canvas/document_store.py` | todo | Auto-creates a Canvas document titled "Weekly Business Review â€” {date}" and populates with structured markdown. |
| P9-04 | Review scheduler UI | `frontend/.../ScheduledRunsPanel.tsx` | todo | UI to pick frequency (weekly/monthly), data sources, and output document target. |

**Key design notes**:
- Skill YAML follows existing workflow step schema so it runs through `workflow_executor.py` unchanged.
- Output is a Canvas document â€” users can edit, share, or export after generation.

---

## P10 â€” ROI / Savings Tracker

**Goal**: Quantify the time and cost saved by each agent so users can prove Maia's business value internally.

| ID | Task | File(s) | Status | Notes |
|---|---|---|---|---|
| P10-01 | ROI tracker service | `api/services/observability/roi_tracker.py` | todo | Per `(tenant_id, agent_id)` accumulates: runs completed, tasks automated, estimated time saved (minutes), cost avoided (USD). |
| P10-02 | Time-saved config | `api/routers/agent_api/agents.py` | todo | `PATCH /api/agents/{id}` accepts `estimated_minutes_saved_per_run` field stored in agent definition. |
| P10-03 | ROI REST endpoint | `api/routers/observability.py` | todo | `GET /api/roi` â€” returns per-agent and aggregate ROI metrics. |
| P10-04 | ROI dashboard | `frontend/.../ROIDashboard.tsx` | todo | Summary cards (total hours saved, total cost avoided, top agent by ROI); bar chart by agent; time range filter. |
| P10-05 | ROI widget on home | `frontend/.../HomePage.tsx` | todo | Compact ROI summary card at top of home screen â€” "This month: saved X hours, $Y cost avoided." |

**Key design notes**:
- `roi_tracker.py` hooks into `record_usage()` (already called in all run completion paths) â€” extend metering to also write ROI rows.
- Time saved = `estimated_minutes_saved_per_run Ã— runs_completed`; cost avoided = `estimated_minutes_saved Ã— (tenant_hourly_rate / 60)` where `hourly_rate` defaults to $50/hr configurable per tenant.

---

## Next Slice Order

1. **P5** â€” Proactive Intelligence Engine (highest market differentiation, builds on existing connector + scheduler infrastructure)
2. **P7** â€” Agent Memory Network (deepens agent quality across all existing use cases)
3. **P6** â€” NL Workflow Builder (lowers barrier to agent creation)
4. **P10** â€” ROI Tracker (business value proof; low backend complexity, high sales impact)
5. **P8** â€” Simulation / Replay (developer-experience feature; safe to do in parallel with P10)
6. **P9** â€” Automated Business Reviews (requires P5 + P6 data pipes to be solid first)

