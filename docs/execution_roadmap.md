# Maia Execution Roadmap

Updated: 2026-03-16

## Rules
1. Frontend-only execution in this slice. No backend modifications.
2. Strict order: hard blockers first, then high-value UX gaps, then enhancements.
3. Each task must be wired end-to-end with visible UI behavior before moving on.
4. Keep changes incremental and production-safe.

---

## Scope
Close remaining **Marketplace + Agent Platform frontend gaps** now that backend APIs are available.

---

## Phase Status Summary

| Phase | Description | Status |
|---|---|---|
| MP-F0 | Hard blockers (Page Monitor, connector definitions, auth-none UX, detail mount) | done |
| MP-F1 | High-value UX (schedule at install, tags/connectors detail polish, health warnings, post-install gate editing) | in_progress |
| MP-F2 | Enhancements (widget expansions + connector marketplace sanity check) | pending |

---

## Frontend Tasks

| ID | Task | Status | Frontend target |
|---|---|---|---|
| F-MP-01 | Add Page Monitor API client (`list/add/remove/refresh`) | done | `src/api/client/pageMonitor.ts`, `src/api/client.ts` |
| F-MP-02 | Build `PageMonitorPanel` UI with add/remove/check-now + change alerts | done | `src/app/components/agents/PageMonitorPanel.tsx` |
| F-MP-03 | Mount Page Monitor in Agent Detail for competitor-change-radar capability | done | `src/app/pages/AgentDetailPage.tsx` |
| F-MP-04 | Add missing connector definitions: `reddit`, `newsapi`, `sec_edgar` | done | `src/app/components/settings/connectorDefinitions.ts` |
| F-MP-05 | Handle `authType: none` cleanly in connector UI (no credential form, public API notice) | done | `src/app/components/connectors/ConnectorDetailPanel.tsx`, `src/app/components/settings/ManualConnectorCard.tsx`, `src/app/pages/ConnectorsPage.tsx` |
| F-MP-06 | Show scheduled trigger details in install modal Step 1 (human-readable + timezone + note) | done | `src/app/components/marketplace/AgentInstallModal.tsx` |
| F-MP-07 | Ensure marketplace detail shows tags and required connector visibility clearly | done | `src/app/pages/MarketplaceAgentDetailPage.tsx` |
| F-MP-08 | Add connector health warning on installed-agent surfaces | done | `src/app/pages/WorkspacePage.tsx` (+ agent card surface) |
| F-MP-09 | Add post-install connector gate policy editing surface in agent detail | in_progress | `src/app/pages/AgentDetailPage.tsx` (+ existing connector binding APIs) |
| F-MP-10 | Verify connector marketplace list is API-driven (no static filter blocking new connectors) | done | `src/app/pages/ConnectorMarketplacePage.tsx` |
| F-MP-11 | Widget output enhancements (chart/table/scorecard widgets) | pending | `src/app/components/widgets/*`, `src/app/components/messages/BlockRenderer.tsx` |

---

## Build Order (Strict)
1. F-MP-01
2. F-MP-02
3. F-MP-03
4. F-MP-04
5. F-MP-05
6. F-MP-06
7. F-MP-07
8. F-MP-08
9. F-MP-09
10. F-MP-10
11. F-MP-11

---

## Acceptance Criteria
1. Competitor Change Radar users can manage monitored URLs directly in Agent Detail and run manual refresh checks.
2. Marketplace install flow supports all connectors used by shipped agents, including no-auth connectors.
3. Install modal clearly communicates scheduled execution behavior before install.
4. Agent/workspace surfaces warn users when required connectors are unconfigured or unhealthy.
5. Connector marketplace and detail pages expose complete, non-hidden metadata for decision-making.
