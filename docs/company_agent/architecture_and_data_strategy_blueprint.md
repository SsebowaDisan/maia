# Architecture and Data Strategy Blueprint

## Runtime Architecture
- API Layer: FastAPI routers for chat, settings, integrations, and orchestration triggers.
- Orchestrator Layer: run planning, tool selection, execution sequencing, and synthesis.
- Specialist Tool Layer: domain tools (research, reporting, analytics, email, invoice, workspace).
- Connector Layer: provider-specific adapters with normalized request/response behavior.
- Persistence Layer:
  - settings store (user/tenant controls)
  - run memory and audit logs
  - activity timeline storage
  - indexed document/vector data stores

## Replay-Safe State Transition Model
### Core Principles
- every state change is evented with ordered sequence numbers
- run events are append-only and persisted
- execution results are captured per step with status and summary
- failed actions are stored with explicit failure reason

### Run Lifecycle
1. `desktop_starting`
2. `planning_started`
3. `plan_ready`
4. repeated step cycle:
 - `tool_queued`
 - `tool_started`
 - `tool_progress` (0..n)
 - `tool_completed` or `tool_failed`
5. `verification_started` -> checks -> `verification_completed`
6. `synthesis_started` -> `synthesis_completed`
7. `event_coverage`

### Replay Requirements
- sequence numbers must remain monotonic within run scope
- each run event carries run_id, event_id, timestamp, and metadata payload
- replay can reconstruct ordered execution without querying external APIs

## Data Strategy
### Storage Categories
- Configuration and policy: user/tenant settings, governance flags
- Operational telemetry: activity events, tool traces, audit records
- Knowledge and retrieval: indexed files/URL chunks, vector and doc stores
- Output artifacts: reports, chart files, invoice documents

### Security and Compliance Controls
- tenant isolation by design for settings/tokens/data access
- secrets never persisted in frontend state
- role-based controls for all execute actions
- audit logs for every high-risk operation

### Retention and Deletion
- run/event/audit data retention policies to be enforced centrally
- deletion workflows must support user and tenant-scope cleanup requests
- storage schemas must avoid cross-tenant references

