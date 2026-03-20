# Maia Release QA Matrix
Updated: 2026-03-19
Scope: Frontend-first release verification while backend is frozen for edits.

## Pass Criteria
1. All P0 tests pass.
2. No regression in install -> setup -> run -> theatre.
3. No user-facing internal connector appears.
4. Smoke script passes: `scripts/smoke_release_gate.ps1`.

## P0 Matrix
| ID | Flow | Type | Steps | Expected Result |
|---|---|---|---|---|
| QA-P0-01 | App health | Automated | Run `powershell -ExecutionPolicy Bypass -File scripts/smoke_release_gate.ps1` | API/UI/route/asset/build checks all pass |
| QA-P0-02 | Connector setup entry consistency | Manual | Open setup from Workspace, Marketplace, Connectors | Same popup/drawer pattern everywhere, no full-page jump |
| QA-P0-03 | Install -> Add to workflow | Manual | Install marketplace agent and click `Add to workflow` | Node appears in canvas with correct agent metadata |
| QA-P0-04 | Step Done persistence | Manual | Configure step, click `Done`, close panel | Step remains on canvas and is editable |
| QA-P0-05 | Workflow run -> theatre visibility | Manual | Run workflow with connector action | Theatre shows step progression with readable status |
| QA-P0-06 | Internal connector visibility | Manual | Open connectors catalog | No internal/runtime connector listed |
| QA-P0-07 | Agent chat routing | Manual | Pick agent from composer menu and send message | Request routes to selected `agent_id` |

## P1 Matrix
| ID | Flow | Type | Steps | Expected Result |
|---|---|---|---|---|
| QA-P1-01 | Hub pages route shell | Manual | Visit `/marketplace`, `/explore`, `/creators/:username` | Hub shell layout renders correctly |
| QA-P1-02 | Creator profile edit | Manual | Edit own profile fields and save | Data persists and displays in profile page |
| QA-P1-03 | Team detail install redirect | Manual | Install published team | Redirect to chat with staged workflow context |
| QA-P1-04 | Connector icon reliability | Manual | Block network to remote icon host and refresh connectors page | Local icon fallback still renders for cached brands |

## Known Risks
1. Critical backend files are intentionally untouched in this phase.
2. Some large frontend files still exceed 500 LOC and may hide regressions.
3. Only Google connector icons are currently fully local-cached.

## Release Decision Template
| Item | Value |
|---|---|
| Build version / commit | |
| Smoke gate status | |
| P0 pass count | |
| P1 pass count | |
| Blocking defects | |
| Go / No-Go | |
