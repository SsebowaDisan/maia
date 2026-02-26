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
Current Active Slice: `none`

