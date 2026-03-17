# Maia Frontend Tasks
Updated: 2026-03-16  
Scope: Frontend only (`docs/open_tasks.md`)

## Open Tasks
### Workflow Gap Remediation (2026-03-17)
| ID | Task | Priority | File(s) | Status |
|---|---|---|---|---|
| WF-01 | Replace hardcoded 2-row node placement with scalable DAG-aware layout | Critical | `workflowStore.ts`, `WorkflowCanvas.tsx` | done |
| WF-02 | Rehydrate node `agentName`/`agentDescription` on reload from installed/catalog agent metadata | Critical | `WorkflowBuilderPage.tsx`, `workflowStore.ts` | done |
| WF-03 | Block cycle-creating edges in real time when connecting nodes | Major | `WorkflowCanvas.tsx` | done |
| WF-04 | Remove live-output truncation and add full output view path | Major | `workflowStore.ts`, `WorkflowRunHistory.tsx` | done |
| WF-05 | Add run-history pagination/load-more to avoid rendering entire history at once | Major | `workflows.ts`, `WorkflowBuilderPage.tsx`, `WorkflowRunHistory.tsx` | done |
| WF-06 | Stop heuristic skip-reason guessing; only show explicit reason (or clear fallback) | Major | `WorkflowRunHistory.tsx`, `types.ts` | done |
| WF-07 | Replace URL-param marketplace handoff with resilient in-canvas agent picker flow | Major | `WorkflowCanvas.tsx` | done |
| WF-08 | Validate edge condition expressions in Step Config before save | Minor | `StepConfigPanel.tsx` | done |
| WF-09 | Validate `input_mapping` entries against available output keys before save | Minor | `StepConfigPanel.tsx`, `WorkflowCanvas.tsx` | done |
| WF-10 | Render friendly tool names + raw-ID tooltip on workflow node cards | Minor | `WorkflowNode.tsx` | done |

## Completed
| ID | Task | Status | Notes |
|---|---|---|---|
| F-01 | `AgentPickerPanel` component | done | New searchable install/add panel with installed vs available sections and inline install flow. |
| F-02 | WorkflowCanvas `+` wired to picker | done | Add-step now opens picker and creates pre-labeled nodes from selected agents. |
| F-03 | StepConfigPanel agent dropdown removal | done | Replaced with read-only agent card + `Change agent` action that reopens picker. |
| F-04 | Remove dead `listAgents()` from WorkflowBuilderPage | done | Workflow page no longer loads/prop-drills unused agent list. |
| F-05 | Wire `MultiAgentTheatre` into AgentDetail live view | done | Overview tab now shows live/replay theatre using `subscribeAgentEvents`, with per-agent columns and status/event mapping. |
| F-06 | Install modal success step with CTA | done | Added step 4 success state with `Done` and `Add to workflow` action. |
| F-07 | Add My Agents nav + route + page | done | Added `/agents` route, sidebar entry, and `MyAgentsPage` cards with Chat/Open actions. |
| F-08 | Chat prefill from `?agent=` | done | `openInChat` uses `/?agent=<id>` and composer now preloads `Run <name> for me`, then clears query param. |
| F-09 | `AgentCommandMenu` component | done | New command picker with Recent + All agents, search, keyboard navigation, and no-agent fallback link. |
| F-10 | `ComposerModeSelector` agent sub-picker behavior | done | Agent row opens sub-menu, trigger shows selected agent name, and re-open works while in Agent mode. |
| F-11 | `useChatMainInteractions` active agent state | done | Added `activeAgent` state, `onAgentSelect`, mode clearing rules, and send options include selected `agentId`. |
| F-12 | `ComposerPanel` prop wiring for selected agent | done | Added `activeAgent` + `onAgentSelect` props and passed through to mode selector. |
| F-13 | `chat.ts` API client `agent_id` support | done | `sendChat` + `sendChatStream` now accept `agentId` and send `agent_id` in request payload. |
| F-14 | `sendMessage.ts` payload threading | done | `sharedPayload` now forwards `agentId` from send options into stream/non-stream requests. |

## Validation To Run
- Build frontend: `npm run build` in `frontend/user_interface`
- Smoke test:
  - Composer: pick agent from `AgentCommandMenu` and send a turn; verify selected `agent_id` routing works end-to-end
  - Composer: switch away from Agent mode and verify selected agent clears
  - Composer: open chat with `/?agent=<id>` and confirm prefill + selected agent state
  - Marketplace install -> success step -> `Add to workflow`
  - Workflow canvas add/change agent via picker
  - Agent detail overview live theatre
  - `Chat with this agent` prefill behavior
