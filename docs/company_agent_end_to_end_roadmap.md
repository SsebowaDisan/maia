# Maia Company Agent End-to-End Roadmap

This roadmap defines the full implementation plan for a **Company Agent** in Maia that can execute cross-functional work across:
- Marketing research and competitive intelligence
- Google Ads and performance analysis
- Email drafting/sending workflows
- Data analysis and reporting
- Invoice drafting, generation, and sending
- Workplace integrations (Slack, Google Workspace, Microsoft 365)

The roadmap is structured phase-by-phase with strict gates.

Status legend:
- `[ ]` Not started
- `[~]` In progress
- `[x]` Completed

---

## 0. Baseline Analysis (Current State)
Status: `[x]`

Current architecture already provides:
- FastAPI backend (`api/`) with chat, uploads, settings routes.
- React frontend (`frontend/user_interface`) with Chat, Files, Resources, Settings, Help.
- Chat retrieval + reasoning pipeline via `ktem` integrations.
- File indexing pipeline + citations + info panel workflows.

Gaps to close for a full Company Agent:
- No dedicated agent mode in chat request contract.
- No unified tool orchestration layer (research/email/ads/data/reporting).
- No execution access mode model (restricted vs full access) for sensitive actions.
- No workflow memory model for task plans and recurring reports.
- No connector framework for external APIs (Slack, Google Ads, Docs/Sheets, Excel/OneDrive).

---

## API Add-on Catalog (Must Include)
Status: `[x]`

Required integrations:
- Slack API
  - Read channels/threads (with permissions)
  - Post messages/replies
  - Send alerts from reports
- Google Ads API
  - Campaign/ad-group/keyword metrics
  - Budget and performance analysis
- Google Workspace APIs
  - Google Docs API (read/write report drafts)
  - Google Sheets API (tabular data read/write)
  - Google Drive API (file discovery and export storage)
- Microsoft 365 APIs
  - Excel (Graph API) for workbook/sheet data
  - OneDrive/SharePoint for file access
  - Outlook mail/calendar (optional after core release)
- Invoice and accounting APIs
  - QuickBooks / Xero (priority based on customer stack)
  - Optional ERP invoice modules (NetSuite/Odoo/SAP) in later phase

Optional next-wave connectors:
- HubSpot / Salesforce
- Meta Ads
- Notion / Confluence

---

## API Add-on Priority Order
Status: `[x]`

1. Slack (read/post) + Google Ads (read)
2. Google Sheets + Google Docs + Google Drive
3. Excel + OneDrive/SharePoint
4. Outlook send/draft flow
5. Invoice/accounting connector (QuickBooks/Xero)
6. CRM and additional ad platforms

---

## Execution Access Modes
Status: `[x]`

Supported modes:
- `Restricted`:
  - Confirm-before-execute for configured action classes.
  - Suitable for normal users and gradual rollout.
- `Full Access`:
  - Auto-execute enabled for allowed tools.
  - No per-action approval prompts.
  - Intended for trusted users/workspaces that explicitly enable it.

Common requirements in both modes:
- RBAC and tenant isolation are always enforced.
- Every action is auditable.
- Per-tool kill switch and global emergency stop remain available.

---

## 1. Product Definition and Guardrails
Status: `[x]`

Goal:
- Define exactly what "company agent" can do in v1, v2, v3.

Scope:
- Capability matrix by domain:
  - Marketing research
  - Ads analysis
  - Email operations
  - Data analysis
  - Reporting
  - Invoice operations
- Define user roles and permission tiers.
- Define action classes:
  - Read-only
  - Draft
  - Execute
- Define execution access modes:
  - Restricted mode (confirm-before-execute)
  - Full Access mode (auto-execute, no approval prompts)

Acceptance criteria:
- Approved capability matrix.
- Approved permission model.
- Approved access mode policy and escalation policy.

---

## 2. UX Entry Point (Primary Access in Composer)
Status: `[x]`

Goal:
- Add ChatGPT-style primary access directly in the chat composer.

Scope:
- Add segmented control in chat composer:
  - `Ask`
  - `Company Agent`
- Keep current top navigation unchanged.
- Persist selected mode per conversation.
- Show active mode label in message metadata (for transparency).

Implementation targets:
- `frontend/user_interface/src/app/components/ChatMain.tsx`
- `frontend/user_interface/src/app/App.tsx`
- `frontend/user_interface/src/api/client.ts`
- `api/schemas.py`

Acceptance criteria:
- User can switch between Ask and Company Agent before sending.
- Mode selection is included in API payload.
- Existing Ask flow remains backward compatible.

---

## 2A. Agent Activity Replay (Live Execution View)
Status: `[x]`

Goal:
- Add a ChatGPT-agent-style activity view that shows what the agent is doing live (searching web, opening documents, applying highlights, and running tools).

Scope:
- Add real-time activity timeline with structured steps:
  - planning
  - web search query + opened result
  - document/PDF open and highlight events
  - tool actions (email, ads analysis, reporting, etc.)
- Add replay controls for completed runs:
  - play/pause
  - step scrubber
  - speed control (`1x`/`2x`)
- Persist per-run event logs for replay, audit, and debugging.
- Link each activity step to evidence/source artifacts in the information panel.

Implementation targets:
- `api/routers/chat.py` (SSE event stream contract)
- `api/services/chat_service.py` (emit activity events)
- New `api/services/agent/activity.py` (event schema + persistence)
- `frontend/user_interface/src/app/components/ChatMain.tsx`
- New `frontend/user_interface/src/app/components/AgentActivityPanel.tsx`
- `frontend/user_interface/src/api/client.ts`

Acceptance criteria:
- User can watch live agent execution steps while response is being generated.
- Completed runs can be replayed step-by-step.
- Clicking an activity step opens the corresponding source and highlight.
- Activity logs are saved and available in run history.

---

## 3. Agent API Contract and Orchestrator
Status: `[x]`

Goal:
- Introduce a formal backend execution layer for company tasks.

Scope:
- Add `agent_mode` and `agent_goal` fields in chat request schema.
- Add orchestrator service:
  - Plan step generation
  - Tool selection
  - Tool execution
  - Result synthesis
- Add structured result format:
  - `answer`
  - `actions_taken`
  - `sources_used`
  - `next_recommended_steps`

Implementation targets:
- `api/schemas.py`
- `api/routers/chat.py`
- `api/services/chat_service.py`
- New files under `api/services/agent/`

Acceptance criteria:
- Orchestrator can run at least one tool and return structured output.
- Fallback to current chat path when `agent_mode` disabled.

---

## 4. Tool Registry and Execution Framework
Status: `[x]`

Goal:
- Create a secure, extensible tool framework for company operations.

Scope:
- Tool registry with metadata:
  - `tool_id`
  - `risk_level`
  - `required_permissions`
  - `execution_policy` (`auto_execute` or `confirm_before_execute`)
- Common tool runtime:
  - Timeout policy
  - Retries
  - Error normalization
  - Audit logging
- Add dry-run mode for execution tools.

Implementation targets:
- New `api/services/agent/tools/registry.py`
- New `api/services/agent/tools/base.py`
- New `api/services/agent/audit.py`

Acceptance criteria:
- Tools can be discovered and executed through one interface.
- Tools must honor selected access mode and execution policy at runtime.

---

## 4A. External API Connector Layer
Status: `[x]`

Goal:
- Implement reusable, secure connector modules for API add-ons.

Scope:
- Connector SDK abstraction:
  - auth provider
  - token refresh
  - rate-limit handling
  - standardized request/response envelope
- Per-provider connector modules:
  - `slack_connector`
  - `google_ads_connector`
  - `google_docs_connector`
  - `google_sheets_connector`
  - `google_drive_connector`
  - `m365_excel_connector`
  - `m365_files_connector` (OneDrive/SharePoint)
- Secret and credential mapping per workspace/user.
- Provider-specific retry/backoff policies.

Implementation targets:
- New `api/services/agent/connectors/` package
- New `api/services/agent/auth/` package
- `api/services/settings_service.py` extensions for connector configs

Acceptance criteria:
- Connector health checks pass for enabled providers.
- Tokens refresh automatically without user interruption.
- Connector errors normalized for agent orchestration.

---

## 5. Marketing Research Agent Tools
Status: `[x]`

Goal:
- Enable robust online research for marketing use cases.

Scope:
- Web search tool adapter with source attribution.
- Page extraction/summarization pipeline.
- Slack trend ingestion (public/internal approved channels) for campaign signals.
- Competitor profile builder:
  - Messaging
  - Pricing signals
  - Positioning gaps
- Research report output templates.

Acceptance criteria:
- Research responses include:
  - Summary
  - Evidence links
  - Confidence notes
- Sources are traceable in info panel.

---

## 6. Email Agent Tools
Status: `[x]`

Goal:
- Draft and send company emails safely.

Scope:
- Email draft generator from prompts + context.
- Integrate SMTP/API provider (configurable).
- Add execution policy support:
  - Restricted mode: confirm-before-send
  - Full Access mode: direct send (no approval prompt)
  - Optional draft-only enforcement by workspace policy
- Add delivery result capture and error reporting.

Acceptance criteria:
- User can generate and edit drafts.
- Sending behavior follows selected execution mode and logs full audit trail.

---

## 6A. Invoice Agent Tools
Status: `[x]`

Goal:
- Enable end-to-end invoice writing and sending from the agent.

Scope:
- Invoice drafting:
  - Client selection
  - Line items, quantity, unit price, taxes, discounts
  - Due date, payment terms, currency
- Validation:
  - Required fields and totals check
  - Tax and rounding consistency checks
- Document generation:
  - Professional PDF invoice output
  - Optional branded templates by company/project
- Sending:
  - Email delivery with PDF attachment
  - Accounting API send/post (QuickBooks/Xero) when enabled
- Tracking:
  - Invoice status (`draft`, `sent`, `paid`, `overdue`)
  - Delivery and postback logs

Acceptance criteria:
- Agent can generate a valid invoice PDF from prompt + structured data.
- User can send invoice directly in Full Access mode.
- All invoice actions are auditable with recipient, amount, currency, and timestamp.

---

## 7. Google Ads / Performance Analysis Tools
Status: `[x]`

Goal:
- Analyze ad performance and recommend optimizations.

Scope:
- Google Ads API connector (OAuth + secure token storage).
- KPI analyzer:
  - CTR, CPC, CPA, ROAS
  - Campaign/ad-group breakdowns
- Cross-source reconciliation:
  - Google Ads metrics + Sheet/Excel budget trackers
  - Optional Slack campaign feedback snapshots
- Insight generator:
  - Budget reallocation suggestions
  - Underperforming keyword/ad detection
  - Creative testing recommendations

Acceptance criteria:
- Agent can answer campaign health queries with numeric evidence.
- Outputs include recommendations + rationale.

---

## 8. Data Analysis Tools (Internal Data + Files)
Status: `[x]`

Goal:
- Let the agent analyze company datasets and indexed docs together.

Scope:
- Connectors:
  - CSV/Excel from Files
  - Google Sheets
  - Google Docs tables/structured exports
  - OneDrive/SharePoint files
  - Optional DB connectors (Postgres/MySQL/BigQuery)
- Safe query runner with row/compute limits.
- Auto-generated analysis blocks:
  - Trends
  - Segments
  - Anomalies
  - Forecast hints

Acceptance criteria:
- Agent returns reproducible analysis with cited source/data references.
- Queries are sandboxed and bounded by limits.

---

## 9. Reporting Engine (One-off + Scheduled)
Status: `[x]`

Goal:
- Deliver clear company reporting outputs from agent workflows.

Scope:
- Report templates:
  - Weekly marketing
  - Ads performance
  - Sales funnel
  - Executive summary
  - Accounts receivable and invoice aging
- Export formats:
  - Markdown
  - PDF
  - Email summary
  - Google Docs publish
  - Google Sheets append/update
  - Excel workbook export/update
  - Slack message digest
  - Invoice summary bundle (PDF + sheet row + sent status)
- Scheduling:
  - Daily/weekly/monthly
  - Recipients + execution profile (restricted or full access)

Acceptance criteria:
- Agent can generate and schedule reports from configured templates.
- All scheduled runs produce logs and retry behavior.

---

## 10. Memory, Task History, and Reuse
Status: `[x]`

Goal:
- Make agent work persistent and reusable.

Scope:
- Store agent runs:
  - Prompt
  - Plan
  - Tool calls
  - Outputs
- Saved playbooks:
  - "Analyze this month's ads"
  - "Send weekly leadership summary"
  - "Create and send monthly client invoices"
- Clone/edit/re-run flows.

Acceptance criteria:
- Any prior agent run can be inspected and rerun.
- Playbooks can be versioned and reused.

---

## 11. Security, Compliance, and Governance
Status: `[x]`

Goal:
- Enforce enterprise-grade controls.

Scope:
- Secrets management:
  - No hardcoded keys
  - Environment + secret vault support
- RBAC for tool access.
- PII and sensitive data handling policy.
- Audit logs for all execute actions.
- Data retention and deletion policies.

Acceptance criteria:
- Sensitive actions are permission-gated and auditable.
- Security review sign-off before production release.

---

## 12. Quality, Testing, and Reliability
Status: `[x]`

Goal:
- Ensure predictable behavior before launch.

Scope:
- Unit tests:
  - Orchestrator
  - Tool registry
  - Tool adapters
- Integration tests:
  - Chat mode -> agent execution -> response
  - Restricted-mode and full-access execution paths
- Load tests for multi-step workflows.
- Failure injection tests (timeouts/rate limits/provider outages).

Acceptance criteria:
- Critical test suites pass in CI.
- Defined SLOs met for success rate and latency.

---

## 13. Rollout Plan
Status: `[x]`

Goal:
- Deploy safely with staged adoption.

Scope:
- Stage 1: Internal alpha (read-only tools only)
- Stage 2: Beta (draft + controlled execute tools in restricted mode)
- Stage 3: Production (full toolset with opt-in full access per workspace/user)
- Feature flags for each tool domain.

Acceptance criteria:
- Clear rollback path exists.
- Production launch checklist completed.

---

## 14. Operational Playbook
Status: `[x]`

Goal:
- Keep the system maintainable after launch.

Scope:
- Runbooks for:
  - Provider outage
  - Token expiry
  - Email failure
  - Ads API quota limits
  - Invoice send failure / bounce
  - Accounting API sync conflicts
  - Slack API rate limits
  - Google Workspace permission drift
  - Microsoft Graph throttling/permission drift
- Monitoring dashboards:
  - Tool success/failure
  - Latency
  - Cost per run
- Monthly review loop for prompt/tool quality.

Acceptance criteria:
- On-call can diagnose top incident classes using runbooks.
- Ops metrics are visible and alerting is active.

---

## Rules We Follow (Non-Negotiable)

1. Phase gate rule:
- We do not start the next phase until current phase acceptance criteria are verified.

2. Safety-before-automation rule:
- Execution policy is controlled by access mode. In Full Access mode, actions can auto-execute without approval prompts.

3. Source-traceability rule:
- Any analytical/research conclusion must include attributable evidence and source links.

4. Least-privilege rule:
- Tools only receive minimum permissions required for their task.

5. Secrets and data rule:
- No API keys in code or logs; sensitive data is redacted where required.

6. Reproducibility rule:
- Agent outputs must include enough context to rerun and validate results.

7. Backward-compatibility rule:
- Existing Ask chat behavior must continue to work during all agent rollouts.

8. Observability rule:
- Every agent run must emit structured logs for plan, tool calls, and outcomes.

9. Access-mode rule:
- Users/workspaces can run Restricted mode or Full Access mode. Full Access disables per-action approvals.

10. Quality gate rule:
- No production release without passing functional, security, and reliability checks.

11. Connector-contract rule:
- Every external integration must implement the shared connector interface and error schema.

12. Write-action policy rule:
- Write actions to Slack, Docs, Sheets, Excel, and email follow the selected execution mode (Restricted or Full Access).

13. Tenant-isolation rule:
- Workspace tokens/data are isolated per tenant and never cross-accessed.

14. Full-access enablement rule:
- Full Access must be explicitly enabled by authorized users and can be revoked instantly.

15. Experience quality gate rule:
- No feature is considered done if it feels basic. Every release must meet the Wow Standard below.

---

## Wow Standard (Release Quality Bar)

Every user-facing agent feature must pass all checks:

1. Clarity in 3 seconds:
- A first-time user must understand what to do next within 3 seconds (no training needed).

2. One-action outcomes:
- Core tasks (research, analyze ads, draft report, send updates) must be reachable in 1-2 actions from composer.

3. Progressive depth, low noise:
- UI stays calm by default; advanced controls appear only when relevant.

4. Proactive intelligence:
- The agent should not only answer; it should propose next best actions with rationale and expected impact.

5. Trust by design:
- Every important output includes sources, assumptions, and confidence signals.

6. Fast perceived performance:
- Provide immediate feedback states (planning, running tools, completed) with no dead UI moments.

7. Executive-grade output:
- Responses must be structured, concise, and ready to share (summary, evidence, action plan, owner, timeline).

Release gate:
- If any checklist item fails in internal review, the feature returns to iteration before release.

---

## Execution Workflow (How We Build)

1. Freeze requirements for current phase.
2. Implement backend contract changes.
3. Implement frontend UX and mode wiring.
4. Add tests for new behavior.
5. Verify acceptance criteria with reproducible checks.
6. Document operational behavior and fallback paths.
7. Mark phase completed and move forward.

---

## Immediate Next Step

Current focus after implementation:
- **Production hardening and connector credential onboarding per tenant**  
  (configure provider tokens, validate governance policies, and run staged rollout checks).
