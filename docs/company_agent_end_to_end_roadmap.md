# World-Class Company AI Agent Roadmap

## Purpose
Build Maia into a production-grade company agent that can execute business tasks end-to-end from one natural-language prompt.

Primary outcomes:
- non-technical users can run complex workflows from the chat bar
- all major actions are visible live in theatre
- execution is policy-safe, auditable, and replayable
- the same agent flow applies across all API families

## Product Principles
- theatre-first: every meaningful action emits live activity events
- llm-first planning: user does not need to name APIs
- wrapper-first UX: prefer business workflows over low-level API parameters
- policy-safe execution: RBAC + confirmation for execute-risk actions
- deterministic auditability: logs, evidence links, and run replay metadata
- no regressions for full-access mode

## End-User Experience
### What the user does
1. Type a business request in plain language.
2. Optionally connect Google or other providers once.
3. Watch Maia execute step-by-step in theatre.

### What Maia does automatically
1. Rewrite request into a detailed execution brief.
2. Build task contract (required outputs, facts, actions).
3. Infer domains and select tools/APIs via LLM planning.
4. Execute steps while streaming progress in theatre.
5. Log notes/status in Docs/Sheets when enabled.
6. Enforce contract gate before external actions.
7. Return final response with evidence and status.

## Unified Execution Flow (All APIs)
Every API integration must follow this exact path:

1. `task_understanding_started`
2. `llm.task_rewrite_started` and `llm.task_rewrite_completed`
3. `llm.task_contract_started` and `llm.task_contract_completed`
4. `llm.capability_plan` (domains + rationale)
5. `plan_step` events for planned actions
6. `tool_queued` and `tool_started`
7. tool trace events (`started/progress/completed/failed`)
8. `tool_completed` or `tool_failed`
9. contract verification before execute-risk delivery actions

### Standard API event contract
For direct API tools, emit at minimum:
- prepare request
- API call started
- API call completed
- normalize response for downstream steps

All payloads include `tool_id` and `scene_surface` for theatre rendering.

## Capability Strategy
### LLM-First Routing
Planner should infer APIs/tools from business intent.

Examples:
- "build weekly KPI sheet" -> GA4 + Sheets workflow
- "plan visits for tomorrow" -> route planning workflow
- "send cloud incident digest" -> logging + email workflow
- "prepare proposal and share with CEO" -> docs + draft workflow

Users should not provide method/path/body unless they explicitly want low-level API control.

### Wrapper-First Hierarchy
1. Use business workflows where available.
2. Use domain tools when wrapper is unavailable.
3. Use generic API tools when no higher-level path exists.

## Integration Baseline
### Core planner/orchestrator components
- task rewrite and contract extraction
- capability planning with domain mapping
- plan decomposition and refinement
- guarded step execution and remediation
- delivery gate with required-action verification

### Existing production pillars
- tool registry with policy checks
- live event broker for theatre stream
- observability logs and metrics endpoint
- memory and context support
- preflight checks for credentials/providers

## API Families and Business Roles
### Workspace and communication
- Gmail API: draft/send/search communications
- Docs API: generate notes, proposals, reports
- Sheets API: trackers, KPI logs, status updates
- Drive API: discover and retrieve shared files
- Calendar/Tasks API: schedule and follow-up workflows

### Data and analytics
- GA4 Data API: KPI reporting and trend summaries
- BigQuery APIs: warehouse access and query workflows
- Cloud Logging/Monitoring/Trace APIs: incident diagnostics
- Dataform/Dataplex APIs: data pipeline and governance flows

### Maps and location
- Geocoding/Distance/Directions APIs: route and travel planning
- Address Validation API: customer/address quality checks
- Elevation/Static/Embed APIs: map context outputs

### Operations and cloud
- Cloud Storage APIs: document and artifact storage
- Cloud SQL/Datastore APIs: operational data administration

## Phase Plan

## Phase 0: Stability Baseline
Status: active

Scope:
- stabilize tests for planner/orchestration/tooling
- enforce docs LOC guardrails
- keep compatibility shims intact for legacy imports

Exit criteria:
- api/tests green in CI
- no compatibility regressions in legacy module paths

## Phase 1: Unified API Flow Contract
Status: active

Scope:
- ensure all API tools follow standard event contract
- normalize error payloads for clear user remediation
- align scene surfaces for consistent theatre rendering

Exit criteria:
- each API tool emits prepare/start/complete/normalize events
- tool failures include actionable remediation hints

## Phase 2: LLM-First Capability Routing
Status: active

Scope:
- domain inference from rewritten task + contract
- planner prompt enriched with capability catalog metadata
- broad toolset available by default to LLM planner

Exit criteria:
- user prompts route correctly without naming APIs
- planner picks wrappers first for non-technical tasks

## Phase 3: Business Workflow Expansion
Status: in_progress

Scope:
- add more non-technical workflows:
  - route planning and dispatch support
  - KPI report pipelines
  - incident digest operations
  - invoice and proposal workflows
  - meeting scheduling and follow-up

Exit criteria:
- each workflow supports plain-language prompt execution
- each workflow has theatre evidence and test coverage

## Phase 4: Data/ML Workbench (Theatre-First)
Status: planned

Scope:
- dataset ingestion/profile/cleanup flows
- AutoML and model evaluation workflows
- explainability outputs for non-technical stakeholders

Exit criteria:
- users upload dataset and run analysis from chat bar
- all model steps visible in theatre with metrics

## Phase 5: Reliability and Cost Controls
Status: planned

Scope:
- caching and retries for API connectors
- planner token budget and prompt minimization
- timeout tuning and graceful fallbacks

Exit criteria:
- lower median execution time
- reduced LLM/API cost per task with no quality drop

## Phase 6: GA Readiness
Status: planned

Scope:
- tenant-safe governance defaults
- acceptance matrix across major workflows
- incident runbooks and operator documentation

Exit criteria:
- release checklist complete
- production monitoring and alerting in place

## Quality Gates
A feature is done only if:
- theatre timeline shows full execution lifecycle
- policy controls are enforced in restricted mode
- full-access mode behavior remains intact
- contract gate blocks unsafe/incomplete delivery
- observability records plan, tool, and run outcomes
- tests cover normal path, failure path, and fallback path

## Testing Strategy
- unit tests for planner/domain inference
- unit tests for tool event sequencing
- integration tests for connector auth/failure modes
- contract tests for delivery gating and remediation insertion
- UI tests for theatre event rendering consistency

## Security and Governance
- least-privilege tool permissions per role
- confirmation required for execute-risk tools in restricted mode
- explicit token/config checks in preflight and failures
- audit log for tool execution and final delivery actions

## Performance Targets
- fast first activity event after prompt submission
- bounded planner latency via prompt budgets
- stable tool execution retries with clear backoff behavior
- graceful degradation when credentials/providers are missing

## Current Priority Backlog
1. enforce standardized API event contract for all connector families
2. keep LLM-first planner defaults and tune routing precision
3. expand wrapper workflows for non-technical business use cases
4. complete data/ML theatre workflows
5. tighten CI to catch compatibility and docs guardrail regressions early

## Definition of Success
Maia is successful when a non-technical business user can type one request, watch all actions live in theatre, and receive a verified, policy-safe final outcome without API-level configuration.
