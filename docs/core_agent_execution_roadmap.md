# Maia Core Agent Execution Roadmap

## Focus
Transform MAIA's mind-map into a live AI Work Graph that shows how micro-agents plan, act, verify, cite evidence, and hand work across theatre, evidence, and chat.

## Rules For Execution
- Only one active slice at a time.
- No file over 500 LOC.
- Use LLM-semantic reasoning for routing and decisions; no hardcoded words as the primary decision mechanism.
- No shortcuts: implement the full slice acceptance path (code, tests, checklist update) before moving on.
- Every user-facing step must meet Apple-level professional quality with clear, polished craftsmanship.
- A slice is complete only when acceptance tests pass, regression slice passes, and checklist is updated to `done`.
- Do not start the next slice until the current slice is complete.
- After a slice is `done`, automatically move the next `todo` slice to `in_progress`.
- At the end of each phase, always run full regression: `PYTHONPATH=.:libs/maia pytest`, `cd frontend/user_interface && npm test`, `cd frontend/user_interface && npm run build`.
- Delete completed stages when the roadmap is done so only active planning content remains.

## Naming Rule (Mandatory)
- Scope: applies to Maia modules under `api/` and `frontend/user_interface/src/`.
- Structure must be domain-first, not prefix-first.
- Do not add new root-level catch-all modules when an existing domain folder fits.
- Keep names boring and searchable: lowercase folders, snake_case files.
- Any move/rename must update all imports in the same slice and keep tests green.

## Status Legend
- `todo` not started
- `in_progress` currently active
- `done` complete and validated
- `blocked` needs decision or prerequisite

## Current Active Slice
- None (`done`) - information panel verification roadmap implemented and validated.

## Completion Summary
- `WG1` complete: backend Work Graph domain, run APIs, snapshot persistence.
- `WG2` complete: run-scoped store, dedicated viewer, live hydration.
- `WG3` complete: ELK layout, swimlanes, custom node/edge rendering.
- `WG4` complete: graph↔theatre sync, evidence/verifier node actions.
- `WG5` complete: search/filter/collapse/focus UX, collaboration abstraction with presence/comments.
- `WG6` complete: external ingestion/status/evidence API contract and analytics (critical path, congestion, verifier hotspots, low-confidence clusters).
- `VP1` complete: end-user information panel reframed around verification with AI Work Graph first and verification surface below.
- `VP2` complete: source bar added with source type/status, evidence count, and conversation-level memory for source/evidence/zoom.
- `VP3` complete: review viewer upgraded with deterministic citation jumps, previous/next evidence controls, and PDF zoom controls.
- `VP4` complete: evidence strip redesigned for compact verification with short snippets and quality signaling.
- `VP5` complete: trust features added (exact/context evidence mode, semantic find, evidence trail, compare view, trust warnings).

## Next Roadmap Template
- Add new phases/slices here when a new roadmap is approved.
