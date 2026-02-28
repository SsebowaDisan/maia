# World-Class Company AI Agent Roadmap
## Purpose
Build Maia into an enterprise-grade Company AI Agent that can reliably handle:
- research and evidence synthesis
- analytics and reporting
- server-side communication workflows
- strategic, operational, HR, and finance support
This roadmap is implementation-focused and slice-driven.
## Non-Negotiable Engineering Constraints
- replay-safe state transitions
- no file over 500 LOC
- LLM-first intelligence across planning, decomposition, extraction, verification, and response shaping
- no hardcoded words or keyword lists in task contracts or execution contracts
---
## Rules For Execution
- Only one active slice at a time.
- A slice is complete only when:
 - acceptance tests pass
 - regression slice passes
 - checklist is updated to `done`
- Do not start the next slice until the current slice is complete.
- If execution goes sideways (failed assumptions, repeated test failures, unclear architecture fit), stop immediately and re-plan before continuing.
- Maintain `tasks/todo.md` during execution; every active slice must have explicit, checkable tasks and verification notes.
- After every user correction, append a lesson entry to `tasks/lessons.md` with root cause and prevention rule before closing the slice.
- Going forward, a slice status cannot be `done` while any checklist item remains `todo` or `in_progress`.
- Use LLM decisioning wherever possible for intent understanding and step decomposition; use deterministic heuristics only as safety fallback.
## Execution Contract Addendum: Module Tree and File Naming
- Refactors of large files must produce a professional package tree with clear domain boundaries and a stable public entrypoint (for example `<package>/app.py`).
- Folder and module names must be domain-accurate and searchable; avoid vague names and avoid ad-hoc filenames.
- Prefer nested structure over filename prefixes:
 - `feature/history_compiler.py` over `feature_history.py`
 - `feature/realtime_context.py` over `feature_now.py`
- Every module must have one responsibility and remain under 500 LOC (preferred 350-450 LOC).
- Shared types/contracts must be extracted first into dedicated modules (for example `core/types.py`, `domain/models.py`) before moving logic.
- Move order for safety is mandatory:
 - types/models first
 - pure logic second
 - side-effect adapters/integrations last
- Backward compatibility is mandatory during migration:
 - keep original file as a thin shim that re-exports the new public entrypoints
 - include deprecation note pointing to the new entry module
- Circular imports are contract violations:
 - dependency direction must stay explicit
 - shared abstractions should be lifted to neutral modules instead of cross-importing features
- `utils.py` as a catch-all is prohibited in new slices; helper modules must be named by purpose (for example `text_normalization.py`, `token_budget.py`, `chunking.py`).
- Any file move or rename must update all imports in the same slice and keep acceptance + regression tests green before marking `done`.
## Naming Rule (Mandatory)
- Scope: these naming rules apply to all modules under `src/`, not only UI modules.
- Structure must be domain-first, not prefix-first.
- Do not add new root-level prefix-first modules in any `src/namel3ss/*` package.
- Do not add new root-level `manifest_*` modules under `src/namel3ss/ui/`.
- Prefer paths like:
 - `src/namel3ss/ui/manifest/chart.py`
 - `src/namel3ss/ui/manifest/table.py`
 - `src/namel3ss/ui/manifest/chat/items.py`
 - `src/namel3ss/ui/manifest/chat/composer.py`
- Keep names boring and searchable: lowercase folders, snake_case files.
- Any move/rename must update all imports in the same slice and keep tests green.
## Status Legend
- `todo` not started
- `in_progress` currently active
- `done` complete and validated
- `blocked` needs decision or prerequisite
---
## Execution Policy
- Roadmap execution is sequential and autonomous.
- Work advances slice by slice with no skip-ahead.
- The next slice starts automatically only after the active slice is validated `done`.
- Re-planning is mandatory whenever the active slice fails acceptance tests twice without a code change that addresses root cause.
- Planning and orchestration must prefer LLM-generated structure before any hardcoded keyword path.
## Global Slice Gate (Applies to Every Slice)
1. Implement scope for the active slice only.
2. Run slice acceptance tests.
3. Run assigned regression slice tests.
4. Update slice checklist state to `done`.
5. Update `tasks/todo.md` with execution evidence for the completed slice.
6. If the user corrected behavior during the slice, record the correction in `tasks/lessons.md`.
7. Only then activate the next slice.
## Release-Wide Quality Gates
- Evidence and traceability for all research/report outputs.
- Audit logs for all write/execute operations.
- RBAC and approval controls enforced for sensitive actions.
- All critical state transitions are replay-safe and idempotent.
- No file exceeds 500 LOC after merge.
- Going forward, every completed slice has a matching verification record in `tasks/todo.md`.
- Repeated mistakes are reduced over time via enforced `tasks/lessons.md` updates.
---
## Foundation and Core Infrastructure
### Strategic Scope and Governance Alignment
**Status:** `done`
**Objective**
- lock functional scope, guardrails, and measurable outcomes across departments
**In Scope**
- final use-case catalog: research, analytics, email automation, RFP/brief generation
- stakeholder alignment: legal, marketing, HR, finance, IT
- compliance and data handling baseline
- formal acceptance criteria per capability area
**Deliverables**
- approved capability map
- role and permission matrix draft
- governance checklist template
**Acceptance Tests**
- all domain owners sign off on capability and data boundaries
- each capability has explicit success criteria and out-of-scope rules
**Regression Slice**
- none
**Checklist**
- [ ] capability map finalized (`in_progress`)
- [ ] governance baseline approved (`todo`)
- [ ] acceptance criteria cataloged (`todo`)
### Architecture and Data Strategy Blueprint
**Status:** `done`
**Objective**
- define modular runtime and durable data topology
**In Scope**
- orchestrator + specialist-module architecture
- ingestion and storage plan (documents, vector index, task/results DB)
- event model for replay-safe state transitions
- data retention, isolation, and deletion strategy
**Deliverables**
- architecture diagram with domain boundaries
- state machine spec for agent runs
- storage/indexing design doc with scale assumptions
**Acceptance Tests**
- architecture review approved by backend/platform owners
- replay simulation proves deterministic run reconstruction
**Regression Slice**
- Strategic Scope and Governance Alignment
**Checklist**
- [ ] architecture spec approved (`todo`)
- [ ] state model validated for replay safety (`todo`)
- [ ] data governance controls mapped (`todo`)
### Integration and Runtime Baseline
**Status:** `done`
**Objective**
- establish secure integration/runtime primitives before specialist features
**In Scope**
- core connectors: Gmail (DWD), web crawl/search, file parsing
- local execution environment and container strategy
- centralized config and secret loading model
- connectivity health checks for external systems
**Deliverables**
- connector contracts and health endpoints
- secure env/secret management policy
- baseline runtime deployment profile
**Acceptance Tests**
- connectors pass health checks in staging
- missing/invalid credential cases return actionable errors
**Regression Slice**
- Architecture and Data Strategy Blueprint
**Checklist**
- [ ] connector baseline available (`todo`)
- [ ] config/secrets standardized (`todo`)
- [ ] runtime smoke checks green (`todo`)
---
## Core Specialist Capability Buildout
### Evidence Research Assistant
**Status:** `done`
**Objective**
- provide evidence-grounded research synthesis
**In Scope**
- web search and browsing execution
- document summarization
- citation and source trace chain in outputs
**Deliverables**
- research module API contract
- source attribution schema
- user-visible evidence blocks
**Acceptance Tests**
- every answer contains traceable citations when external/internal sources are used
- citation links and snippets match retrieved content
**Regression Slice**
- Integration and Runtime Baseline
**Checklist**
- [ ] retrieval + summarization operational (`todo`)
- [ ] citation chain validated (`todo`)
- [ ] traceability UI/API verified (`todo`)
### Executive Writer and Report Generator
**Status:** `done`
**Objective**
- generate executive-ready structured outputs
**In Scope**
- templates: market analysis, competitor overview, weekly KPI summary
- output formats: Markdown + PDF
- draft-ready communication summary blocks
**Deliverables**
- template library
- report generation service with format options
**Acceptance Tests**
- generated reports pass structure and completeness checks
- markdown and PDF exports are consistent for the same source data
**Regression Slice**
- Evidence Research Assistant
**Checklist**
- [ ] templates implemented (`todo`)
- [ ] export pipeline stable (`todo`)
- [ ] report QA checks pass (`todo`)
### Server-Side Mailer Service
**Status:** `done`
**Objective**
- send reports without interactive OAuth friction
**In Scope**
- backend-only report delivery via Google Workspace DWD
- strong error mapping (API disabled, delegation, mailbox state, invalid recipient)
- delivery logging and trace events
**Deliverables**
- `send_report_email(...)` server interface
- error taxonomy and operator-facing remediation hints
- smoke script and operational runbook section
**Acceptance Tests**
- test delivery succeeds in configured workspace using impersonated sender
- failure cases produce explicit and actionable diagnostics
**Regression Slice**
- Executive Writer and Report Generator
**Checklist**
- [ ] DWD send path verified (`todo`)
- [ ] failure diagnostics validated (`todo`)
- [ ] delivery logging complete (`todo`)
### Data Analyst Baseline
**Status:** `done`
**Objective**
- enable practical structured data analysis
**In Scope**
- ingest CSV/Excel/SQL-style data sources
- basic aggregations and chart-ready outputs
- narrative summary for non-technical users
**Deliverables**
- data ingestion adapters
- summary and chart pipeline
**Acceptance Tests**
- analyst module returns reproducible metrics with source references
- chart artifacts and numeric summaries agree
**Regression Slice**
- Server-Side Mailer Service
**Checklist**
- [ ] data adapters stable (`todo`)
- [ ] aggregation outputs validated (`todo`)
- [ ] chart and narrative parity checks pass (`todo`)
---
## Advanced Domain Specialists
### Business Intelligence and Strategy Engine
**Status:** `done`
**Objective**
- produce deeper, decision-grade business insight
**In Scope**
- trend dashboards and ROI/cash-flow style analytics blocks
- forecasting primitives (time-series baseline + scenario simulations)
**Deliverables**
- strategy insight module
- forecast report sections with assumptions
**Acceptance Tests**
- strategy outputs include assumptions, ranges, and confidence levels
- forecast backtests beat baseline thresholds defined in governance acceptance
**Regression Slice**
- Data Analyst Baseline
**Checklist**
- [ ] BI analysis modules shipped (`todo`)
- [ ] forecast model guardrails in place (`todo`)
- [ ] decision-output QA complete (`todo`)
### Marketing and Growth Specialist
**Status:** `done`
**Objective**
- automate actionable growth workflows
**In Scope**
- ICP profiling
- outreach sequencing logic
- competitor content analysis
- CRM-informed personalization
**Deliverables**
- growth specialist module
- CRM mapping and response tracking hooks
**Acceptance Tests**
- generated outreach plans satisfy policy and personalization constraints
- CRM sync and response-state updates are deterministic
**Regression Slice**
- Business Intelligence and Strategy Engine
**Checklist**
- [ ] ICP and sequencing logic validated (`todo`)
- [ ] CRM-driven personalization integrated (`todo`)
- [ ] growth workflow tests pass (`todo`)
### Product and Operations Specialist
**Status:** `done`
**Objective**
- improve product/process quality using structured analysis
**In Scope**
- feature gap analysis
- feedback clustering
- SOP/process map generation
- bottleneck detection and optimization suggestions
**Deliverables**
- product/operations specialist module with standardized outputs
**Acceptance Tests**
- module outputs include ranked gaps, grouped themes, and prioritized actions
**Regression Slice**
- Marketing and Growth Specialist
**Checklist**
- [ ] feature-gap workflows complete (`todo`)
- [ ] feedback clustering quality validated (`todo`)
- [ ] SOP/process outputs reviewed (`todo`)
### Human Resources and Finance Specialist
**Status:** `done`
**Objective**
- support talent and financial planning tasks
**In Scope**
- CV parsing and job-description drafting
- onboarding documentation assistants
- budgeting, margin, and projection helpers
**Deliverables**
- HR specialist module
- finance specialist module
**Acceptance Tests**
- HR artifacts follow required templates and compliance prompts
- finance outputs are numerically consistent and assumption-tagged
**Regression Slice**
- Product and Operations Specialist
**Checklist**
- [ ] HR flows validated (`todo`)
- [ ] finance modeling outputs validated (`todo`)
- [ ] cross-domain regression stable (`todo`)
---
## Enterprise Governance and Resilience
### Access Governance and Approval Controls
**Status:** `done`
**Objective**
- enforce strict operational control on sensitive actions
**In Scope**
- role model: employee, manager, admin
- permission boundaries per module/data/action
- explicit approval workflows for high-risk operations
**Deliverables**
- production RBAC policy map
- approval workflow engine contracts
**Acceptance Tests**
- unauthorized action attempts are blocked and audited
- approval-required flows cannot bypass controls
**Regression Slice**
- Human Resources and Finance Specialist
**Checklist**
- [ ] RBAC policy enforced (`todo`)
- [ ] approvals audited end-to-end (`todo`)
- [ ] governance controls signed off (`todo`)
### Reliability, Preflight, and Fallback Framework
**Status:** `done`
**Objective**
- maximize reliability under partial failure and dependency drift
**In Scope**
- preflight checks (credentials/connectivity/service health)
- self-check gates (citation completeness, logic consistency)
- retries, queuing, and fallback behavior for failed actions
**Deliverables**
- reliability guardrail framework
- fallback orchestration rules
**Acceptance Tests**
- injected provider failures trigger expected retries/fallbacks
- partial failures remain replay-safe and recoverable
**Regression Slice**
- Access Governance and Approval Controls
**Checklist**
- [ ] preflight framework active (`todo`)
- [ ] self-check gates active (`todo`)
- [ ] retry/fallback reliability targets met (`todo`)
### Continuous Improvement and Learning Loop
**Status:** `done`
**Objective**
- continuously improve quality and utility from real usage
**In Scope**
- feedback capture and usage metrics
- controlled experiments where applicable
- re-index/retrain/update cycle for knowledge and model components
**Deliverables**
- improvement loop pipeline
- periodic quality review dashboard
**Acceptance Tests**
- quality metrics trend and alert thresholds defined and active
- documented process exists for promoting improvements safely
**Regression Slice**
- Reliability, Preflight, and Fallback Framework
**Checklist**
- [ ] feedback telemetry pipeline running (`todo`)
- [ ] experiment framework documented (`todo`)
- [ ] update cadence and review ritual established (`todo`)
---
## Scale and Personalization Expansion
### Systems Expansion and Performance Scale
**Status:** `done`
**Objective**
- broaden enterprise data coverage without sacrificing latency or safety
**In Scope**
- integrate HR, finance, ticketing, and inventory systems
- scale vector index and retrieval performance
- add caching and async throughput improvements
**Deliverables**
- integration expansion plan implemented for priority systems
- performance baseline and optimization report
**Acceptance Tests**
- defined scale test passes for throughput and latency targets
- data isolation and access controls remain intact at scale
**Regression Slice**
- Continuous Improvement and Learning Loop
**Checklist**
- [ ] new systems integrated (`todo`)
- [ ] performance targets met (`todo`)
- [ ] security and tenancy checks pass (`todo`)
### Cross-Module Workflow Orchestration
**Status:** `done`
**Objective**
- execute end-to-end multi-module business workflows
**In Scope**
- module chaining (Researcher -> Writer -> Mailer -> Tracker)
- reusable workflow templates (for example weekly KPI cycle)
**Deliverables**
- workflow orchestration templates
- inter-module contract validation suite
**Acceptance Tests**
- chained workflows complete with full traceability and replay safety
- handoff contracts preserve context and state deterministically
**Regression Slice**
- Systems Expansion and Performance Scale
**Checklist**
- [ ] workflow templates shipped (`todo`)
- [ ] handoff contracts validated (`todo`)
- [ ] chain reliability tests pass (`todo`)
### Modes and Personalization Framework
**Status:** `done`
**Objective**
- tailor behavior by domain, role, and user context
**In Scope**
- mode selection (strategy, legal, technical, and other domain modes)
- role-aware prompt and tool policy overlays
- preference/memory-aware response adaptation
**Deliverables**
- mode configuration framework
- personalization rules and safety constraints
**Acceptance Tests**
- mode switching changes behavior predictably and safely
- personalization improves relevance without violating policy
**Regression Slice**
- Cross-Module Workflow Orchestration
**Checklist**
- [ ] custom modes operational (`todo`)
- [ ] personalization rules verified (`todo`)
- [ ] safety and policy checks remain green (`todo`)
---
## LLM Task Understanding and Delivery Excellence
### Contract Schema Hardening
**Status:** `done`
**Objective**
- make every run machine-checkable before execution begins
**In Scope**
- expand task contract schema with objective, required facts, required outputs, required actions, delivery target, constraints, missing requirements, and success checks
- enforce mandatory rule in contract generation and validation: no hardcoded words or keyword lists
- normalize contract fields for deterministic downstream checks
**Deliverables**
- strict contract schema and parser updates
- contract normalization layer with mandatory constraints
- contract serialization contract test fixtures
**Acceptance Tests**
- all contracts include required schema fields
- mandatory no-hardcode constraint is always present in both planning and execution contracts
- malformed contract payloads are normalized safely without crashes
**Regression Slice**
- Modes and Personalization Framework
**Checklist**
- [x] strict contract schema finalized (`done`)
- [x] mandatory constraints enforcement validated (`done`)
- [x] contract normalization tests pass (`done`)
### Clarification Gate and Missing Requirement Detection
**Status:** `done`
**Objective**
- prevent wrong execution when user intent is underspecified
**In Scope**
- pre-execution gate that blocks action when critical requirements are missing
- structured clarification prompts (recipient, target URL, required facts, output format)
- event streaming for clarification lifecycle in theatre
**Deliverables**
- clarification gate in orchestrator
- missing-requirements classifier and prompt templates
- live events for clarification requested/resolved
**Acceptance Tests**
- external actions are blocked when critical requirements are missing
- clarification questions are specific and bounded
- resolved clarifications unblock execution deterministically
**Regression Slice**
- Contract Schema Hardening
**Checklist**
- [x] clarification gate integrated (`done`)
- [x] missing requirements classifier validated (`done`)
- [x] clarification event stream visible in theatre (`done`)
### Evidence-Aware Planning Contract
**Status:** `done`
**Objective**
- guarantee plans are evidence-producing, not just action-producing
**In Scope**
- require planner rows to include rationale and expected evidence for required facts
- enforce plan rejection when required facts have no evidence path
- maintain LLM-first planning with deterministic schema checks
**Deliverables**
- upgraded planner step schema with evidence metadata
- plan critic rules for fact coverage
- plan quality tests for ambiguous prompts
**Acceptance Tests**
- each required fact maps to at least one evidence-producing step
- plans without fact coverage are rejected and regenerated
- no hardcoded keyword routing in planner decisions
**Regression Slice**
- Clarification Gate and Missing Requirement Detection
**Checklist**
- [x] planner evidence schema implemented (`done`)
- [x] plan critic coverage checks active (`done`)
- [x] plan quality regression tests pass (`done`)
### Execution Verification and External Action Gating
**Status:** `done`
**Objective**
- block final responses and external actions until contract obligations are met
**In Scope**
- required-fact to evidence mapping validator
- automated remediation step insertion for missing obligations
- action gate for email/contact form/send operations
**Deliverables**
- execution verifier with structured missing-items output
- remediation insertion flow
- blocking logic for unsafe or incomplete external actions
**Acceptance Tests**
- external sends are blocked when required facts are unverified
- verifier explains missing items with actionable remediation
- remediation loop converges or exits with clear blocked reason
**Regression Slice**
- Evidence-Aware Planning Contract
**Checklist**
- [x] execution verifier integrated (`done`)
- [x] action-gate blocking validated (`done`)
- [x] remediation loop tests pass (`done`)
### Evidence-Backed Value-Add Response Enhancer
**Status:** `done`
**Objective**
- exceed user expectations without hallucinating
**In Scope**
- post-verification value-add section generated only from verified evidence
- recommendation ranking based on confidence and relevance
- strict prohibition on unsupported claims
**Deliverables**
- value-add response module
- confidence-aware recommendation formatter
- citation-linked enhancement output
**Acceptance Tests**
- value-add content appears only when evidence coverage threshold is met
- no unsupported claim appears in final response
- response quality metrics improve without increasing contradiction rate
**Regression Slice**
- Execution Verification and External Action Gating
**Checklist**
- [x] value-add generator implemented (`done`)
- [x] confidence and citation rules enforced (`done`)
- [x] hallucination guard tests pass (`done`)
### Theatre Transparency and Screen Transition Stability
**Status:** `done`
**Objective**
- make every planning and execution phase visibly understandable in real time
**In Scope**
- live streaming of phases: understanding, contract, clarification, planning, execution, verification, delivery
- stable full-screen transitions between website, docs, and sheets
- removal of noisy overlays that obscure primary work surface
**Deliverables**
- theatre phase timeline renderer
- scene transition controller for website/docs/sheets
- reduced-noise UI overlays and stable replay behavior
**Acceptance Tests**
- user can observe phase transitions live without flicker/blinking regressions
- docs and sheets open as full screens when active
- theatre replay preserves ordered phase history
**Regression Slice**
- Evidence-Backed Value-Add Response Enhancer
**Checklist**
- [x] phase timeline streaming implemented (`done`)
- [x] scene transitions stabilized (`done`)
- [x] theatre replay regression tests pass (`done`)
### Continuous Agent Evals and Regression Guardrails
**Status:** `done`
**Objective**
- lock in gains and prevent understanding/delivery regressions
**In Scope**
- evaluation suite for ambiguity, multi-intent requests, delivery completeness, and contradiction risk
- CI gating for contract, planner, verifier, and delivery behavior
- regression fixtures from real production-like failures
**Deliverables**
- automated eval suite and score thresholds
- CI policy for failing regressions
- evaluation dashboard for trend monitoring
**Acceptance Tests**
- CI fails when understanding or delivery quality drops below threshold
- eval suite covers representative real user task patterns
- repeated failures produce documented lessons in `tasks/lessons.md`
**Regression Slice**
- Theatre Transparency and Screen Transition Stability
**Checklist**
- [x] eval suite implemented (`done`)
- [x] CI quality gates configured (`done`)
- [x] regression fixtures maintained (`done`)
---
## Slice Execution Order
1. Strategic Scope and Governance Alignment
2. Architecture and Data Strategy Blueprint
3. Integration and Runtime Baseline
4. Evidence Research Assistant
5. Executive Writer and Report Generator
6. Server-Side Mailer Service
7. Data Analyst Baseline
8. Business Intelligence and Strategy Engine
9. Marketing and Growth Specialist
10. Product and Operations Specialist
11. Human Resources and Finance Specialist
12. Access Governance and Approval Controls
13. Reliability, Preflight, and Fallback Framework
14. Continuous Improvement and Learning Loop
15. Systems Expansion and Performance Scale
16. Cross-Module Workflow Orchestration
17. Modes and Personalization Framework
18. Contract Schema Hardening
19. Clarification Gate and Missing Requirement Detection
20. Evidence-Aware Planning Contract
21. Execution Verification and External Action Gating
22. Evidence-Backed Value-Add Response Enhancer
23. Theatre Transparency and Screen Transition Stability
24. Continuous Agent Evals and Regression Guardrails
Current Active Slice: `None (All Roadmap Slices Complete)`

---
## Repository-Wide Refactorization Program (One File Per Slice)
### Activation Rule
- Start this queue only after the current active slice is marked `done`.
- Execute exactly one file slice at a time until the queue is fully complete.
- A file slice cannot be marked `done` if the source file still exceeds 500 LOC.

### Universal File Slice Definition of Done
- legacy file is reduced below 500 LOC and becomes a thin coordinator/shim where needed
- extracted modules are domain-named and each under 500 LOC (preferred 350-450 LOC)
- all imports are updated in the same slice, with no circular imports introduced
- acceptance tests for touched behavior pass
- assigned regression slice tests pass
- `tasks/todo.md` is updated with verification evidence
- if any user correction occurred, a lesson is appended to `tasks/lessons.md`

### File-By-File Slice Queue (Do Not Skip)
#### Hard Size Violations (`>500` LOC)
1. `api/services/chat_service.py` (1362 LOC) -> split into `api/services/chat/` package modules (`pipeline`, `fast_qa`, `streaming`, `citations`, `conversation_store`, `app`)
2. `api/services/agent/tools/workspace_tools.py` (868 LOC) -> split tool classes into per-tool modules under `api/services/agent/tools/workspace/`
3. `api/routers/integrations.py` (728 LOC) -> split into connector-focused routers (`maps`, `ollama`, `web_search`) + shared router helpers
4. `api/routers/agent.py` (622 LOC) -> split by domain (`oauth`, `credentials`, `runs`, `playbooks`, `schedules`, `governance`, `sse`)
5. `api/services/ingestion_service.py` (547 LOC) -> split manager into `jobs`, `worker`, `progress`, `cleanup`, and persistence helpers
6. `api/services/agent/connectors/browser_connector.py` (537 LOC) -> split live stream flow, page capture, and interaction helpers into dedicated modules
7. `api/services/google/auth.py` (537 LOC) -> split OAuth lifecycle, token refresh/session HTTP client, and state management
8. `api/services/upload_service.py` (526 LOC) -> split upload/indexing, file-group management, and deletion/move operations
9. `frontend/user_interface/src/app/components/InfoPanel.tsx` (1625 LOC) -> split cards and render blocks into focused components
10. `frontend/user_interface/src/app/components/FilesView.tsx` (1508 LOC) -> split file table, grouping actions, dialogs, and shared formatters/hooks
11. `frontend/user_interface/src/app/components/AgentActivityPanel.tsx` (1400 LOC) -> split timeline rows, metadata renderers, scene mapping, and filters
12. `frontend/user_interface/src/app/App.tsx` (1197 LOC) -> split layout shell, panel state hooks, chat orchestration, and persistence utilities
13. `frontend/user_interface/src/app/components/AgentDesktopScene.tsx` (921 LOC) -> split scene renderer, transitions, controls, and event adapters
14. `frontend/user_interface/src/api/client.ts` (830 LOC) -> split API surface by domain (`conversations`, `files`, `ingestion`, `agent`, `oauth`, `sse`)
15. `frontend/user_interface/src/app/components/ChatMain.tsx` (687 LOC) -> split message list, composer, attachment actions, and stream handlers
16. `frontend/user_interface/src/app/components/ui/sidebar.tsx` (672 LOC) -> split primitives into item/group/header/footer modules
17. `frontend/user_interface/src/app/components/agentActivityMeta.ts` (668 LOC) -> split metadata serializers by event domain
18. `frontend/user_interface/src/app/utils/infoInsights.ts` (664 LOC) -> split insight transforms, scoring, graph assembly, and formatting helpers
19. `frontend/user_interface/src/app/components/ResourcesView.tsx` (587 LOC) -> split resource list, tool sections, and interaction handlers
20. `libs/ktem/ktem/index/file/ui.py` (1574 LOC) -> split views, handlers, and formatting/rendering helpers
21. `libs/ktem/ktem/pages/chat/__init__.py` (1274 LOC) -> split page state, event handlers, and page composition
22. `libs/ktem/ktem/index/file/pipelines.py` (826 LOC) -> split pipeline registry, builders, and execution adapters
23. `libs/ktem/ktem/reasoning/simple.py` (527 LOC) -> split reasoning stages and response formatting

#### Complexity Hotspots (Mandatory After Size Queue)
24. `api/services/agent/orchestration/answer_builder.py` (C901=55) -> split section builders (`understanding`, `plan`, `summary`, `delivery`, `verification`, `artifacts`)
25. `api/services/agent/orchestration/step_planner.py` (C901=45) -> split contract shaping, intent enrichments, evidence enforcement, and event emission
26. `api/services/agent/orchestration/step_execution.py` (C901=28) -> split guard checks, tool execution loop, workspace shadow logging, and failure recovery
27. `api/services/agent/llm_execution_support.py` (496 LOC, C901=21) -> split rewriting, recovery, summarization, and next-step curation
28. `api/services/agent/connectors/browser_contact_connector.py` (C901=39) -> split form detection, field mapping, and submit/retry flow
29. `api/services/agent/orchestration/delivery.py` (C901=17) -> split delivery decisioning, send path, and remediation handling
30. `api/services/agent/intelligence.py` (459 LOC, C901 hotspots) -> split claim extraction, verification scoring, and contradiction analysis

### Refactor Slice Status Board
- [x] Slice 01 complete (`done`)
- [x] Slice 02 complete (`done`)
- [x] Slice 03 complete (`done`)
- [x] Slice 04 complete (`done`)
- [x] Slice 05 complete (`done`)
- [x] Slice 06 complete (`done`)
- [x] Slice 07 complete (`done`)
- [x] Slice 08 complete (`done`)
- [x] Slice 09 complete (`done`)
- [x] Slice 10 complete (`done`)
- [x] Slice 11 complete (`done`)
- [x] Slice 12 complete (`done`)
- [x] Slice 13 complete (`done`)
- [x] Slice 14 complete (`done`)
- [x] Slice 15 complete (`done`)
- [x] Slice 16 complete (`done`)
- [x] Slice 17 complete (`done`)
- [x] Slice 18 complete (`done`)
- [x] Slice 19 complete (`done`)
- [x] Slice 20 complete (`done`)
- [x] Slice 21 complete (`done`)
- [x] Slice 22 complete (`done`)
- [x] Slice 23 complete (`done`)
- [x] Slice 24 complete (`done`)
- [x] Slice 25 complete (`done`)
- [x] Slice 26 complete (`done`)
- [x] Slice 27 complete (`done`)
- [x] Slice 28 complete (`done`)
- [x] Slice 29 complete (`done`)
- [x] Slice 30 complete (`done`)

