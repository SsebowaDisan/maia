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
- citation-by-default answers: every final response includes evidence citations, not only PDF/RAG flows
- no regressions for full-access mode

### Citation Enforcement Policy
- applies to both `ask` mode and `company_agent` mode
- server enforces citations even if client requests `citation=off`
- if model output misses inline references, backend appends evidence citation links or an explicit internal-evidence trace line

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
Status: in_progress

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

## Bright Data-Inspired Native Web Data Roadmap (No Bright Data API Dependency)

### Objective
Implement Bright Data MCP-grade web research and scraping reliability inside Maia using native connectors only (Brave/Bing + Playwright + Maia extraction), while keeping the existing LLM-first planner and theatre-first execution model.

### Why this roadmap
Bright Data MCP performs well because it combines:
- search tools + page extraction tools + browser control tools in one stack
- robust provider routing and fallback
- structured extraction from raw pages
- explicit observability for every step

Maia already has major building blocks (`marketing.web_research`, `browser.playwright.inspect`, tool traces, theatre), so the roadmap focuses on reliability, routing, and structured extraction depth.

### Non-Goals
- no Bright Data API calls
- no MCP runtime dependency required for this roadmap
- no replacement of Maia planner/orchestrator architecture

### Current Baseline In Maia
- web research tool: `api/services/agent/tools/research_tools.py`
- browser inspection tool: `api/services/agent/tools/browser_tools.py`
- browser connector: `api/services/agent/connectors/browser_connector.py`
- search connectors: `api/services/agent/connectors/brave_search_connector.py`, `api/services/agent/connectors/bing_search_connector.py`
- planner/routing: `api/services/agent/planner.py`, `api/services/agent/llm_intent.py`
- theatre event contract: `api/services/agent/events.py`

### Implementation Principles
- llm-first routing for web intent (`online_research` vs `url_scrape` vs `none`)
- provider abstraction in tool params (`provider`, `web_provider`) with deterministic defaults
- theatre completeness: every provider and extraction stage must emit user-visible events
- structured output first: capture URLs, titles, snippets, entities, claims, and evidence references
- safe fallback: degrade gracefully when a provider is unavailable

### Phase W0: Routing Contract (LLM-only)
Status: done

Scope:
- finalize LLM web-routing contract in `llm_intent.py`
- enforce routing decision in planner normalization
- remove any keyword-only routing dependencies

Exit criteria:
- URL scrape prompts route to `browser.playwright.inspect`
- online research prompts route to `marketing.web_research`
- routing decision is emitted in theatre at planning stage

### Phase W1: Research Provider Hardening
Status: done

Scope:
- make Brave the primary research provider
- keep optional controlled fallback to Bing
- emit provider-start/provider-complete/provider-failed events

Implementation tasks:
- add strict provider mode handling in `marketing.web_research`
- add retries/backoff and typed failure reasons in search connectors
- persist provider metadata in tool output for downstream evidence scoring

Exit criteria:
- deterministic provider behavior per plan
- clear theatre timeline for provider path
- test coverage for primary, fallback, and hard-fail modes

### Phase W2: Website Scrape Reliability Layer
Status: done

Scope:
- strengthen Playwright scrape reliability for dynamic websites
- add navigation strategy and retry policy
- improve content extraction quality from rendered pages

Implementation tasks:
- staged extraction pipeline in `browser_connector.py`:
  - initial render capture
  - lazy-load scroll strategy
  - optional internal-link follow-up for same-domain evidence
- classify extraction quality and empty-page states
- add standardized metadata: `render_quality`, `content_density`, `blocked_signal`

Exit criteria:
- higher successful extraction rate on JS-heavy pages
- blocked/empty cases produce explicit remediation in output
- theatre shows each scrape stage with timing and result

### Phase W3: Structured Extraction (Bright Data `extract` equivalent, native)
Status: in_progress

Scope:
- add Maia-native structured extraction tool from page text/HTML
- support schema-guided extraction for workflows (company profile, pricing, contacts, etc.)

Implementation tasks:
- new tool: `web.extract.structured` under `api/services/agent/tools/`
- inputs: URL, extraction goal, optional field schema
- outputs: normalized JSON + confidence + source evidence links
- LLM-based extraction with deterministic sanitization and schema validation

Exit criteria:
- tool returns stable JSON for repeated runs on same page
- extraction result is linked to theatre evidence cards
- failure mode returns partial extraction + gaps

### Phase W4: Browser Interaction Model Upgrade
Status: in_progress

Scope:
- move from broad page extraction to targeted interaction evidence
- include element-level operations and page-state artifacts

Implementation tasks:
- add browser helper actions for targeted evidence:
  - click element by safe selector strategy
  - fill inputs for navigation-only scenarios
  - capture post-action snapshot
- keep strict policy limits for write-like browser actions

Exit criteria:
- interaction flows produce reproducible evidence snapshots
- all actions visible in theatre with snapshots and event sequencing

### Phase W5: Web Dataset Adapters (Native, Priority Domains)
Status: in_progress

Scope:
- replicate high-value `web_data_*` behavior for selected domains using native scrapers

Initial adapters:
- LinkedIn company profile (public page fields where allowed)
- Reuters article summary extraction
- GitHub repository file/content metadata
- Google Maps review summary (public pages where allowed)

Exit criteria:
- each adapter returns normalized schema + source URL
- adapters can be selected by LLM planner without manual API naming
- adapter failures include remediation and fallback to generic scrape path

### Phase W6: Theatre and UX Completion
Status: done

Scope:
- make web research/scrape flow fully transparent in theatre and chat outputs

Implementation tasks:
- add planner event for routing decision
- add provider badge and extraction-quality markers in activity panel
- persist web evidence metadata into message history for replay

Exit criteria:
- users can see: route chosen, provider used, extraction quality, evidence links
- no hidden web step outside theatre visibility

### Phase W7: Validation and Performance
Status: done

Scope:
- reliability, latency, and quality validation for native web stack

Test matrix:
- static page, dynamic page, infinite scroll, anti-bot soft block, empty content
- provider unavailable/fallback
- schema extraction success/failure

KPIs:
- web task completion rate
- extraction quality score
- median time to first web evidence event
- fallback frequency

Exit criteria:
- KPI thresholds defined and met in CI smoke + staging runs
- regressions block release via test gates

### Exact Integration Order
1. Complete W0 routing contract and planner/theatre wiring.
2. Harden W1 provider behavior and tests.
3. Implement W2 extraction reliability improvements.
4. Add W3 structured extraction tool.
5. Deliver W6 UX/theatre completion in parallel with W3-W4.
6. Add W5 domain adapters based on business priority.
7. Gate rollout using W7 KPIs before enabling by default.

### Definition of Done For Web Features
- planner route is LLM-derived and auditable
- every web stage is theatre-visible
- outputs include source links and structured evidence
- fallback path is deterministic and tested
- no Bright Data API dependency

### Web Implementation Update (2026-03-02)
- Completed W0:
  - planner now resolves web routing through `detect_web_routing_mode` and emits `llm.web_routing_decision` in theatre planning events.
  - routing metadata is passed into plan normalization to avoid divergent route decisions.
- Completed W1:
  - `marketing.web_research` now emits provider failure metadata with typed reasons (`missing_credentials`, `auth_error`, `rate_limited`, `timeout`, `upstream_error`, `invalid_response`, `provider_unavailable`).
  - Bing connector now has retry/backoff behavior for transient failures.
  - provider attempt history/failure metadata is persisted in tool output for downstream evidence handling.
- Completed W2:
  - Playwright connector now emits staged extraction metadata (`initial_render`, `lazy_load_scroll`, `same_domain_followup`) with timing.
  - standardized scrape quality metadata added: `render_quality`, `content_density`, `blocked_signal`, `blocked_reason`.
  - browser tool output includes remediation-oriented next steps for blocked/low-quality extraction cases.
- Advanced W3:
  - new tool `web.extract.structured` implemented and registered for policy/planner/tool-registry execution.
  - tool supports URL or direct page text, optional schema-guided extraction, normalized JSON output, confidence, evidence rows, and gap reporting.
- Advanced W6:
  - theatre metadata now carries routing/provider/quality fields into replay action metadata.
  - browser desktop scene shows provider and extraction quality badges from live event payloads.
- Advanced W4:
  - Playwright connector now accepts optional `interaction_actions` (`click`/`fill`) with per-action started/completed/failed theatre events.
  - browser inspection tool forwards interaction actions and persists action metadata in result payload.
- Advanced W5:
  - new adapter tool `web.dataset.adapter` added with LLM-based adapter selection and native adapter schemas:
    `linkedin_company`, `reuters_article`, `github_repository`, `google_maps_reviews`, `generic_web_profile`.
  - adapter tool delegates extraction to `web.extract.structured` and returns normalized adapter metadata.
- Advanced W7:
  - targeted tests added/updated for routing, provider fallback/hard-fail behavior, and structured extraction.
  - added run-level web KPI rollups (`web_steps_total`, `avg_quality_score`, `blocked_count`, `avg_duration_seconds`) and finalization event `web_kpi_summary`.
  - KPI readiness heuristic added (`ready_for_scale`) to gate scale-up decisions.
- Advanced W3:
  - structured extraction now computes `schema_coverage`, `quality_score`, `quality_band`, and deterministic `extraction_fingerprint`.
  - per-run extraction cache added to stabilize repeated extraction calls on same content/schema.
- Advanced W4:
  - LLM-based browser interaction policy review added before Playwright action execution (`browser_interaction_policy`).
  - blocked-page recovery retries added in read-only mode with quality-aware fallback selection.
- Advanced W5:
  - adapter selection now includes LLM confidence + reason metadata.
  - low-confidence adapter results trigger automatic fallback to `generic_web_profile` extraction.
- Completed W6:
  - web evidence is now persisted per run (`__web_evidence`) and summarized in finalization via `web_evidence_summary`.
  - chat message metadata now stores `web_summary` for replay/history hydration in React.
- Completed W7:
  - release-gate evaluation now runs at finalization (`web_release_gate`) using configurable KPI thresholds.
  - gate payload includes failed checks, success/fallback rates, and `gate_enforced` mode for rollout control.
- Hardening update (LLM-first query strategy):
  - web query variant generation now uses LLM-first variant planning with deterministic fallback.
  - removed static phrase-based query expansion patterns in search helper fallback paths.

---

## React UI Unification Roadmap (Primary UI = `frontend/user_interface`)

### Objective
Unify Maia onto the React UI (`localhost:5173` in dev) backed by FastAPI (`localhost:8000`), and fully remove Gradio/KTEM UI runtime once feature parity and deployment cutover are complete.

### Current State (Baseline)
- React UI is running from `frontend/user_interface` (Vite).
- FastAPI backend serves APIs from `api/main.py`.
- Runtime entrypoints now default to FastAPI + React static hosting.
- Legacy Gradio launch files were removed; remaining cleanup is docs/reference burn-down.

### Scope
- In scope:
  - frontend runtime and API integration alignment
  - authentication/session model for React stack
  - deployment/runtime cutover from Gradio to FastAPI+React
  - full legacy UI deletion
- Out of scope:
  - changes to business workflow semantics unless required by UI/API contract
  - connector capability expansion unrelated to UI cutover

### Migration Principles
- single-source UX: React is the only end-user surface
- API-first contract: all UI behavior flows through versioned API endpoints
- reversible milestones: each phase has a rollback point
- no dark launches without observability and explicit acceptance criteria

### Phase 0: Inventory and Guardrails
Status: done

Goals:
- enumerate all Gradio runtime entrypoints and deployment references
- define migration checkpoints and rollback triggers
- add migration tracking to active execution tracker

Exit criteria:
- full map of entrypoints (`app.py`, `launch.sh`, deploy config) documented
- roadmap and tracker checklist committed

Rollback:
- none required (documentation and planning only)

### Phase 1: React-First Developer Workflow
Status: done

Goals:
- make React+FastAPI the default documented local workflow
- add explicit scripts for running backend + frontend stack
- remove Gradio startup path from operator guidance

Implementation tasks:
- add dev scripts:
  - backend: `run_api.py` (`api.main:app` on `:8000`)
  - frontend: `frontend/user_interface` Vite on `:5173`
  - combined helper scripts for one-command local startup
- update README with React-first startup flow
- add frontend env template for `VITE_API_BASE_URL`
- add frontend env template for `VITE_USER_ID`

Exit criteria:
- new contributors start the correct UI without ambiguity
- local dev commands for React stack are documented and tested

Rollback:
- revert startup scripts and docs from pre-cutover release tag

### Phase 2: Authentication and Session Contract (React Stack)
Status: in_progress

Goals:
- replace implicit `"default"` user fallback with explicit auth/session behavior for React
- ensure each request has deterministic tenant/user identity

Implementation tasks:
- define auth mode matrix (dev-local, single-user, multi-user, SSO)
- implement explicit user/session propagation for `/api/*`
- remove silent fallback user path in production modes
- add auth error surfaces in UI (session expired, unauthorized, forbidden)

Exit criteria:
- no production request path relies on implicit default user
- UI has clear sign-in/session states and recovery paths

Rollback:
- keep dev-only fallback behind explicit feature flag

### Phase 3: Feature Parity and Legacy Dependency Burn-Down
Status: planned

Goals:
- ensure all user-critical capabilities used in Gradio are available via React UI + API
- remove backend couplings that exist only for Gradio behavior

Implementation tasks:
- parity matrix by domain (chat, files, resources, settings, integrations)
- port/replace missing controls in React components
- remove unused Gradio-only hooks and event paths once parity is confirmed

Exit criteria:
- parity checklist complete for all must-have workflows
- no active user journey requires Gradio

Rollback:
- temporary feature flag to re-enable specific legacy endpoints if needed

### Phase 4: Deployment Cutover to React + FastAPI
Status: done

Goals:
- switch deployment runtime from Gradio entrypoint to API entrypoint
- serve built React bundle from FastAPI in packaged environments

Implementation tasks:
- Docker/build pipeline:
  - build frontend assets during image build
  - serve `frontend/user_interface/dist` from FastAPI mount
- launch/runtime scripts:
  - default to API app startup
- update infra configs and health checks

Exit criteria:
- production starts without Gradio process
- health checks and metrics confirm stable cutover

Rollback:
- revert deployment/runtime files from pre-cutover release tag

### Phase 5: Full Gradio Deletion (Final)
Status: in_progress

Goals:
- permanently remove Gradio/KTEM UI runtime from this repository

Implementation tasks:
- delete legacy UI launch entrypoints and runtime branches:
  - `app.py`, Gradio branches in `launch.sh`, Gradio-only deploy toggles
- remove stale docs and scripts that reference Gradio UI operation
- remove Gradio UI assets/code paths not required by backend services
- tighten CI to fail on reintroduction of legacy runtime entrypoints

Exit criteria:
- no Gradio UI process can be started from repo defaults
- docs, scripts, and deployment paths are React/FastAPI only
- regression suite and smoke tests pass on new stack

Rollback:
- none (post-removal). Rollback requires reverting to pre-Phase-5 release tag.

### Risk Register
- Auth migration risk: moving off implicit user fallback can break existing local workflows.
  - Mitigation: staged auth flags and explicit dev mode profile.
- Deployment risk: frontend build artifacts missing in image.
  - Mitigation: CI build validation + startup assertions.
- Operational risk: hidden dependencies on Gradio event behavior.
  - Mitigation: parity matrix and canary cutover before deletion.

### Acceptance Checklist (Program-Level)
- React stack is the only documented and default run path.
- API auth/session behavior is explicit and test-covered.
- Deployment no longer starts Gradio runtime.
- All critical user workflows validated in React UI.
- Final legacy removal completed with no references in docs/scripts.
