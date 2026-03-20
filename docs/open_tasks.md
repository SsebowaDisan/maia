# Maia Open Tasks
Updated: 2026-03-19
Scope: Active gaps and execution priorities.

## Current Constraint
Backend code is frozen for edits in this phase. Work is frontend/docs/scripts only.

## Priority Gaps
| ID | Gap | Priority | Status |
|---|---|---|---|
| G-01 | Release hygiene (clean staging + controlled merge flow) | Critical | In progress |
| G-02 | End-to-end QA matrix for install -> setup -> run -> theatre | Critical | In progress |
| G-03 | Reliable smoke coverage for critical UI flows | Critical | In progress |
| G-04 | Non-technical UX defaults in configuration panels | High | Open |
| G-05 | Frontend performance and bundle size reduction | High | Open |
| G-06 | Frontend file decomposition to under 500 LOC | High | Open |
| G-07 | Connector icon local cache strategy | High | In progress |
| G-08 | Task/documentation alignment with new hub/automation surfaces | Medium | In progress |
| G-09 | Frontend integration tests for key routes and interactions | Medium | Open |

## Completed Recently
1. Added release smoke gate script: `scripts/smoke_release_gate.ps1`.
2. Added LOC reporting script: `scripts/report_files_over_500_loc.ps1`.
3. Regenerated LOC report: `docs/files_over_500_loc.md`.
4. Added strict 7-day fix order roadmap: `docs/execution_roadmap.md`.

## Next Frontend Work Order
1. Expand smoke coverage for critical UI paths and static assets.
2. Finish connector icon fallback strategy with local-first rendering.
3. Reduce the largest frontend files below 500 LOC in phased refactors.
4. Add focused UI tests for canvas Done flow and install-to-workflow flow.
