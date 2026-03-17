# Maia Frontend Execution Roadmap
Updated: 2026-03-17  
Scope: Marketplace install UX and connector readiness flows

## Analysis Summary
1. The install flow can skip modal friction when preflight confirms immediate install.
2. Post-install state should be updated from install response payloads to remove redundant list refetches.
3. Connector readiness needs to be visible earlier (cards/detail) and clearer at confirmation time.
4. Installed/version state should drive `Installed` vs `Update` calls-to-action directly from preflight/install responses.
5. Audit/debug and workflow validation UX should expose connector-related history/warnings without hard-blocking save.

## Active Tasks

### P0 - Critical (pairs with B0/B3)

#### F1 - One-click install button driven by preflight
- Description: On marketplace detail page, call `POST /api/marketplace/agents/{id}/install/preflight` on load. If `can_install_immediately: true`, show one-click `Install` (direct install call, no modal). If false, keep modal flow for connector setup.
- Files:
  - `src/app/pages/MarketplaceAgentDetailPage.tsx`
  - `src/app/components/marketplace/AgentInstallModal.tsx`

#### F2 - Update local agent state from install response (no refetch)
- Description: Use `installed_agent` returned from install success to merge directly into agent list store instead of calling `GET /api/agents` again.
- Files:
  - `src/app/api/client/marketplace.ts`
  - `src/app/components/marketplace/AgentInstallModal.tsx`

#### F3 - Show auto-mapped connectors in confirmation UI
- Description: If install response includes `auto_mapped_connectors`, render inline "Connected automatically" chips under the success message (example: `brave_search -> tenant_brave_01`).
- Files:
  - `src/app/components/marketplace/AgentInstallModal.tsx`

### P1 - High Value (pairs with B1/B6)

#### F4 - Connector status pills on marketplace cards and detail page
- Description: Use `connector_status` from `GET /api/marketplace/agents` to show status pills per required connector:
  - `Connected` (green)
  - `Missing` (amber)
  - `Not required` (grey)
- List page shows compact summary; detail page shows full per-connector breakdown.
- Files:
  - `src/app/pages/MarketplacePage.tsx`
  - `src/app/pages/MarketplaceAgentDetailPage.tsx`
  - `src/app/components/marketplace/ConnectorStatusPill.tsx` (new)

#### F5 - Collapse install modal to a single connector-setup sheet
- Description: When `can_install_immediately: false` and exactly one item in `missing_connectors`, skip wizard and show inline sheet (`This agent needs <connector> -> Connect`). On OAuth success, auto-install. Keep 4-step wizard for 2+ missing connectors or explicit `Customise`.
- Files:
  - `src/app/components/marketplace/AgentInstallModal.tsx`

#### F6 - Already-installed badge and update flow
- Description: If `already_installed: true` from preflight/install, replace `Install` call-to-action with an `Installed` badge. If marketplace version is newer than installed version, show `Update available` and re-use install endpoint for upgrade/upsert flow.
- Files:
  - `src/app/pages/MarketplaceAgentDetailPage.tsx`
  - `src/app/api/client/marketplace.ts`

### P2 - Polish (pairs with B8)

#### F7 - Install history drawer on AgentDetailPage
- Description: Add a `History` tab on Agent detail that calls `GET /api/agents/{id}/install-history` and renders timeline entries for timestamp, installed version, user, and mapped connectors.
- Files:
  - `src/app/pages/AgentDetailPage.tsx`
  - `src/app/components/agents/InstallHistoryTab.tsx` (new)

#### F8 - Workflow canvas connector warning indicators
- Description: When `POST /api/workflows/validate` warnings mention missing connectors, highlight affected nodes with an amber border and tooltip (`Missing connector: <name> - configure in Settings`). Warning-only behavior: saving is still allowed.
- Files:
  - `src/app/components/workflowCanvas/WorkflowNode.tsx`
  - `src/app/components/workflowCanvas/WorkflowCanvas.tsx`

## Suggested Implementation Order
1. F1 -> F2 -> F3
2. F4 -> F5 -> F6
3. F7 -> F8

## Completion Criteria
1. Immediate-install agents can be installed from detail page with one click and no modal.
2. Post-install UI state updates without `GET /api/agents` refetch.
3. Auto-mapped connectors appear in success confirmation.
4. Connector readiness is visible on marketplace cards and detail page.
5. Installed vs Update controls render correctly from response data.
6. Agent detail exposes an install history timeline.
7. Workflow validation warnings visually mark affected nodes while preserving save behavior.
