# Core Agent Execution Roadmap (LLM-Semantic, Core-First)

## Objective
Build Maia as a general execution agent with this runtime order:

`understand -> discover -> act -> verify -> ask only if still blocked`

This roadmap prioritizes core-agent capabilities first, then adds goal-specific navigation as an optional module.

## Non-Negotiable Rule: LLM Semantic Decisions, Not Hardcoded Word Lists
Use LLM semantic reasoning for planning/discovery/routing decisions.

Allowed deterministic logic:
- URL/email/phone format validation
- Safety and policy gates
- Schema and type validation

Not allowed for decision-making:
- Hardcoded keyword lists that decide intent, blockers, routing, or slot classification

## Build Order
1. Stage 1 (Execution Kernel)
2. Stage 2 (Discover-First Task Contract)
3. Stage 4 (Live Theatre)
4. Stage 5 (Unified Interaction Pipeline)
5. Stage 6 (Human Verification + Resume)
6. Optional Module: `goal_page_discovery.py` behind capability/intent flag

## Execution Status (2026-03-06)
- [x] Stage 1 completed
- [x] Stage 2 completed (semantic slot/blocker alignment enabled)
- [x] Stage 4 completed (action-grounded overlay + strict cursor source)
- [x] Stage 5 completed (shared interaction normalization in stream pipeline)
- [x] Stage 6 completed (pause/resume handoff state wired end-to-end)
- [x] Optional `goal_page_discovery.py` module completed behind capability/intent gating

---

## Stage 1: Execution Kernel (Core)

### Goal
Create one execution contract for browser interactions with structured state and verification semantics.

### Files
- `api/services/agent/execution/browser_runtime.py`
- `api/services/agent/execution/browser_event_contract.py`
- `api/services/agent/execution/browser_action_models.py`
- `api/services/agent/connectors/browser_connector.py`
- `api/services/agent/tools/browser_tools.py`
- `api/services/agent/orchestration/stream_bridge.py`

### Work
1. Enforce one action vocabulary for browser actions:
   - `navigate`, `hover`, `click`, `type`, `scroll`, `extract`, `verify`
2. Ensure each event carries:
   - cursor position (percent)
   - scroll direction/percent when relevant
   - target payload
   - snapshot reference
   - result metadata (`status`, `phase`, confidence if available)
3. Apply normalization consistently for all browser-like traces (not only specific tool paths).
4. Fix taxonomy drift where emitters/UI/contracts disagree on event names.

### Definition of Done
- Every browser action event is machine-normalized.
- Event consumers can render actions without tool-specific branching.
- Tests validate normalization and metadata completeness.

---

## Stage 2: Discover-First Task Contract (Core)

### Goal
Make clarification truly last-resort using typed slot resolution and autonomous discovery attempts.

### Files
- `api/services/agent/orchestration/contract_slots.py`
- `api/services/agent/orchestration/discovery_gate.py`
- `api/services/agent/llm_contracts.py`
- `api/services/agent/contract_verification.py`
- `api/services/agent/orchestration/task_preparation.py`
- `api/services/agent/orchestration/step_execution_sections/guards.py`

### Work
1. Keep missing requirements in typed slots only:
   - `description`
   - `discoverable`
   - `blocking`
   - `confidence`
   - `evidence_sources`
   - `resolved_value`
2. Add slot lifecycle states:
   - `open`, `attempting_discovery`, `resolved`, `blocked`
3. Trigger clarification only after:
   - discovery attempts are executed
   - slot remains blocking and unresolved
4. Replace keyword-driven blocking logic with LLM semantic slot classification.

### Definition of Done
- Maia does not ask for values that can be discovered.
- Clarification is emitted only after autonomous attempts fail.
- Slot state and evidence are visible in run metadata.

---

## Stage 4: Live Theatre (Core)

### Goal
Make theatre playback action-grounded and consistent across browser, docs, sheets, PDF.

### Files
- `frontend/user_interface/src/app/components/agentDesktopScene/BrowserScene.tsx`
- `frontend/user_interface/src/app/components/agentDesktopScene/DocumentScenes.tsx`
- `frontend/user_interface/src/app/components/agentActivityPanel/DesktopViewer.tsx`
- `frontend/user_interface/src/app/components/agentActivityPanel/useAgentActivityDerived.ts`
- New: `frontend/user_interface/src/app/components/agentDesktopScene/InteractionOverlay.tsx`
- New: `frontend/user_interface/src/app/components/agentDesktopScene/sceneEvents.ts`

### Work
1. Centralize event-to-overlay mapping in `sceneEvents.ts`.
2. Move reusable overlay rendering to `InteractionOverlay.tsx`.
3. Drive cursor/click/scroll visuals strictly from event payload, not fallback guesses.
4. Ensure PDF scan focus and page movement reflect real event data.
5. Normalize coordinate systems to percentages across all emitters.

### Definition of Done
- Cursor movement visibly tracks actual actions.
- Click/scroll/type states are consistently shown.
- PDF playback is scan/interaction-driven, not static.

---

## Stage 5: Unified Interaction Pipeline (Core)

### Goal
Unify action/event semantics across web research, browser execution, and document/PDF flows.

### Files
- `api/services/agent/tools/research_tools.py`
- `api/services/agent/tools/document_highlight_tools.py`
- `api/services/agent/connectors/browser_connector.py`
- `api/services/agent/orchestration/stream_bridge.py`

### Work
1. Standardize event envelope fields and action metadata across tools.
2. Map tool-specific events to shared action vocabulary where possible.
3. Keep source-specific details in metadata, not in event-type proliferation.
4. Ensure theatre receives one consistent interaction schema.

### Definition of Done
- Search results, opened pages, and PDFs emit compatible live actions.
- UI no longer needs separate bespoke parsing rules per tool family.

---

## Stage 6: Human Verification + Resume (Core)

### Goal
Support explicit pause/resume for human verification barriers (CAPTCHA, auth prompts, protected flows).

### Files
- New: `api/services/agent/orchestration/handoff_state.py`
- `api/services/agent/orchestration/task_preparation.py`
- `api/services/agent/orchestration/step_execution_sections/guards.py`
- `api/services/agent/orchestration/finalization.py`
- `api/services/agent/tools/browser_tools.py`

### Work
1. Introduce persisted handoff state model:
   - `pause_reason`
   - `handoff_url`
   - `resume_token`
   - `paused_at`
   - `resume_status`
2. Convert barrier handling to runtime pause, not only final review note.
3. Resume execution from pause point once user completes verification.
4. Keep honest messaging: no fake automatic CAPTCHA solving.

### Definition of Done
- Barrier paths are resumable.
- Run state transitions: `running -> paused_for_human -> resumed -> completed`.
- User-visible events clearly show pause and resume lifecycle.

---

## Optional Capability Module: `goal_page_discovery.py`

### Purpose
Generic goal-oriented website navigation capability for any task, not just contact forms.

### Files
- New: `api/services/agent/connectors/browser_goal/goal_page_discovery.py`
- `api/services/agent/connectors/browser_contact/contact_discovery.py` (thin wrapper)
- `api/services/agent/llm_intent.py`
- `api/services/agent/orchestration/step_planner_sections/capability_planning.py`
- `api/services/agent/orchestration/step_planner_sections/intent_enrichment.py`

### Gating
Feature flag:
- `agent.capabilities.goal_page_discovery_enabled` (default `false`)

Intent/capability routing:
- Add intent tag for generic goal-page navigation
- Planner inserts goal discovery only when both intent + capability are active

### Work
1. Build generic goal profile input:
   - goal description
   - expected evidence
   - constraints
2. Use LLM semantic ranking of candidate pages (no hardcoded route keywords).
3. Expose reusable traces for theatre and contract verification.
4. Keep contact-form flow as an optional consumer of this module.

### Definition of Done
- Goal discovery can support non-contact tasks.
- Contact flow still works via wrapper with no regressions.
- Capability remains opt-in and safely disabled by default.

---

## Cross-Stage Quality Gates

1. Contract Gate
- Required facts/actions must remain machine-checkable.
- No downgrade from semantic slot logic to keyword heuristics.

2. Event Contract Gate
- Mandatory fields present on interaction events.
- Backward compatibility for existing event consumers.

3. Theatre Gate
- Same run renders correctly for browser/document/PDF/email/system tabs.

4. Resume Gate
- Pause/resume state survives process boundaries and can be replayed.

---

## Suggested Milestones

1. Milestone A (Stages 1 + 2)
- Core execution and clarification behavior corrected.

2. Milestone B (Stages 4 + 5)
- Unified, human-legible live theatre and interaction schema.

3. Milestone C (Stage 6)
- Production-safe human handoff and resume lifecycle.

4. Milestone D (Optional module)
- `goal_page_discovery.py` available behind capability flag.

---

## Implementation Notes for This Repo

1. Keep existing `contact_form_submission` capability, but do not couple core-agent progress to outreach features.
2. Prioritize fixing event taxonomy mismatches before adding new UI logic.
3. Treat LLM semantic routing as default for discovery/planning decisions.
4. Preserve deterministic validation primitives, but avoid hardcoded decision keyword lists.
