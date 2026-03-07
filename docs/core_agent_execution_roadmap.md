# Maia Core Agent Execution Roadmap

## Rules For Execution
- Only one active slice at a time.
- No file over 500 LOC.
- Use LLM-semantic reasoning for routing and decisions; no hardcoded words as the primary decision mechanism.
- No shortcuts: implement the full slice acceptance path (code, tests, checklist update) before moving on.
- Every user-facing step must meet Apple-level professional quality, with clear and polished "Steve Jobs style" craftsmanship.
- A slice is complete only when:
  - acceptance tests pass
  - regression slice passes
  - checklist is updated to `done`
- Do not start the next slice until the current slice is complete.

## Naming Rule (Mandatory)
- Scope: these naming rules apply to Maia modules under `api/` and `frontend/user_interface/src/`, not only UI modules.
- Structure must be domain-first, not prefix-first.
- Do not add new root-level prefix-first modules when an existing Maia domain folder already fits the code.
- Do not add new root-level catch-all modules such as `agent_*`, `browser_*`, `chat_*`, or `manifest_*` if the code belongs under an existing domain path.
- Prefer paths like:
  - `api/services/agent/orchestration/role_router.py`
  - `api/services/agent/execution/browser_event_contract.py`
  - `api/services/agent/tools/workspace/research_notes.py`
  - `frontend/user_interface/src/app/components/agentDesktopScene/InteractionOverlay.tsx`
  - `frontend/user_interface/src/app/components/chatMain/citationFocus.ts`
- Keep names boring and searchable: lowercase folders, snake_case files.
- Any move/rename must update all imports in the same slice and keep tests green.

## Status Legend
- `todo` not started
- `in_progress` currently active
- `done` complete and validated
- `blocked` needs decision or prerequisite

## Purpose
Turn Maia into a general execution agent whose default runtime loop is:

1. Understand the request.
2. Discover missing context autonomously.
3. Act through the right specialist role.
4. Verify outputs, evidence, and side effects.
5. Ask the user only when still blocked or when approval is required.

This roadmap is intentionally "mind first, theatre second." A believable UI depends on real internal role separation, scoped context, durable memory, and a unified action protocol.

## Analysis Summary

### What the proposal gets right
- Maia should not behave like one monolithic planner. Distinct roles improve decomposition, tool choice, verification, and transparency.
- Long-running tasks need compiled context, not raw prompt stuffing.
- A theatre engine only works if every surface emits a shared action/event vocabulary.
- Verification and approval must be first-class runtime stages, not post-hoc formatting.

### What must be adapted for Maia
- Do not make contact-form automation a core stage. It is a specialist capability, not the center of the agent.
- Do not replace the current Maia orchestrator with CrewAI or AutoGen in the first implementation pass. Maia already has an execution spine in `api/services/agent/orchestration/app.py`, `api/services/agent/events.py`, `api/services/agent/live_events.py`, and the tool registry. Replacing that now would add abstraction churn without solving the main gaps.
- Do not use hardcoded prompt words to choose roles or capabilities. Role selection, slot resolution, discovery decisions, and approval gating must stay LLM-semantic and evidence-aware.
- `goal_page_discovery.py` is the correct general abstraction. Contact discovery stays behind that more general navigation capability instead of becoming a top-level architecture concept.

## Non-Negotiable Rules
- LLM-semantic routing only. No hardcoded keyword lists as the primary decision path.
- Discover before clarify. Missing information is modeled as typed slots, then resolved through browsing, search, file reading, memory, or direct user input only if those attempts fail.
- The runtime must stay resumable. Human handoff is a pause/resume boundary, not a failed run.
- Every visible motion in the theatre must come from a real execution event.
- The same interaction grammar must cover browser, documents, sheets, email, and deep-research surfaces.
- External side effects such as sending email, posting messages, or submitting forms require explicit approval when policy says so.
- CAPTCHA handling is `pause -> user completes -> Maia resumes`. No fake automatic solving.

## Current Maia Assessment

### What already exists
- Conductor/orchestrator skeleton:
  - `api/services/agent/orchestration/app.py`
  - `api/services/agent/orchestration/task_preparation.py`
  - `api/services/agent/orchestration/step_execution.py`
  - `api/services/agent/orchestration/step_planner_sections/*`
- Semantic contract and discover-first infrastructure:
  - `api/services/agent/llm_contracts.py`
  - `api/services/agent/contract_verification.py`
  - `api/services/agent/orchestration/contract_slots.py`
  - `api/services/agent/orchestration/discovery_gate.py`
- Browser execution/event groundwork:
  - `api/services/agent/execution/browser_runtime.py`
  - `api/services/agent/execution/browser_event_contract.py`
  - `api/services/agent/execution/interaction_event_contract.py`
  - `api/services/agent/connectors/browser_connector.py`
- Live event transport and UI theatre skeleton:
  - `api/services/agent/events.py`
  - `api/services/agent/live_events.py`
  - `api/services/agent/orchestration/stream_bridge.py`
  - `frontend/user_interface/src/app/components/agentDesktopScene/*`
  - `frontend/user_interface/src/app/components/agentActivityPanel/*`
  - `frontend/user_interface/src/app/components/InfoPanel.tsx`
- Human pause/resume primitive:
  - `api/services/agent/orchestration/handoff_state.py`

### What is still missing
- Roles are still mostly implicit and tool-centric rather than first-class micro-agent contracts.
- Context is partially assembled in preparation code, but not yet compiled through explicit processors per role.
- Memory is still lightweight file-backed JSON in `api/services/agent/memory.py`; it is useful, but not yet a durable session-plus-memory architecture.
- Interaction normalization exists, but the protocol is still browser-biased and not yet the authoritative contract for all surfaces.
- Specialist modules such as contact-form flows still sit too close to the center of the architecture.
- Approval, verification, and delivery are present, but they need stronger coupling to role handoff, side-effect policy, and resumable barriers.

## Target Role Topology

| Role | Responsibility | Current Maia anchor points | Gap to close |
| --- | --- | --- | --- |
| Conductor | Own the run loop, route work, maintain checkpoints | `orchestration/app.py`, `stream_bridge.py`, `events.py` | Needs first-class role handoffs and scoped context boundaries |
| Planner | Decompose tasks into executable steps and success criteria | `task_preparation.py`, `llm_planner.py`, `step_planner_sections/*` | Needs explicit planner output contract tied to roles/capabilities |
| Research | Search, open sources, collect evidence, fuse findings | `tools/research_tools.py`, `web_evidence.py`, `web_kpi.py` | Needs stronger source budgeting, parallel gather, and evidence packaging |
| Browser | Perform live web interaction and page inspection | `connectors/browser_connector.py`, `tools/browser_tools.py`, `execution/browser_*` | Needs richer page-state data and broader action parity beyond browser-only events |
| Document | Read PDFs and files, extract/highlight evidence | `tools/document_tools.py`, `tools/document_highlight_tools.py` | Needs to emit the same live interaction contract as browser flows |
| Analyst | Aggregate data, compute metrics, create charts | `tools/data_tools.py`, `tools/charts_tools.py`, `tools/data_science/*` | Needs a clearer handoff contract from research/document roles |
| Writer | Produce reports, emails, workspace docs, summaries | `answer_builder.py`, `answer_builder_sections/*`, `llm_execution_support_parts/*`, `tools/email_tools.py`, `tools/workspace/*` | Needs structured output targets and stronger recipient/content understanding |
| Verifier | Check fact coverage, plan completion, action outcomes | `contract_verification.py`, `intelligence_sections/verification.py`, `answer_builder_sections/verification.py` | Needs deeper step-level and side-effect verification |
| Safety | Gate risky actions and manage human confirmation | `governance.py`, `policy.py`, `contract_gate.py`, `handoff_state.py`, `step_execution_sections/guards.py` | Needs to become a first-class runtime role rather than a scattered concern |

## Role Persistence Strategy
- Persistent core roles:
  - `conductor`
  - `planner`
  - `research`
  - `browser`
  - `writer`
  - `verifier`
  - `safety`
- Initially ephemeral specialist helpers:
  - `document_reader`
  - `analyst`
  - `chart_builder`
  - `workspace_editor`
  - `goal_page_discovery`
  - `contact_form`
- Promotion rule:
  - promote a helper into a persistent role only after telemetry shows it is reused often enough to justify dedicated contracts, memory, and replay semantics.

## Canonical Runtime Loop

```text
understand
  -> compile contract
  -> classify missing slots
discover
  -> search / browse / read files / use memory
  -> resolve or narrow slots
act
  -> planner assigns a role and tool path
  -> role executes with scoped context
verify
  -> check evidence coverage, output quality, and side effects
ask
  -> only if unresolved blockers remain or human approval is required
```

## Canonical Interaction Contract
The current browser event contract is a good start. Maia should extend it into a single authoritative interaction schema used across all surfaces.

```json
{
  "event_schema_version": "interaction_v2",
  "role": "browser",
  "action": "click",
  "surface": "website",
  "phase": "active",
  "status": "ok",
  "target": {
    "url": "https://example.com",
    "selector": "button[type=submit]",
    "label": "Submit"
  },
  "cursor": { "x": 512, "y": 304 },
  "scroll": { "direction": "down", "percent": 42.0 },
  "snapshot_ref": "snapshots/example.png",
  "result": {
    "summary": "Clicked the submit button",
    "verified": false
  },
  "evidence": [
    {
      "source_id": "src_123",
      "file_id": "file_456",
      "page_label": "Page 2",
      "snippet": "Quarterly revenue increased..."
    }
  ],
  "timestamp": "2026-03-07T15:10:30Z"
}
```

Browser-only actions remain a subset:
- `navigate`
- `hover`
- `click`
- `type`
- `scroll`
- `extract`
- `verify`

Cross-surface scenes may carry the same verbs with different target metadata.

## Implementation Order
The order below is the shortest practical path for Maia in this repo.

1. Micro-agent control plane
2. Context compiler and memory architecture
3. Unified interaction grammar
4. Orchestrator role routing and persistent task loop
5. Theatre engine and evidence rail
6. Verification, approval, and resumable handoff
7. Optional specialist capabilities such as `goal_page_discovery.py`

## Execution Slices
Current active slice: `complete`

### Stage 1 slices: Micro-Agent Control Plane
- `done` `S1.1` Define canonical role identifiers and contracts in `api/services/agent/orchestration/agent_roles.py` and `api/services/agent/orchestration/role_contracts.py`. Acceptance and regression tests passed (`test_agent_role_contracts`, `test_agent_capability_planning`, `test_agent_planner`).
- `done` `S1.2` Introduce `api/services/agent/orchestration/role_router.py` and make planner output role-owned execution steps instead of tool-first steps. Acceptance and regression tests passed (`test_agent_role_router`, `test_agent_step_planner_research_and_logging`, `test_agent_step_planner_evidence`, plus planner/capability regression).
- `done` `S1.3` Emit role-handoff and role-activation events through `api/services/agent/orchestration/app.py`, `api/services/agent/events.py`, and `api/services/agent/orchestration/stream_bridge.py`. Acceptance and regression tests passed (`test_agent_step_execution_roles`, `test_agent_event_schema`, planner/step-planner regression).
- `done` `S1.4` Enforce role-based tool allowlists and verification obligations inside `api/services/agent/orchestration/step_execution.py` and related step-execution sections. Acceptance and regression tests passed (`test_agent_step_execution_role_contract_guards`, `test_agent_deferred_clarification`, step execution/planner regression).

### Stage 2 slices: Context Compiler and Memory Architecture
- `done` `S2.1` Add `api/services/agent/orchestration/session_store.py` and define durable separation between session events and long-term memory artifacts. Acceptance and regression tests passed (`test_agent_session_store`, `test_agent_orchestration_prompt_context`, `test_agent_event_schema`, plus Stage 1 role/guard/planner regression).
- `done` `S2.2` Add `api/services/agent/orchestration/context_processors.py` and `api/services/agent/orchestration/working_context.py` to compile request, contract, slot, history, artifact, and memory context. Acceptance and regression tests passed (`test_agent_working_context`, `test_agent_event_schema`, plus session/planner/role regression).
- `done` `S2.3` Refactor `api/services/agent/orchestration/task_preparation.py` and execution call sites to hand each role a scoped working context instead of broad raw history. Acceptance and regression tests passed (`test_agent_orchestration_prompt_context`, `test_agent_working_context`, plus session/planner/role regression).
- `done` `S2.4` Tighten `api/services/agent/orchestration/contract_slots.py`, `api/services/agent/orchestration/discovery_gate.py`, and clarification helpers so autonomous discovery is exhausted before clarification is emitted. Acceptance and regression tests passed (`test_agent_discovery_gate`, `test_discovery_gate_slots`, `test_agent_deferred_clarification`, plus session/planner/role regression).

### Stage 3 slices: Unified Interaction Grammar
- `done` `S3.1` Define the shared interaction schema revision and role/surface metadata in `api/services/agent/execution/interaction_event_contract.py`. Acceptance and regression tests passed (`test_browser_event_contract`, `test_interaction_event_contract`, plus Stage 1/2 discovery-role-planner regression).
- `done` `S3.2` Refactor `api/services/agent/execution/browser_event_contract.py`, `api/services/agent/execution/browser_runtime.py`, and `api/services/agent/connectors/browser_connector.py` to emit the shared contract consistently. Acceptance and regression tests passed (`test_browser_event_contract`, `test_interaction_event_contract`, `test_agent_stream_bridge`, plus Stage 1/2 discovery-role-planner regression).
- `done` `S3.3` Normalize non-browser surfaces in `api/services/agent/tools/research_tools.py`, `api/services/agent/tools/document_highlight_tools.py`, `api/services/agent/tools/document_tools.py`, `api/services/agent/tools/email_tools.py`, and `api/services/agent/tools/workspace/*`. Acceptance and regression tests passed (`test_interaction_event_contract`, `test_agent_stream_bridge`, `test_workflow_specialist_tools`, plus Stage 1/2 role-discovery-context regression slice).
- `done` `S3.4` Add event-coverage tests and release checks for normalized browser, document, email, docs, and sheets actions. Acceptance and regression tests passed (`test_interaction_event_contract`, `test_interaction_event_release_gate`, `test_agent_stream_bridge`, `test_workflow_specialist_tools`, plus Stage 1/2 role-discovery-context regression slice).

### Stage 4 slices: Orchestrator Role Routing and Persistent Task Loop
- `done` `S4.1` Refactor `api/services/agent/orchestration/app.py` into a role-aware persistent execution loop with explicit checkpoints and role dispatch. Acceptance and regression tests passed (`test_agent_execution_checkpoints`, `test_agent_event_schema`, `test_interaction_event_contract`, `test_agent_stream_bridge`, plus Stage 1/2 role-discovery-context regression slice).
- `done` `S4.2` Upgrade planner and execution state models so retries, remediation, and parallel research gathering remain traceable and contract-bound. Acceptance and regression tests passed (`test_agent_execution_trace`, `test_agent_step_execution_retry`, `test_agent_step_execution_role_contract_guards`, plus Stage 1/2/3 role-discovery-interaction regression slice).
- `done` `S4.3` Make `api/services/agent/orchestration/contract_gate.py`, `api/services/agent/contract_verification.py`, and delivery sections authoritative for side-effect completion status. Acceptance and regression tests passed (`test_agent_delivery_authority`, `test_agent_llm_contracts`, plus Stage 1/2/3/4 orchestration regression slice).
- `done` `S4.4` Persist resumable run checkpoints and next-step state so role execution can continue safely after interruptions. Acceptance and regression tests passed (`test_agent_run_checkpoint_persistence`, `test_agent_session_store`, plus Stage 1/2/3/4 orchestration regression slice).

### Stage 5 slices: Theatre Engine and Evidence Rail
- `done` `S5.1` Refactor `frontend/user_interface/src/app/components/agentActivityPanel/useAgentActivityDerived.ts` and desktop viewer state so role-aware scenes derive directly from normalized interaction events. Acceptance and regression checks passed (`frontend/user_interface npm run build`).
- `done` `S5.2` Update `frontend/user_interface/src/app/components/agentDesktopScene/*` to render grounded motion across browser, PDFs, docs, sheets, and email. Acceptance and regression checks passed (`frontend/user_interface npm run build`).
- `done` `S5.3` Strengthen `frontend/user_interface/src/app/components/InfoPanel.tsx` as an evidence-first panel with citation replay and source context. Acceptance and regression checks passed (`frontend/user_interface npm run build`).
- `done` `S5.4` Add replay and rendering tests for role transitions, approval pauses, citation focus, and mixed-surface runs. Acceptance and regression checks passed (`frontend/user_interface npm test`, `frontend/user_interface npm run build`).

### Stage 6 slices: Verification, Approval, and Resumable Handoff
- `done` `S6.1` Expand barrier taxonomy and pause/resume events in `api/services/agent/orchestration/handoff_state.py`, guard sections, and policy/governance modules. Acceptance and regression checks passed (`PYTHONPATH=... pytest -q api/tests/test_handoff_state.py api/tests/test_agent_event_schema.py api/tests/test_browser_tools.py api/tests/test_contact_form_tool.py`, plus role/discovery regression slice).
- `done` `S6.2` Route CAPTCHA and human-verification detection into explicit resumable handoff state instead of failure-only handling. Acceptance and regression checks passed (`PYTHONPATH=... pytest -q api/tests/test_browser_tools.py api/tests/test_contact_form_tool.py api/tests/test_handoff_state.py`, plus orchestration regression slice).
- `done` `S6.3` Require post-resume verification before `finalization.py` can report completion of external actions. Acceptance and regression checks passed (`PYTHONPATH=... pytest -q api/tests/test_agent_finalization_info_html.py api/tests/test_handoff_state.py api/tests/test_agent_event_schema.py api/tests/test_browser_tools.py api/tests/test_contact_form_tool.py`, plus orchestration regression slice).
- `done` `S6.4` Audit final answer truthfulness so outputs always distinguish attempted, approved, blocked, resumed, and sent outcomes. Acceptance and regression checks passed (`PYTHONPATH=... pytest -q api/tests/test_agent_answer_builder_delivery_status.py api/tests/test_agent_finalization_info_html.py api/tests/test_handoff_state.py api/tests/test_agent_event_schema.py`, plus orchestration regression slice).

### Stage 7 slices: Optional Specialist Capabilities
- `done` `S7.1` Formalize `api/services/agent/connectors/browser_goal/goal_page_discovery.py` as the reusable goal-page capability behind a semantic capability flag. Added `api/services/agent/connectors/browser_goal/capability.py`, persisted capability-plan signals in planner settings, and threaded structured capability decisions through contact discovery. Acceptance and regression checks passed (`PYTHONPATH=... pytest -q api/tests/test_goal_page_capability.py api/tests/test_browser_contact_discovery.py api/tests/test_contact_form_tool.py api/tests/test_agent_step_planner_research_and_logging.py api/tests/test_agent_planner.py`, plus regression slice: `test_agent_discovery_gate`, `test_agent_deferred_clarification`, `test_agent_delivery_authority`, `test_agent_event_schema`, `test_handoff_state`, `test_agent_stream_bridge`, `test_interaction_event_contract`).
- `done` `S7.2` Decouple `api/services/agent/connectors/browser_contact/*` and `api/services/agent/tools/contact_form_tools.py` from the core runtime path. Contact-form tooling is now specialist-gated (`MAIA_AGENT_CONTACT_FORM_ENABLED`) at registry level, planner enrichment checks specialist capability state, and unavailable tools are filtered from execution plans before runtime. Acceptance and regression checks passed (`PYTHONPATH=... pytest -q api/tests/test_tool_registry_specialist_capabilities.py api/tests/test_tool_registry.py api/tests/test_agent_step_planner_research_and_logging.py api/tests/test_contact_form_tool.py api/tests/test_agent_planner.py`, plus regression slice: `test_agent_discovery_gate`, `test_agent_deferred_clarification`, `test_agent_delivery_authority`, `test_agent_event_schema`, `test_handoff_state`, `test_agent_stream_bridge`, `test_interaction_event_contract`).
- `done` `S7.3` Make specialist capability invocation derive from task contract and role planning rather than hardcoded prompt phrases. Contact-step enrichment now requires structured contract/intent/capability-plan signals instead of heuristic `wants_contact_form` phrases, with explicit specialist enablement gating. Acceptance and regression checks passed (`PYTHONPATH=... pytest -q api/tests/test_agent_step_planner_research_and_logging.py api/tests/test_agent_planner.py api/tests/test_goal_page_capability.py api/tests/test_tool_registry_specialist_capabilities.py`, plus regression slice: `test_agent_discovery_gate`, `test_agent_deferred_clarification`, `test_agent_delivery_authority`, `test_agent_event_schema`, `test_handoff_state`, `test_agent_stream_bridge`, `test_interaction_event_contract`).
- `done` `S7.4` Add optional-capability tests, rollout flags, and guardrails so specialist modules do not regress the core agent path. Added specialist rollout and guardrail coverage for registry toggles, runtime contact-capability gating, and unavailable-tool filtering (`test_agent_specialist_capability_guardrails`, `test_tool_registry_specialist_capabilities`). Acceptance and regression checks passed (`PYTHONPATH=... pytest -q api/tests/test_agent_specialist_capability_guardrails.py api/tests/test_tool_registry_specialist_capabilities.py api/tests/test_agent_step_planner_research_and_logging.py api/tests/test_agent_planner.py api/tests/test_goal_page_capability.py`, plus regression slice: `test_agent_discovery_gate`, `test_agent_deferred_clarification`, `test_agent_delivery_authority`, `test_agent_event_schema`, `test_handoff_state`, `test_agent_stream_bridge`, `test_interaction_event_contract`).

## Stage 1: Micro-Agent Control Plane

### Goal
Make roles explicit without rewriting the whole system around a new external framework.

### Why this comes first
Maia currently has execution logic, but role ownership is implicit. Without explicit role contracts, the planner, researcher, writer, verifier, and safety logic blur together and the theatre cannot explain who is acting or why.

### Primary files to refactor
- `api/services/agent/orchestration/app.py`
- `api/services/agent/orchestration/task_preparation.py`
- `api/services/agent/orchestration/step_execution.py`
- `api/services/agent/orchestration/step_planner_sections/*`
- `api/services/agent/llm_planner.py`
- `api/services/agent/llm_contracts.py`

### New files to add
- `api/services/agent/orchestration/agent_roles.py`
- `api/services/agent/orchestration/role_router.py`
- `api/services/agent/orchestration/role_contracts.py`

### Implementation tasks
1. Define stable role identifiers and their allowed tools, outputs, and verification obligations.
2. Convert current planner output into a role-aware plan format:
   - step goal
   - owner role
   - required capability
   - required evidence
   - success condition
3. Add role-handoff events so the UI can show which role is active.
4. Keep the conductor as the only runtime owner of the full run state.
5. Treat sub-agents as scoped role contracts first, not as fully separate processes.
6. Make role selection semantic through LLM contracts and intent signals, not prompt keyword matching.

### Definition of done
- Every planned step has a declared role owner.
- The runtime emits role-handoff events that can be rendered live.
- Tool access is constrained by role contract rather than being globally implicit.
- The final answer can explain which role performed which major part of the work.

## Stage 2: Context Compiler and Memory Architecture

### Goal
Replace broad prompt assembly with compiled working context per role.

### Why this is necessary
Passing full conversation history to every role causes scope drift, noise, and accidental invention. Maia already has contract slots and memory snippets; they need to become a deliberate compiled context pipeline.

### Primary files to refactor
- `api/services/agent/memory.py`
- `api/services/agent/orchestration/task_preparation.py`
- `api/services/agent/orchestration/models.py`
- `api/services/agent/llm_contracts.py`
- `api/services/agent/orchestration/clarification_helpers.py`
- `api/services/agent/orchestration/contract_slots.py`
- `api/services/agent/orchestration/discovery_gate.py`

### New files to add
- `api/services/agent/orchestration/working_context.py`
- `api/services/agent/orchestration/context_processors.py`
- `api/services/agent/orchestration/session_store.py`

### Implementation tasks
1. Separate durable session events from long-term memory artifacts.
2. Introduce context processors that build a working context from:
   - user request
   - active contract
   - resolved slots
   - recent session events
   - retrieved memory
   - active artifacts and evidence
3. Compile different working contexts for different roles.
4. Distinguish two handoff patterns:
   - role-as-tool: narrow one-shot subtask, no inherited history
   - control transfer: scoped session handoff for multi-step work
5. Move missing information handling fully onto typed slots:
   - `description`
   - `discoverable`
   - `blocking`
   - `confidence`
   - `evidence_sources`
   - `resolved_value`
6. Keep all slot resolution semantic. The LLM decides if an item is discoverable or blocking; the code enforces lifecycle and safety.
7. Add persistent storage abstraction so the JSON store can remain a fallback while a database-backed implementation is introduced later.

### Definition of done
- Every LLM call can be traced back to a compiled working-context snapshot.
- Roles no longer receive the full raw history by default.
- Clarification is triggered only after autonomous discovery attempts fail.
- Memory retrieval is testable and reproducible from session state.

## Stage 3: Unified Interaction Grammar

### Goal
Make `interaction_event_contract.py` the shared source of truth for all visible execution surfaces.

### Primary files to refactor
- `api/services/agent/execution/browser_event_contract.py`
- `api/services/agent/execution/interaction_event_contract.py`
- `api/services/agent/events.py`
- `api/services/agent/tools/browser_tools.py`
- `api/services/agent/tools/research_tools.py`
- `api/services/agent/tools/document_highlight_tools.py`
- `api/services/agent/tools/document_tools.py`
- `api/services/agent/tools/email_tools.py`
- `api/services/agent/tools/workspace/*`

### Implementation tasks
1. Normalize browser, document, email, docs, sheets, and research events into one event model.
2. Expand metadata so every visible event can carry:
   - acting role
   - surface
   - target metadata
   - cursor position when meaningful
   - scroll state when meaningful
   - snapshot reference
   - result summary
   - evidence references
3. Keep browser action names stable, but make other surfaces map into the same limited verb set where possible.
4. Add regression tests for event normalization across website, PDF, email, docs, and sheets.
5. Make event coverage a release gate for any new tool that appears in the theatre.

### Definition of done
- Search results, opened pages, PDFs, docs, sheets, and emails all emit the same contract family.
- UI rendering does not need tool-specific heuristics for basic motion semantics.
- Event coverage reports can show missing live-visibility gaps before release.

## Stage 4: Orchestrator Role Routing and Persistent Task Loop

### Goal
Make the conductor run a true multi-role execution loop rather than a mostly linear tool plan.

### Primary files to refactor
- `api/services/agent/orchestration/app.py`
- `api/services/agent/orchestration/step_execution.py`
- `api/services/agent/orchestration/step_planner_sections/*`
- `api/services/agent/orchestration/contract_gate.py`
- `api/services/agent/contract_verification.py`
- `api/services/agent/orchestration/delivery_sections/*`

### Implementation tasks
1. Introduce a persistent run loop that repeatedly evaluates:
   - current contract
   - unresolved slots
   - completed steps
   - verification state
   - approval barriers
2. Let the planner assign work to roles rather than directly naming tools as the primary abstraction.
3. Route execution through the conductor with minimal scoped context per role.
4. Add retry and remediation policies:
   - transient web failures
   - blocked pages
   - missing document evidence
   - delivery authorization gaps
5. Support parallel research gathering where safe, then merge evidence into a shared verification state.
6. Distinguish these three outcomes clearly:
   - autonomous continuation
   - human approval required
   - hard failure
7. Make the contract gate authoritative for external side effects. A tool may technically run, but the run is not "successful" if the contract gate blocks delivery.

### Definition of done
- The runtime behaves as `understand -> discover -> act -> verify -> ask`.
- Parallel research can happen without losing run traceability.
- Delivery and side-effect reporting cannot claim success when the gate blocks completion.

## Stage 5: Theatre Engine and Evidence Rail

### Goal
Make the front-end render real role-based activity across browser, PDFs, docs, sheets, and email.

### Primary files to refactor
- `frontend/user_interface/src/app/components/agentDesktopScene/BrowserScene.tsx`
- `frontend/user_interface/src/app/components/agentDesktopScene/DocumentScenes.tsx`
- `frontend/user_interface/src/app/components/agentDesktopScene/DocsScene.tsx`
- `frontend/user_interface/src/app/components/agentDesktopScene/SheetsScene.tsx`
- `frontend/user_interface/src/app/components/agentDesktopScene/EmailScene.tsx`
- `frontend/user_interface/src/app/components/agentDesktopScene/InteractionOverlay.tsx`
- `frontend/user_interface/src/app/components/agentDesktopScene/sceneEvents.ts`
- `frontend/user_interface/src/app/components/agentActivityPanel/useAgentActivityDerived.ts`
- `frontend/user_interface/src/app/components/agentActivityPanel/DesktopViewer.tsx`
- `frontend/user_interface/src/app/components/InfoPanel.tsx`

### Implementation tasks
1. Render role-aware captions such as:
   - "Planner is structuring the task"
   - "Research is gathering sources"
   - "Browser is opening the pricing page"
   - "Verifier is checking coverage"
2. Tie cursor motion, click pulse, scroll movement, typing focus, and highlight regions to normalized events only.
3. Upgrade document scenes so PDFs show scan focus, page movement, and evidence highlighting rather than static preview.
4. Keep the information panel evidence-first:
   - structured evidence cards
   - citation deep links
   - source preview only when useful
5. Show approval and handoff barriers directly in the theatre, with clear resume state.
6. Make the user visible to the role flow without cluttering the UI with tool internals.

### Definition of done
- The theatre can replay a mixed browser/document/email run coherently.
- The active role is always visible.
- Citation focus and evidence preview work across website and file sources.
- Motion is grounded in real events rather than simulated filler.

## Stage 6: Verification, Approval, and Resumable Handoff

### Goal
Make trust and resumability part of the runtime, not an afterthought.

### Primary files to refactor
- `api/services/agent/orchestration/handoff_state.py`
- `api/services/agent/orchestration/step_execution_sections/guards.py`
- `api/services/agent/governance.py`
- `api/services/agent/policy.py`
- `api/services/agent/orchestration/contract_gate.py`
- `api/services/agent/orchestration/delivery_sections/decisioning.py`
- `api/services/agent/orchestration/finalization.py`

### Implementation tasks
1. Separate fact verification from action approval.
2. Expand barrier types:
   - human verification
   - external authorization
   - policy approval
   - sensitive side effect confirmation
3. Persist handoff state with enough detail to resume safely:
   - pause reason
   - target location
   - notes
   - resume token
   - verification context
4. Emit explicit pause/resume events so the UI can display them naturally.
5. Make CAPTCHA or bot challenge detection automatically transition into a resumable handoff state.
6. Require the verifier to re-check completion after resume before reporting success.

### Definition of done
- Maia never pretends to solve CAPTCHAs autonomously.
- A paused run can resume without losing its contract, evidence, or planned next step.
- Approval state is auditable in the final run log.

## Stage 7: Optional Specialist Capabilities

### Goal
Keep the core agent general while still allowing specialist automation modules.

### Capability model
- Core runtime first.
- Specialist capability second.
- Capability selection through semantic role planning and contract needs, not hardcoded prompt phrases.

### General capability to keep
- `api/services/agent/connectors/browser_goal/goal_page_discovery.py`

### Specialist capabilities that stay optional
- `api/services/agent/connectors/browser_contact/*`
- `api/services/agent/tools/contact_form_tools.py`
- domain-specific workspace or business flows

### Naming decision
- `contact_discovery.py` is too narrow to represent Maia's general navigation intelligence.
- The general abstraction is goal-page discovery.
- Contact-form discovery should remain a special-case implementation that uses the general goal-page navigation capability when the contract requires outreach or form submission.

### Implementation tasks
1. Move generic page-finding logic toward `browser_goal/goal_page_discovery.py`.
2. Keep contact-specific field extraction and submission logic inside `browser_contact/*`.
3. Introduce capability flags so specialist modules can be enabled without polluting the core runtime path.
4. Make capability invocation semantic:
   - derive from task contract
   - derive from role plan
   - derive from evidence of target surface affordances

### Definition of done
- Maia remains a general agent even if specialist modules are installed.
- Contact-form logic is not part of the core planner loop unless the task truly requires it.
- Goal-page discovery can be reused by other workflows beyond contact forms.

## Example End-to-End Flow
User request:

`Analyze this company website, gather supporting evidence, draft a report, and send it after I approve it.`

Expected runtime:

1. Conductor receives the request and starts a run.
2. Planner builds a role-aware contract and execution plan.
3. Discovery gate classifies missing slots and attempts autonomous resolution.
4. Research role searches and opens source pages.
5. Browser role navigates the site and emits live interaction events.
6. Document role reads any attached PDFs and links evidence.
7. Analyst role aggregates findings if numeric synthesis is needed.
8. Writer role drafts the report and email.
9. Verifier checks evidence coverage, contract completion, and delivery readiness.
10. Safety role pauses for approval before sending.
11. User approves.
12. Conductor resumes the run and completes delivery.
13. Finalization writes a truthful summary that distinguishes:
    - analysis completed
    - delivery approved
    - delivery sent

## Quality Gates
- No hardcoded keyword path for role selection or clarification logic.
- Every user-visible action maps to the interaction contract.
- Every external side effect has an approval and verification trail.
- Every final answer must distinguish "attempted", "verified", and "completed".
- Every citation shown in the info panel must resolve to evidence context.

## Testing Plan

### Backend
- Add unit tests for:
  - role routing
  - context processor output
  - slot lifecycle and discovery resolution
  - interaction event normalization
  - contract gate behavior after external tool execution
- Add integration tests for:
  - website research runs
  - PDF evidence runs
  - approval pause/resume flows
  - delivery truthfulness in finalization

### Frontend
- Add scene tests for:
  - browser motion
  - document scan focus
  - email compose flow
  - approval barrier rendering
  - citation focus replay

### End-to-end
- Website analysis and report draft
- PDF extraction and citation grounding
- Research plus email delivery with approval pause
- Human verification barrier and resume

## Anti-Patterns to Avoid
- Treating contact-form automation as the identity of the agent.
- Replacing the current orchestrator before the core role model is defined.
- Stuffing the entire run history into every prompt.
- Emitting decorative UI events that do not correspond to real execution.
- Reporting delivery success when the contract gate or approval state says otherwise.
- Falling back to brittle keyword triggers when LLM-semantic classification already exists.

## Final Definition of Done
This roadmap is complete only when Maia behaves like a general execution agent with explicit roles, compiled context, shared interaction semantics, trustworthy verification, resumable handoff, and a theatre that reflects real work rather than simulated activity.
