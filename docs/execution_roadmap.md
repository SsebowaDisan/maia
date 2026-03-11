# Maia Execution Roadmap

## Rules For Execution
1. Only one active slice at a time.
2. No file over 500 LOC.
3. A slice is complete only when:
   - acceptance tests pass
   - regression slice passes
   - checklist is updated to `done`
4. Do not start the next slice until the current slice is complete.
5. Use LLM reasoning for semantic decisions; do not rely on hardcoded words, brittle keyword lists, or shortcut phrase matching.
6. No shortcuts in delivery quality: every step must be production-grade and complete.
7. End-user surfaces must stay Apple-like: low noise, strong hierarchy, calm motion, clear typography, no debug leakage.
8. Keep the execution quality professional and consistent with the roadmap design standards.
9. When this roadmap is completed, remove or delete completed stages so the active roadmap only contains unfinished work.
10. Prefer LLM-first implementations wherever feasible for interpretation, routing, and task semantics; use hardcoded mappings only as guarded fallback paths.
11. Do not change the Theatre layout, structure, or visual design in this roadmap; limit work to behavioral/event-state fixes unless a design change is explicitly requested.

## Objective
Introduce typed assistant message blocks, an interactive thin-lens widget, and a synced canvas document panel without breaking the existing chat, theatre, or conversation history flows.

## Status Legend
- `todo` not started
- `in_progress` currently active
- `done` complete and validated
- `blocked` needs decision or prerequisite

## Execution Status
- Current slice: `S5 - streaming, validation, and regression`
- Overall progress: `4/5 slices done`

---

## Implementation Slices
Status: `in_progress`

### Slice S1 - Block Contract And Compatibility
Status: `done`
Targets:
- `api/schemas.py`
- `api/services/chat/app.py`
- `api/services/chat/app_stream_orchestrator.py`
- `api/services/chat/app_stream_pipeline.py`
- `api/services/chat/fast_qa_turn_helpers.py`
- `frontend/user_interface/src/api/client/types.ts`
- `frontend/user_interface/src/app/types.ts`
- `frontend/user_interface/src/app/appShell/eventHelpers.ts`
- `frontend/user_interface/src/app/appShell/conversationChat/sendMessage.ts`
Plan:
- define a typed block/document schema with additive optional fields on existing chat responses
- preserve `answer: string` and existing SSE text behavior as the compatibility path
- persist turn blocks in `message_meta`
- persist canvas documents in conversation data so reloads do not lose document state
- hydrate `ChatTurn` with optional block/document payloads while preserving older conversations
Acceptance:
- legacy conversations with only `assistant` text still render unchanged
- new responses may include `blocks` and `documents` without breaking current clients
- conversation reload preserves structured turn content and synced documents

### Slice S2 - Frontend Block Renderer
Status: `done`
Targets:
- `frontend/user_interface/src/app/components/messages/MessageBlocks.tsx`
- `frontend/user_interface/src/app/components/messages/BlockRenderer.tsx`
- `frontend/user_interface/src/app/components/chatMain/turns/TurnListItem.tsx`
- `frontend/user_interface/src/app/components/chatMain/types.ts`
Plan:
- add typed rendering for `text`, `markdown`, `math`, `code`, `image`, `table`, `notice`, `widget`, and `document_action`
- use a block-first render path with string fallback for older turns
- reuse the existing markdown safety model unless a block requires a richer markdown pipeline
Acceptance:
- assistant turns render blocks deterministically
- old string-only assistant turns still render exactly as before
- unsupported or malformed blocks fail safely without crashing the turn UI

### Slice S3 - Lens Equation Widget
Status: `done`
Targets:
- `frontend/user_interface/src/app/components/widgets/LensEquationWidget.tsx`
- `frontend/user_interface/src/app/components/widgets/registry.ts`
Plan:
- implement the thin lens equation simulator with typed props and deterministic physics
- support focal length/object distance controls, real-vs-virtual classification, and SVG diagram rendering
- register the widget through a closed widget registry
Acceptance:
- the widget renders from a `widget` block with no ad-hoc turn logic
- object/focal changes update image distance and diagram correctly
- no layout regressions are introduced in the chat surface

### Slice S4 - Canvas Document Panel
Status: `done`
Targets:
- `frontend/user_interface/src/app/stores/canvasStore.ts`
- `frontend/user_interface/src/app/components/canvas/CanvasPanel.tsx`
- `frontend/user_interface/src/app/components/chatMain/app.tsx`
- `frontend/user_interface/src/app/components/messages/BlockRenderer.tsx`
Plan:
- create a synced canvas/document store for open documents and active document selection
- open the canvas from `document_action` blocks and upsert payload-backed documents into the store
- mount the panel without breaking the existing chat/theatre structure
- start with markdown editing that is stable and production-safe
Acceptance:
- document-action blocks open the requested document in the canvas panel
- document edits update the active store state immediately
- refreshing a conversation can restore persisted document content

### Slice S5 - Streaming, Validation, And Regression
Status: `in_progress`
Targets:
- `frontend/user_interface/src/api/client/chat.ts`
- `frontend/user_interface/src/app/components/messages/*.test.tsx`
- `frontend/user_interface/src/app/components/widgets/*.test.tsx`
- `frontend/user_interface/src/app/stores/*.test.ts`
- relevant backend tests for chat schema and persistence
Plan:
- keep initial streaming compatible by delivering final structured payloads even if text deltas remain string-based
- add validation tests for block/document schemas and malformed payload handling
- add frontend coverage for block fallback, widget rendering, and document-action canvas opening
Acceptance:
- build and targeted tests pass
- block/document payloads are validated end-to-end
- legacy string-only responses remain stable

## Delivery Order
1. `S1`
2. `S2`
3. `S3`
4. `S4`
5. `S5`

## Exit Criteria
- assistant messages support a typed block contract with string fallback compatibility
- lens equation responses can render an interactive widget via the registry
- document-action blocks can open synced canvas documents
- structured content persists across conversation reloads
- no Theatre layout/structure/design changes are introduced
