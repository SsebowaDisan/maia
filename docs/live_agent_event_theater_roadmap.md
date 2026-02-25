# Maia Live Agent Theater Roadmap

## Objective
Build a ChatGPT-like live agent experience where users can watch every step in real time: desktop startup, file/document interactions, web actions, drafting, and execution (email/docs/slack/ads), with replay after completion.

## Core Rule
Every meaningful action must emit a structured event.  
No hidden work for user-visible workflows.

---
## Execution Status
- [x] Phase 1 - Event Protocol Foundation (`DONE` on 2026-02-25)
- [x] Phase 2 - High-Granularity Event Taxonomy (`DONE` on 2026-02-25)
- [x] Phase 3 - Live Theater UI (Message-Scoped) (`DONE` on 2026-02-25)
- [x] Phase 4 - Live Preview Tabs (Browser / Document / Email) (`DONE` on 2026-02-25)
- [x] Phase 5 - Tool Instrumentation (`DONE` on 2026-02-25)
- [x] Phase 6 - API Integrations (Real Actions) (`DONE` on 2026-02-25, baseline delivery)
- [x] Phase 7 - Safety, Control, and Trust (`DONE` on 2026-02-25, timeline policy events)
- [x] Phase 8 - Replay, Audit, and Debug (`DONE` on 2026-02-25, replay/export enabled)
- [x] Phase 9 - Performance and Scale (`DONE` on 2026-02-25, sampled + coalesced rendering)
- [x] Phase 10 - Product Polish (`DONE` on 2026-02-25, theater UX baseline)

---

## Phase 1 - Event Protocol Foundation
### Goal
Create one canonical event schema used by orchestrator, tools, streaming API, and UI.

### Deliverables
- Event envelope (required fields):
  - `run_id`, `event_id`, `seq`, `ts`, `type`, `stage`, `status`, `title`, `detail`, `data`, `snapshot_ref`
- Event levels:
  - `system`, `plan`, `tool`, `ui_action`, `preview`, `result`, `error`
- Ordering guarantees:
  - monotonic `seq` per run
- Streaming contract:
  - SSE/WebSocket event types and payload validation

### Acceptance
- All company-agent runs use the same schema.
- Frontend can render without event-type-specific hacks.

---

## Phase 2 - High-Granularity Event Taxonomy
### Goal
Define many events so users see each micro-step.

### Event Families
- Desktop/session:
  - `desktop_starting`, `desktop_ready`, `session_heartbeat`, `session_paused`, `session_resumed`
- Planning:
  - `planning_started`, `plan_candidate`, `plan_refined`, `plan_ready`
- Tool lifecycle:
  - `tool_queued`, `tool_started`, `tool_progress`, `tool_completed`, `tool_failed`, `tool_retry`
- Documents:
  - `doc_open`, `doc_scroll`, `doc_locate_anchor`, `doc_select_range`, `doc_insert_text`, `doc_replace_text`, `doc_insert_table`, `doc_checkbox_toggle`, `doc_save`, `doc_version_created`
- PDF/research:
  - `pdf_open`, `pdf_page_change`, `pdf_scan_region`, `pdf_highlight_added`, `pdf_evidence_linked`
- Email:
  - `email_draft_create`, `email_set_to`, `email_set_cc`, `email_set_subject`, `email_set_body`, `email_attach`, `email_ready_to_send`, `email_sent`
- Browser:
  - `browser_open`, `browser_navigate`, `browser_wait_network`, `browser_click`, `browser_scroll`, `browser_extract`, `browser_capture`
- Synthesis/answer:
  - `response_outline_ready`, `response_writing`, `response_chunk`, `response_written`, `synthesis_completed`
- Governance:
  - `approval_required`, `approval_granted`, `policy_blocked`, `full_access_applied`

### Acceptance
- At least 80% of user-visible actions map to explicit events.
- Missing event coverage report generated per run.

---

## Phase 3 - Live Theater UI (Message-Scoped)
### Goal
Render agent activity under each relevant chat message with replay controls.

### Deliverables
- Message-scoped activity panel (already started)
- Cinematic stage:
  - live status, step progress, current action subtitle
- Replay timeline:
  - scrubber, speed, jump to step, auto-follow
- Event chips:
  - compact by default, expandable detail
- Per-message persistence:
  - replay remains available after run completion

### Acceptance
- Activity appears directly below the corresponding message.
- Replay works for both completed and in-progress runs.

---

## Phase 4 - Live Preview Tabs (Browser / Document / Email)
### Goal
Show “what the agent is doing” visually, not only text logs.

### Deliverables
- Preview tabs in activity panel:
  - `Browser`, `Document`, `Email`, `System`
- Document/PDF preview:
  - page changes, highlighted regions, cursor overlays
- Email preview:
  - live form fill and attachment chips
- Browser preview:
  - navigation + action trace (frame or simulated snapshots)

### Acceptance
- User can watch at least one full document workflow and one email workflow live.

---

## Phase 5 - Tool Instrumentation
### Goal
Emit granular events from each tool implementation, not just orchestrator wrappers.

### Deliverables
- Standard event helper in tool base class
- Instrumented tools:
  - research/web, report, document, email, invoice, slack, ads
- Snapshot support:
  - optional `snapshot_ref` for preview frames or diff chunks

### Acceptance
- Each tool emits start/progress/end/error and domain-specific events.

---

## Phase 6 - API Integrations (Real Actions)
### Goal
Connect real external systems after protocol/UI stability.

### Priority Order
1. Gmail + Microsoft email
2. Google Docs + Microsoft Word/Excel (Graph)
3. Slack
4. Google Ads

### Deliverables
- Connector capability map
- Credential/config validation screens
- End-to-end evented workflows per connector

### Acceptance
- Real send/write actions execute and stream live events.

---

## Phase 7 - Safety, Control, and Trust
### Goal
Prevent silent destructive actions while preserving “live” feel.

### Deliverables
- Modes:
  - `restricted` (approval for irreversible actions)
  - `full_access` (auto-execute with audit)
- Confirmation events:
  - `approval_required`, `approval_granted`, `approval_denied`
- Action receipts:
  - doc version links, message IDs, external URLs

### Acceptance
- Every irreversible action has explicit policy evidence in timeline.

---

## Phase 8 - Replay, Audit, and Debug
### Goal
Make every run inspectable and reproducible.

### Deliverables
- Stored event log + snapshots per run
- Timeline replay from persisted data
- Run export (JSON)
- Developer diagnostics:
  - event gaps, latency per step, tool failure clustering

### Acceptance
- Any run can be replayed without rerunning tools.

---

## Phase 9 - Performance and Scale
### Goal
Support high event volume without noisy UX or UI lag.

### Deliverables
- Event throttling/compression strategy:
  - keep raw events, render coalesced view
- Backpressure handling for stream
- Sampling for ultra-frequent events (cursor/scroll)
- Virtualized timeline list

### Acceptance
- Smooth UI at 5,000+ events in a single run.

---

## Phase 10 - Product Polish
### Goal
Make the experience premium and intuitive.

### Deliverables
- Apple-style visual polish:
  - restrained palette, motion quality, clean hierarchy
- UX controls:
  - filter by event family, search events, bookmark moments
- “What changed” panel:
  - doc diff, email diff, action summary

### Acceptance
- Users can understand and trust agent behavior without technical knowledge.

---

## Implementation Rulebook
- Emit events before and after every meaningful mutation.
- Never block answer streaming while activity streaming.
- Keep event names professional and stable (no ad hoc variants).
- Version event schema (`event_schema_version`) for compatibility.
- Avoid file bloat:
  - keep each file under 1000 LOC.
- Every new tool must ship with event instrumentation and tests.

---

## Immediate Next Sprint (Execution Plan)
1. Finalize event schema and constants module.
2. Refactor orchestrator to use schema + sequence IDs.
3. Add tool-level progress event helpers.
4. Upgrade activity panel with preview tabs and event filters.
5. Add persisted replay loader for prior runs.
6. Integrate first real connector (email) end to end.

---

## Definition of Done (Program Level)
- User sees agent desktop start.
- User sees detailed live actions (doc/email/browser) while response is generated.
- User can replay the entire run with evidence and outcomes.
- External actions are auditable and policy-compliant.
