# Maia Universal Theatre Flow and Design Specification

## Purpose
Define one deterministic, premium Theatre experience for all agent tasks in Maia. The same flow must work for browser research, documents, spreadsheets, API/SAP data pulls, and email composition without modality-specific UX forks.

This document is a product + engineering contract for:
- UX behavior
- stage transitions
- surface commit rules
- failure and manual override handling
- implementation ownership across frontend and backend modules

## Design Intent
Theatre should show what the agent is doing now, not what might happen next.

Core principles:
- System-first clarity: start in a calm, dark stage that explains intent before showing a tool surface.
- Progressive reveal: only show a surface after explicit commit signals.
- One narrative pipeline: every task follows the same stage model.
- Minimal, high-signal UI: emphasize current step; reduce chrome and noise.
- Trust through visibility: live actions, checkpoints, and confirmation before irreversible actions.

## Current Behavior Summary (as implemented)
These points describe the current baseline behavior in code:
- Event playback is cursor-driven with deterministic ordering and `visibleEvents = orderedEvents.slice(0, safeCursor + 1)`.
- Scene selection uses anti-flicker fallback: if active event is system, scene can stay on last non-system event.
- `previewTab` initializes to `browser` and resets to `browser` when a new streaming run starts.
- Streaming tab switching suppresses system takeover: if derived `sceneTab` is `system`, it keeps current `previewTab`.
- Browser URL derivation includes broad fallback that can resolve URLs from any event text.
- Tasks (`ResearchTodoList`) are currently surfaced in `CinemaOverlay`, not the default `ActivityPanelBody`.
- `SystemScene` uses fixed planner copy for some planning event prefixes instead of always using dynamic narration.

Primary modules:
- `frontend/user_interface/src/app/components/agentActivityPanel/app.tsx`
- `frontend/user_interface/src/app/components/agentActivityPanel/useAgentActivityDerived.ts`
- `frontend/user_interface/src/app/components/agentActivityPanel/contentDerivation.ts`
- `frontend/user_interface/src/app/components/agentActivityPanel/helpers.ts`
- `frontend/user_interface/src/app/components/agentActivityPanel/roadmapDerivation.ts`
- `frontend/user_interface/src/app/components/agentActivityPanel/ResearchTodoList.tsx`
- `frontend/user_interface/src/app/components/agentActivityPanel/ActivityPanelBody.tsx`
- `frontend/user_interface/src/app/components/agentActivityPanel/CinemaOverlay.tsx`
- `frontend/user_interface/src/app/components/agentDesktopScene/app.tsx`
- `frontend/user_interface/src/app/components/agentDesktopScene/SystemFallbackScenes.tsx`
- `frontend/user_interface/src/app/components/agentActivityMeta/tabs.ts`

## Universal Theatre Pipeline
All runs must follow this stage pipeline:

1. Understand
- Visual: dark system stage.
- Message: concise dynamic narration, for example `Understanding your request...`.
- Output: parsed intent, initial scope, constraints.

2. Breakdown
- Visual: system stage remains active.
- Message: plan-ready narration.
- Output: visible roadmap/todo list with ordered steps and one active step.

3. Analyze
- Visual: system stage with progress cues while source/data is loading.
- Message: `Fetching data...`, `Loading document...`, `Preparing draft...`.
- Output: modality-specific commit signal candidates.

4. Surface
- Visual: browser/docs/sheets/pdf/email/API scene.
- Message: live interaction narration and action trace.
- Output: user-visible edits/navigation/extraction in real time.

5. Execute
- Visual: committed surface stays stable while work continues.
- Message: incremental progress and completed task checks.
- Output: draft content or prepared action.

6. Review
- Visual: clean summary stage with completed tasks and pending confirmations.
- Message: clear irreversible-action warning if needed.
- Output: explicit user decision point.

7. Confirm
- Visual: minimal action screen.
- Message: single primary CTA (`Send`, `Save`, `Apply`, `Submit`) plus back.
- Output: final execution command.

8. Done and Reset
- Visual: brief completion cue, then neutral idle Theatre state.
- Message: action receipt where applicable.
- Output: ready for next run.

## Deterministic Orchestration Model
Use two composed state machines:

1. `StageMachine` (narrative flow)
- Owns current user-facing stage.
- Inputs: phase signals, user controls, run lifecycle, review requirements.

2. `SurfaceCommitMachine` (modality truth)
- Owns whether each surface is committed and with what payload.
- Inputs: tool/runtime events and metadata.

Composition rule:
- `StageMachine` may request a surface stage.
- Surface stage is only entered when `SurfaceCommitMachine` has a valid commit for that modality.

This split prevents state explosion and keeps routing explainable.

## StageMachine Contract

### States
- `idle`
- `understand`
- `breakdown`
- `analyze`
- `surface`
- `execute`
- `review`
- `confirm`
- `done`
- `blocked`
- `needs_input`
- `error`

### Required events
- `run_started`
- `intent_parsed`
- `plan_ready`
- `analysis_started`
- `analysis_progress`
- `surface_commit_available`
- `execution_progress`
- `execution_ready_for_review`
- `confirmation_required`
- `confirmation_granted`
- `confirmation_denied`
- `run_completed`
- `run_failed`
- `run_blocked`
- `user_input_required`
- `user_input_received`
- `user_cancelled`
- `user_tab_override`

### Guard examples
- `understand -> breakdown` only when plan/roadmap exists or intent parsing completed.
- `analyze -> surface` only when commit exists for target modality.
- `execute -> review` when irreversible action is pending or explicit review policy requires it.
- `confirm -> done` only on confirmed success event.

### Entry action examples
- `understand`: show dynamic understanding narration.
- `breakdown`: render roadmap in default Theatre, set active roadmap index.
- `surface`: set `previewTab` to committed tab.
- `review`: freeze auto-tab switching and present summary.
- `done`: show completion cue, then auto-reset.

## SurfaceCommitMachine Contract

### Surface commit definition
A surface is committed when there is strong evidence the agent actually entered or mutated that surface. Prompt text and speculative URLs are never commit evidence.

### Commit signals by modality

| Modality | Required commit signal examples | Non-commit examples |
|---|---|---|
| Browser | `opened_pages` append, explicit navigation URL fields on browser-like events, browser snapshot refs | URL string in unrelated title/detail |
| Docs | `document_url`, docs open/edit event family, explicit `scene_surface=google_docs/docs` | generic plan text mentioning docs |
| Sheets | `spreadsheet_url`, sheets open/edit event family, explicit `scene_surface=google_sheets/sheets` | generic plan text mentioning sheet |
| PDF | resolvable PDF URL/file + PDF event signals (`pdf_*`) or PDF playback metadata | non-PDF link with `.pdf` in free text only |
| Email | draft/create/set/to/subject/body/send lifecycle events, explicit email surface metadata | mention of email recipient in planning text |
| API/SAP | API runtime event family, connector execution lifecycle + payload schema | mention of SAP in prompt only |

### Commit payload shape (recommended)
```ts
type SurfaceCommit = {
  surface: "browser" | "document" | "email" | "api";
  subtype?: "docs" | "sheets" | "pdf" | "sap" | string;
  sourceUrl?: string;
  committedEventId: string;
  committedAt: string;
  confidence: "high" | "medium";
};
```

## Routing Rules

1. System-first
- New streaming run sets stage to `understand`.
- Effective visible tab is `system` until stage gate opens.

2. Phase gate
- For phases `understanding`, `contract`, `clarification`, `planning`, stage remains system.
- For `execution` and later, system remains active until a valid surface commit exists.

3. Surface stability
- Once in `surface`/`execute`, keep committed surface stable.
- System/meta events update narration and roadmap without forced tab flicker.

4. Browser URL safety
- Browser URL resolution must never scan arbitrary non-browser events as fallback.
- Empty browser URL is valid before commit.

5. Manual override
- If user switches tab during auto-staged flow, enter override mode with deterministic resume policy.
- Suggested default: user override pauses auto-routing for current run until user presses `Resume Auto`.

## UX and Motion Guidance

### Visual hierarchy
- Dark neutral system stage for non-surface phases.
- One focal message at a time.
- Keep secondary context (timeline, metrics) visually subordinate.

### Copy style
- Use short, neutral, action-oriented copy.
- Avoid modality hardcoding in generic stage messages.
- Prefer event-derived narration over static placeholder text.

### Motion
- Use subtle fades and small positional transitions.
- Use completion micro-feedback for step completion.
- Respect `prefers-reduced-motion`.

### Interaction model
- Hide non-essential chrome by default in surface mode.
- Keep core controls discoverable: pause/play, back, review, confirm.
- Preserve keyboard accessibility and visible focus states.

### Accessibility
- High contrast text in dark stages.
- Announce stage changes with screen-reader friendly labels.
- Ensure all confirmation flows are keyboard navigable.

## Error, Blocked, and Needs Input States

### `blocked`
- Triggered by policy or trust gates.
- Must present reason, impact, and allowed actions.
- Supports `approve`, `cancel`, or `request changes`.

### `needs_input`
- Triggered when credentials or human data is required.
- Must suspend auto-progression and show explicit input request.

### `error`
- Triggered by non-recoverable runtime failure.
- Must provide retry path and preserve completed work context.

## Data Contract Recommendations
To reduce prefix heuristics over time, standardize metadata:
- `scene_surface` (already used): authoritative surface hint.
- `event_family`: normalized family (`browser`, `docs`, `sheets`, `email`, `api`, `system`).
- `tool_id`: consistent tool identity.
- `ui_stage` (new): optional explicit stage hint.
- `ui_target` (new): optional explicit target tab/surface.
- `ui_commit` (new): optional explicit commit payload.

Frontend should treat these as primary and keep prefix mapping as fallback compatibility.

## Implementation Mapping

### Frontend changes (priority order)
1. System-first routing
- `agentActivityPanel/app.tsx`
- Initialize and run-start reset `previewTab` to `system`.
- Replace `sceneTab === "system" ? previewTab : sceneTab` suppression with stage-gated routing.

2. URL commitment hardening
- `agentActivityPanel/contentDerivation.ts`
- Remove broad fallback loops that recover URL from any event.
- Resolve browser URL only from committed browser signals.

3. Stage derivation
- Add pure stage derivation helper, for example `deriveTheatreStage.ts`.
- Inputs: phase (`phaseForEvent`), commit state, review requirements, manual override.

4. Surface commit derivation
- Extend `useAgentActivityDerived.ts` to compute and expose `surfaceCommit`.
- Prefer merged `opened_pages`, explicit URLs, scene metadata, and event families.

5. Task visibility in default Theatre
- `ActivityPanelBody.tsx` and/or `SystemFallbackScenes.tsx`
- Render roadmap/todo in the main Theatre stage, not only Cinema.

6. Dynamic system narration
- `SystemFallbackScenes.tsx`
- Prefer live `sceneText` and active event detail/title over fixed planner-copy replacements.

7. Heuristic reduction
- `agentActivityMeta/tabs.ts`, `interactionSemantics.ts`, `ResearchTodoList.tsx`
- Keep prefix logic as fallback only, prioritize metadata and plan-derived roadmap.

### Backend and orchestration alignment
- `api/services/chat/app_stream_orchestrator.py`
- Agent orchestration event builders under `api/services/agent/...`
- Emit consistent `scene_surface`, `event_family`, `tool_id`, and commit-ready metadata fields.

## Test Plan

### Unit tests
1. Stage gating
- New pure tests for `deriveTheatreStage`.
- Assert system stage across early phases and until commit exists.

2. Browser URL regression
- `contentDerivation` tests for prompt URL leakage prevention.
- Assert no browser URL from non-browser planning text.

3. Commit detection
- `useAgentActivityDerived` tests for browser/docs/sheets/email/api commit extraction.

4. Roadmap visibility
- UI tests ensuring tasks render in default Theatre when roadmap exists.

5. Narration behavior
- System scene tests ensuring dynamic narration priority and sensible fallback text.

### Integration tests
1. End-to-end staged replay
- Simulated run: understanding -> plan -> browser commit -> email draft -> review -> confirm.
- Assert visible stage and tab transitions are deterministic.

2. Manual override
- Assert user tab override pauses auto-routing and resume behavior is deterministic.

3. Error and blocked paths
- Assert transition to `error`/`blocked`/`needs_input` with clear recover actions.

## Acceptance Criteria
- New runs always start in system stage.
- No surface is shown before a valid commit signal.
- URL in prompt alone never populates browser scene.
- Roadmap is visible in default Theatre when plan data exists.
- Irreversible actions always route through review/confirm gate.
- Manual override behavior is predictable and test-covered.
- Accessibility and reduced-motion requirements are met.

## Rollout Strategy
1. Phase A: correctness guardrails
- System-first tab reset + remove aggressive URL fallbacks.

2. Phase B: deterministic staging
- Add stage/commit derivation and wire routing.

3. Phase C: UX polish
- Upgrade system stage narration, tasks presentation, and transitions.

4. Phase D: metadata-first contract
- Gradually shift from prefix heuristics to emitted metadata as primary signal.

## Notes
- Preserve existing anti-flicker scene fallback logic during execution; it remains useful once surface is committed.
- Keep backwards compatibility with legacy event streams while adding metadata-first routing.
