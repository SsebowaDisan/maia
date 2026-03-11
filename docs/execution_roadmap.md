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
Improve agent interaction quality on pages/documents by supporting multiple `interaction_suggestion` events per step and choosing the strongest suggestion deterministically at merge time.

## Status Legend
- `todo` not started
- `in_progress` currently active
- `done` complete and validated
- `blocked` needs decision or prerequisite

## Execution Status
- Current slice: `F1 - multi-suggestion extraction`
- Overall progress: `0/4 slices done`

---

## Frontend Tasks (Current Scope)
Status: `in_progress`

### Slice F1 - Multi-Suggestion Merge Layer Shape
Status: `in_progress`
Targets:
- `frontend/user_interface/src/app/components/agentActivityPanel/interactionSuggestionMerge.ts`
Plan:
- add `highlightText?: string` to `InteractionSuggestion`
- change `extractSuggestionLayer` from `Map<string, InteractionSuggestion>` to `Map<string, InteractionSuggestion[]>`
- append suggestions per key (no replacement)
- change `mergeSuggestion` input from single suggestion to `InteractionSuggestion[] | null`
- inside `mergeSuggestion`, select highest-confidence suggestion, then apply existing logic unchanged
Acceptance:
- multiple backend suggestion events for the same step are retained
- merge result semantics remain unchanged except best-candidate selection

### Slice F2 - Scene Prop Type Update
Status: `todo`
Targets:
- `frontend/user_interface/src/app/components/agentDesktopScene/types.ts`
Plan:
- change `interactionSuggestion?: InteractionSuggestion | null` to `interactionSuggestion?: InteractionSuggestion[] | null`
Acceptance:
- desktop scene prop types align with new merge-layer output

### Slice F3 - Derived State Type Propagation
Status: `todo`
Targets:
- `frontend/user_interface/src/app/components/agentActivityPanel/useAgentActivityDerived.ts`
Plan:
- change active suggestion memo type from `InteractionSuggestion | null` to `InteractionSuggestion[] | null`
- keep `.get(key) || null` fallback behavior
Acceptance:
- active suggestion selection remains key-based but returns full suggestion list for that key

### Slice F4 - Compile Flow in Desktop Scene
Status: `todo`
Targets:
- `frontend/user_interface/src/app/components/agentDesktopScene/app.tsx`
Plan:
- keep merge call-site unchanged in behavior
- ensure type flow compiles cleanly once F1-F3 are in place
Acceptance:
- scene compiles with array-based suggestion input and unchanged interaction rendering behavior

---

## Delivery Order
1. `F1`
2. `F2`
3. `F3`
4. `F4`

## Exit Criteria
- suggestion layer stores all suggestions per step key
- merge chooses highest-confidence suggestion deterministically
- derived + scene type flow compiles without widening unsafe types
- no Theatre layout/structure/design changes
