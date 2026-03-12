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
The mindmap now behaves like a NotebookLM-style research artifact: horizontal by default, branch-oriented, calmer in chrome, and finished at the bottom edge.

## Analysis
- Completed in this roadmap:
  - first-open mindmap defaults to a horizontal left-to-right tree
  - `collapse all` returns to a useful overview instead of a dead or fully exploded state
  - the popup header is flatter and more editorial
  - the toolbar is quieter and more subordinate to the content
  - the right inspector remains stable and no bottom tray is needed
  - the tree density and bottom finish now support scanning without large dead zones
- No active frontend slices remain in this roadmap.

## Status Legend
- `todo` not started
- `in_progress` currently active
- `done` complete and validated
- `blocked` needs decision or prerequisite

## Execution Status
- Current slice: `none`
- Overall progress: `3/3 slices done`

---

## Active Frontend Work
- No active frontend slices remain in this roadmap.

## Exit Criteria
- the mindmap opens as a horizontal left-to-right tree by default
- branch disclosure works as a progressive overview rather than a fully exploded graph
- the header and toolbar read as one calm artifact surface
- the inspector remains in the right rail only
- the bottom of the popup ends with a soft, deliberate finish
- no Theatre layout, structure, or design changes are introduced

