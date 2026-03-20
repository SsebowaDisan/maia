# Maia Frontend Tasks
Updated: 2026-03-19
Scope: Frontend and frontend-owned scripts/docs.

## Active Sprint

### F-R1 - Reliability and QA
| ID | Task | Priority | File(s) | Status |
|---|---|---|---|---|
| F-R1-01 | Maintain release smoke gate for app/route/asset/build checks | Critical | `scripts/smoke_release_gate.ps1` | in progress |
| F-R1-02 | Publish release QA matrix for manual + automated P0/P1 checks | Critical | `docs/release_qa_matrix.md` | in progress |
| F-R1-03 | Add focused UI tests for canvas Done and install->workflow flows | High | `frontend/user_interface/src/**` | open |

### F-U1 - UX for Non-Technical Users
| ID | Task | Priority | File(s) | Status |
|---|---|---|---|---|
| F-U1-01 | Hide technical settings by default in step config panels | High | `StepConfigPanel` and related components | open |
| F-U1-02 | Improve plain-language helper copy in setup and validation states | Medium | workflow and connector panels | open |

### F-C1 - Connector Experience
| ID | Task | Priority | File(s) | Status |
|---|---|---|---|---|
| F-C1-01 | Use local-first icon fallback strategy with remote backup | High | `ConnectorBrandIcon.tsx`, `public/icons/connectors/*` | in progress |
| F-C1-02 | Expand local cached icon coverage beyond current Google set | Medium | `public/icons/connectors/*` | open |
| F-C1-03 | Verify setup entry consistency across Workspace/Marketplace/Connectors | High | page-level CTA entry points | open |

### F-P1 - Performance and Structure
| ID | Task | Priority | File(s) | Status |
|---|---|---|---|---|
| F-P1-01 | Reduce bundle size via route-level splitting and lazy sections | High | app shell and hub routes | open |
| F-P1-02 | Split top oversized frontend files to <500 LOC | High | see `docs/files_over_500_loc.md` | open |

## Runbook
1. `powershell -ExecutionPolicy Bypass -File scripts/smoke_release_gate.ps1`
2. `powershell -ExecutionPolicy Bypass -File scripts/report_files_over_500_loc.ps1`
3. Validate against `docs/release_qa_matrix.md` P0 checklist.
