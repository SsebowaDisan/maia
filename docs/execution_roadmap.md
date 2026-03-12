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
Improve citation interaction so web-source citations open immediately when appropriate, power users can bypass the info-panel flow with modifier clicks, and evidence-section anchors always have valid scroll targets.

## Status Legend
- `todo` not started
- `in_progress` currently active
- `done` complete and validated
- `blocked` needs decision or prerequisite

## Execution Status
- Current slice: `none`
- Overall progress: `3/3 slices done`

---

## Implementation Slices
Status: `done`

No open slices. This roadmap is complete.

## Delivery Order
Completed.

## Exit Criteria
- web-only citations open directly with one click
- modifier-click and middle-click provide direct source navigation on any URL-backed citation
- evidence citation anchors always resolve to valid scroll targets
- no Theatre layout/structure/design changes are introduced
