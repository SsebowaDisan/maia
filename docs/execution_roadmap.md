# Maia Agent OS Frontend Execution Roadmap

## Principles
1. One phase completes before the next begins.
2. Each slice must ship with a concrete acceptance check.
3. No slice exceeds 500 LOC of net new complexity.
4. Every slice is end-to-end functional before moving on.
5. Extend existing Maia architecture; do not replace core surfaces wholesale.
6. Connectors remain first-class in UX, not hidden behind secondary flows.
7. Keep visual language clean and consistent across all new pages.
8. Avoid hardcoded business semantics where dynamic data is available.

## Scope
- Frontend tasks only.
- Backend work is treated as prerequisite/completed input for this roadmap.

## Status Legend
- `todo` not started
- `in_progress` active
- `done` completed and validated
- `blocked` waiting on prerequisite

## Execution Status
- Current phase: `Phase 6`
- Current slice: `Completed`
- Overall progress: `32/32 slices done`

---

## Phase 0 - Foundation Cleanup (Frontend)
Goal: Stabilize rendering and navigation foundation for upcoming Agent OS surfaces.

1. **F0-01 - Inline math rendering hardening**
   - status: `done`
   - files: `src/app/utils/richText.ts`, `src/app/components/messages/BlockRenderer.tsx`
   - scope: robust `$...$` and `$$...$$` rendering with currency-safe handling.
   - acceptance: `$F = ma$` renders as KaTeX, `$5.00` stays plain text.

2. **F0-02 - Route scaffolding for new product areas**
   - status: `done`
   - files: `src/app/App.tsx` or router module
   - scope: add routes for `/marketplace`, `/workspace`, `/agents/:agentId`, `/connectors`, `/developer`.
   - acceptance: all routes resolve without 404 and mount placeholder shells.

3. **F0-03 - Design token audit baseline**
   - status: `done`
   - files: `src/styles/index.css`
   - scope: normalize spacing/color/typography token usage for new surfaces.
   - acceptance: no new magic-number styling in this phase.

Phase 0 completion notes:
- F0-01 validated via existing math tests/build (`renderMathInMarkdown` + markdown path integration).
- F0-02 implemented path shells for `/marketplace`, `/workspace`, `/agents/:agentId`, `/connectors`, `/developer`.
- F0-03 added token baseline at `src/styles/tokens.css` and audit doc at `docs/frontend_design_tokens_audit.md`.

---

## Phase 1 - Connector Infrastructure UX
Goal: Ship connector connection, status, and permission management surfaces.

1. **F1-01 - Connectors page scaffold**
   - status: `done`
   - file: `src/app/pages/ConnectorsPage.tsx`
   - scope: connector catalog grid with status badges.
   - acceptance: all connector definitions render with accurate status.
   - completion note: `/connectors` now renders a live connector grid with status/auth/action badges and refresh.

2. **F1-02 - Connector detail slide-over**
   - status: `done`
   - file: `src/app/components/connectors/ConnectorDetailPanel.tsx`
   - scope: auth-specific connect flows, test, revoke, timestamps.
   - acceptance: OAuth/API-key connectors transition to Connected state without full reload.

3. **F1-03 - OAuth popup utility**
   - status: `done`
   - file: `src/app/utils/oauthPopup.ts`
   - scope: centered popup + `postMessage` handshake + lifecycle handling.
   - acceptance: successful OAuth resolves promise and auto-closes popup.

4. **F1-04 - Workspace connector sidebar**
   - status: `done`
   - file: `src/app/components/workspace/WorkspaceSidebar.tsx`
   - scope: live connector status rail + quick config access + active-agent count.
   - acceptance: status dots refresh after connector changes.

5. **F1-05 - Tool permission matrix**
   - status: `done`
   - file: `src/app/components/connectors/ToolPermissionMatrix.tsx`
   - scope: agents x connectors permission toggles with PATCH wiring.
   - acceptance: revoking access removes restricted tools from agent tool selection.

---

## Phase 2 - Agent Runtime UX
Goal: Build complete agent creation, gating, history, and memory exploration surfaces.

1. **F2-01 - Agent builder page**
   - status: `done`
   - file: `src/app/pages/AgentBuilderPage.tsx`
   - scope: visual builder + YAML mode with two-way sync.
   - acceptance: visual config and YAML remain semantically equivalent.

2. **F2-02 - System prompt editor**
   - status: `done`
   - file: `src/app/components/agentBuilder/SystemPromptEditor.tsx`
   - scope: variable autocomplete, highlighting, token estimate.
   - acceptance: typing `{{` opens variable suggestions and token count updates live.

3. **F2-03 - Tool selector**
   - status: `done`
   - file: `src/app/components/agentBuilder/ToolSelector.tsx`
   - scope: grouped tool selection by connector with disabled-until-connected behavior.
   - acceptance: connected tools selectable, unconnected tools blocked with guidance.

4. **F2-04 - Gate configuration UI**
   - status: `done`
   - file: `src/app/components/agentBuilder/GateConfig.tsx`
   - scope: per-tool approval toggles, timeout behavior, cost gate controls.
   - acceptance: gate settings serialize correctly into agent definition payload.

5. **F2-05 - Chat gate approval card**
   - status: `done`
   - file: `src/app/components/chatMain/GateApprovalCard.tsx`
   - scope: inline approve/reject UI for `gate_pending` activity events.
   - acceptance: approve resumes run stream; reject cancels with visible state update.

6. **F2-06 - Workspace dashboard**
   - status: `done`
   - file: `src/app/pages/WorkspacePage.tsx`
   - scope: installed agents grid with run/edit/pause/delete actions.
   - acceptance: manual run action starts run and links to output.

7. **F2-07 - Agent run history panel**
   - status: `done`
   - file: `src/app/components/agents/AgentRunHistory.tsx`
   - scope: paged historical runs + theatre replay entry.
   - acceptance: selecting a history row loads accurate historical replay.

8. **F2-08 - Memory explorer**
   - status: `done`
   - file: `src/app/components/agents/MemoryExplorer.tsx`
   - scope: Episodes, Knowledge, Working tabs with read-only visibility and delete action.
   - acceptance: memory views reflect recent runs and recall responses.

---

## Phase 3 - Marketplace UX
Goal: Enable discovery, install, updates, and publisher workflows for agents.

1. **F3-01 - Marketplace discovery page**
   - status: `done`
   - file: `src/app/pages/MarketplacePage.tsx`
   - scope: searchable/filterable listing with install state.
   - acceptance: combined filters + debounced search return expected results.

2. **F3-02 - Marketplace agent detail page**
   - status: `done`
   - file: `src/app/pages/MarketplaceAgentDetailPage.tsx`
   - scope: hero, details, required connectors, changelog, reviews.
   - acceptance: connector availability shows correctly for current tenant.

3. **F3-03 - Agent install modal**
   - status: `done`
   - file: `src/app/components/marketplace/AgentInstallModal.tsx`
   - scope: multi-step install including connector mapping and inline connect.
   - acceptance: missing connector flow can be completed inside modal.

4. **F3-04 - Developer portal page**
   - status: `done`
   - file: `src/app/pages/DeveloperPortalPage.tsx`
   - scope: publisher inventory, analytics, reviews, publish/update entry.
   - acceptance: publisher can submit a new version and view outcome state.

5. **F3-05 - Composer @agent picker**
   - status: `done`
   - file: `src/app/components/chatMain/composer/ComposerAgentPicker.tsx`
   - scope: keyboard-first fuzzy picker for installed agents + marketplace entry point.
   - acceptance: `@` opens picker, keyboard navigation selects an agent tag.

6. **F3-06 - Update notification banner**
   - status: `done`
   - file: `src/app/components/workspace/UpdateBanner.tsx`
   - scope: update availability banner + review/update slide-over.
   - acceptance: banner lifecycle respects dismiss/update actions per version.

---

## Phase 4 - Advanced Connector Ecosystem UX
Goal: Add connector marketplace discovery, SDK docs, and webhook operations UI.

1. **F4-01 - Connector marketplace page**
   - status: `done`
   - file: `src/app/pages/ConnectorMarketplacePage.tsx`
   - scope: connector catalog by category with install flow entry.
   - acceptance: installed connector appears immediately in available connector list.

2. **F4-02 - Connector SDK docs page**
   - status: `done`
   - file: `src/app/pages/DeveloperDocsPage.tsx`
   - scope: markdown docs with code examples, copy actions, sandbox links.
   - acceptance: docs render correctly and sandbox link opens.

3. **F4-03 - Webhook manager**
   - status: `done`
   - file: `src/app/components/connectors/WebhookManager.tsx`
   - scope: list/register/delete webhook endpoints per connector.
   - acceptance: newly registered webhook appears with live metadata.

---

## Phase 5 - Observability and Operations UX
Goal: Expose reliability, cost, and error operations to tenant admins.

1. **F5-01 - Operations dashboard page**
   - status: `done`
   - file: `src/app/pages/OperationsDashboardPage.tsx`
   - scope: KPI cards, trends, cost/error charts, health table.
   - acceptance: values align with telemetry API aggregates.

2. **F5-02 - Live run monitor**
   - status: `done`
   - file: `src/app/components/observability/LiveRunMonitor.tsx`
   - scope: near-real-time active run stream with theatre deep-link.
   - acceptance: started runs appear within 5s and clear on completion.

3. **F5-03 - Budget settings UI**
   - status: `done`
   - file: `src/app/components/workspace/BudgetSettings.tsx`
   - scope: daily limits, alert threshold, billing history, progress state.
   - acceptance: budget threshold behavior matches backend limit enforcement.

4. **F5-04 - Error log and replay**
   - status: `done`
   - file: `src/app/components/observability/RunErrorLog.tsx`
   - scope: filterable errors + theatre link + replay action.
   - acceptance: failed run opens accurate theatre trace and replay triggers new run.

---

## Phase 6 - Agent Composition UX
Goal: Enable workflow construction and multi-agent operation visibility.

1. **F6-01 - Workflow builder page**
   - status: `done`
   - file: `src/app/pages/WorkflowBuilderPage.tsx`
   - scope: visual DAG builder with edge conditions and run action.
   - acceptance: two-step workflow can be built and executed from canvas.

2. **F6-02 - Multi-agent theatre**
   - status: `done`
   - file: `src/app/components/agentActivityPanel/MultiAgentTheatre.tsx`
   - scope: side-by-side activity columns with delegation cues and gate pauses.
   - acceptance: three-step workflow shows synchronized multi-column runtime.

3. **F6-03 - Improvement suggestion UI**
   - status: `done`
   - file: `src/app/components/agents/ImprovementSuggestion.tsx`
   - scope: prompt-diff review card with apply/dismiss actions.
   - acceptance: applying suggestion updates agent definition for next run.

---

## Dependency Order
1. Phase 0
2. Phase 1
3. Phase 2
4. Phase 3
5. Phase 4
6. Phase 5
7. Phase 6

## Exit Criteria
1. All 32 frontend slices are marked `done` with acceptance evidence.
2. No unresolved UX blockers remain for connector, agent, marketplace, observability, or workflow surfaces.
3. Cross-surface navigation and state are consistent across all new routes.
