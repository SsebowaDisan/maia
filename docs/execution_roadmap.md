# Maia Execution Roadmap (7-Day Fix Order)
Updated: 2026-03-19
Scope: Stabilize launch-critical flows, harden quality gates, then optimize UX/performance.

## Goal
Ship a reliable, non-technical-user-friendly baseline where install -> setup -> run -> theatre works consistently.

## Rules
1. No new feature expansion until Day 4.
2. Every day ends with a runnable validation checklist.
3. Keep files under 500 LOC when touching code.
4. No merge without smoke checks passing.

## Day 1 - Baseline and Guardrails (Completed)
Owner A:
- Publish this roadmap and execution checklist.
- Add release smoke script for API/UI health + critical endpoints.
- Add LOC report script and regenerate `docs/files_over_500_loc.md`.

Owner B:
- Freeze API contract for connector status + theatre metadata fields.
- Ensure all newly added routes are included in app startup and OpenAPI.

Acceptance:
- `scripts/smoke_release_gate.ps1` exists and passes locally.
- `docs/files_over_500_loc.md` is regenerated from code.
- Contract fields are documented and stable for frontend consumption.

## Day 2 - Critical Runtime Reliability
Owner A:
- Add front-end smoke checks for: workflow step Done -> node appears, install success CTA path, connector drawer open/close.
- Fix non-technical UX labels in step config defaults (hide raw developer fields behind expand/collapse).

Owner B:
- Harden API error model for install/setup/run endpoints (typed errors, no ambiguous plain strings).
- Add server-side regression tests for install preflight/install/handoff/memory APIs.

Acceptance:
- Reproducible pass on critical flow checklist.
- No blocker bug in Done button or node creation path.

Status update (2026-03-19):
- Smoke release gate implemented and passing.
- LOC reporting script implemented and report regenerated.
- Release QA matrix added.
- Day 2 is now the active implementation focus.

## Day 3 - Connector Reliability and Setup Consistency
Owner A:
- Enforce one setup UX entry: popup/drawer from all surfaces.
- Add connector status chips and setup state messaging consistency.

Owner B:
- Stabilize setup status computation (`connected`, `needs_setup`, `needs_permission`, `expired`) across connectors.
- Ensure internal/runtime connectors remain hidden from user catalog.

Acceptance:
- Setup feels identical from Workspace, Marketplace, and Connectors.
- No user-facing internal connectors.

## Day 4 - Theatre and Computer Observability
Owner A:
- Improve theatre labels for connector-aware scenes (email/sheet/doc/chat/api).
- Ensure transitions and handoffs are readable for non-technical users.

Owner B:
- Guarantee theatre events include `connector_id`, `brand_slug`, `scene_family`, `operation_label`.
- Verify computer-use stream events are emitted end-to-end.

Acceptance:
- Every critical workflow step is visible and interpretable in theatre.
- No fallback to unclear generic event labels in core flows.

## Day 5 - Security and Tenant Hardening
Owner A:
- Surface permission errors with user-safe copy and recovery CTAs.

Owner B:
- Audit auth/tenant checks on new routes (`creators`, `explore`, `dashboard`, `triggers`, `memory`, `og`).
- Add abuse/rate-limit protections on publish/review-like endpoints.

Acceptance:
- No cross-tenant leakage in API checks.
- Permission failures are explicit and recoverable.

## Day 6 - Performance and File Structure
Owner A:
- Split oversized frontend files touched this week to <500 LOC.
- Add route-level code splitting for heavy hub pages.

Owner B:
- Split oversized backend routers/services touched this week to <500 LOC.
- Profile slow startup paths and remove obvious boot-time bottlenecks.

Acceptance:
- Updated LOC report shows downward trend with concrete splits.
- Frontend bundle warning reduced from current baseline.

## Day 7 - Launch Readiness Gate
Owner A + B:
- Run full smoke suite.
- Run manual launch checklist (install, connect, run, theatre, chat redirect).
- Produce go/no-go report with blockers and rollback plan.

Acceptance:
- All P0 checks pass.
- Remaining issues are non-blocking and documented.

## P0 Launch Checklist
1. API and UI both healthy.
2. Connector setup works from every entry point without full-page redirect.
3. Workflow step Done creates/updates node correctly.
4. Install -> add to workflow -> run in theatre is stable.
5. Computer-use and API steps are both observable in theatre.
6. No user-facing internal connectors.
7. No critical auth/tenant leak.

## Current Start State (2026-03-19)
- Frontend build passes.
- Multiple large source files exceed 500 LOC and need decomposition.
- Large uncommitted worktree requires disciplined merge validation.
