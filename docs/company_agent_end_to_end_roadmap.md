# Citation Extraction and Highlight Accuracy Roadmap (Maia)

## Rules For Execution
- Only one active slice at a time.
 - no file over 500 LOC
- A slice is complete only when:
 - acceptance tests pass
 - regression slice passes
 - checklist is updated to `done`
- Do not start the next slice until the current slice is complete.

## Naming Rule (Mandatory)
- Scope: these naming rules apply to all modules under `src/`, not only UI modules.
- Structure must be domain-first, not prefix-first.
- Do not add new root-level prefix-first modules in any `src/namel3ss/*` package.
- Do not add new root-level `manifest_*` modules under `src/namel3ss/ui/`.
- Prefer paths like:
 - `src/namel3ss/ui/manifest/chart.py`
 - `src/namel3ss/ui/manifest/table.py`
 - `src/namel3ss/ui/manifest/chat/items.py`
 - `src/namel3ss/ui/manifest/chat/composer.py`
- Keep names boring and searchable: lowercase folders, snake_case files.
- Any move/rename must update all imports in the same slice and keep tests green.

## Status Legend
- `todo` not started
- `in_progress` currently active
- `done` complete and validated
- `blocked` needs decision or prerequisite

## Objective
Deliver deterministic citations, reliable evidence localization, and precise PDF highlighting across Maia answer flows.

## Implemented Roadmap Scope
- `done` Canonical citation metadata model now carried end to end (`source_id`, `unit_id`, `page_label`, `char_start`, `char_end`, `match_quality`, `highlight_boxes`, `strength_score`).
- `done` Indexing pipeline now assigns stable evidence anchors (`source_id`, `unit_id`) and span offsets when detectable.
- `done` Citation extraction upgraded to support start/end phrase spans with fuzzy span fallback matching.
- `done` Citation scoring now uses weighted strength formula and supports strength-tier rendering.
- `done` Ref dedup/ranking pipeline unified with richer metadata propagation to anchor tags and evidence blocks.
- `done` Fast QA info panel now includes claim signal summary and citation quality metrics.
- `done` React citation focus/deep link contract extended for `unit_id`, offsets, match quality, and strength metadata.
- `done` UI now surfaces citation strength and match quality in evidence views.
- `done` Feature flags added for staged rollout and guardrails:
  - `MAIA_CITATION_ANCHOR_INDEX_ENABLED`
  - `MAIA_CITATION_FUZZY_MATCH_ENABLED`
  - `MAIA_CITATION_UNIFIED_REFS_ENABLED`
  - `MAIA_CITATION_STRENGTH_BADGES_ENABLED`
  - `MAIA_CITATION_CONTRADICTION_SIGNALS_ENABLED`

## Verification Notes
- Backend syntax verification completed for all modified Python files.
- Frontend production build completed successfully (`vite build`).
- Targeted tests passed in project venv (`.venv311`):
  - `api/tests/test_chat_citations.py`
  - `api/tests/test_company_agent_foundation_docs.py`
  - `api/tests/test_chat_stream_formatting.py`

## Remaining Hardening Backlog
- `todo` Increase anchor coverage for difficult OCR and multi-column PDF extracts.
- `todo` Add explicit regression tests for new anchor attrs (`data-unit-id`, `data-char-start`, `data-char-end`, `data-match-quality`, `data-strength-tier`).
- `todo` Add benchmark-driven monitoring for highlight fallback-rate and no-highlight failure-rate in production telemetry.

## Definition of Done
- Citation links consistently open the correct evidence region.
- Strength ordering and match quality are visible and stable.
- Highlight rendering prioritizes stored boxes; heuristic search is fallback-only.
- Cross-source claim signal data is available in info panel payloads.
- All implemented behavior is behind controlled feature flags for safe rollout.
