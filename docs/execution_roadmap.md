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
Complete frontend highlight reliability so backend 420-char citation phrases and char offsets are preserved end-to-end in PDF focus and citation preview.

## Analysis
- Backend now emits phrase windows up to 420 chars and can emit char offsets.
- Frontend must avoid re-truncation and must prefer char-offset highlighting before fuzzy search.
- Scanned-PDF text-layer gaps remain an ingestion concern (bounding boxes), not a frontend rendering concern.

## Status Legend
- `todo` not started
- `in_progress` currently active
- `done` complete and validated
- `blocked` needs decision or prerequisite

## Execution Status
- Current slice: `none`
- Overall progress: `5/5 slices done`

---

## Frontend Highlight Slices
1. **FHI-01 - Match backend phrase length in citation extract normalization**
   - status: `done`
   - file: `frontend/user_interface/src/app/components/chatMain/citationFocus.ts`
   - change: `MAX_EXTRACT_CHARS` aligned to 420

2. **FHI-02 - Strengthen sentence cut threshold for long phrases**
   - status: `done`
   - file: `frontend/user_interface/src/app/components/chatMain/citationFocus.ts`
   - change: sentence/word cut threshold aligned to 200 for 420-char phrases

3. **FHI-03 - Char offset highlighting before fuzzy candidate search**
   - status: `done`
   - files:
     - `frontend/user_interface/src/app/components/CitationPdfPreview.tsx`
     - `frontend/user_interface/src/app/components/citationPdfPreviewFocus.ts`
     - `frontend/user_interface/src/app/components/citationPdfHighlight.ts`
   - change: `tryFocusHighlight` resolves `findRangeByCharOffsets(...)` before `findHighlightRange(...)`

4. **FHI-04 - Pass char offsets from citation focus into PDF preview**
   - status: `done`
   - file: `frontend/user_interface/src/app/components/infoPanel/CitationPreviewPanel.tsx`
   - change: pass `charStart={citationFocus.charStart}` and `charEnd={citationFocus.charEnd}` to `CitationPdfPreview`

5. **FHI-05 - Prioritize first complete sentence in candidate ordering**
   - status: `done`
   - files:
     - `frontend/user_interface/src/app/components/citationPdfHighlight.ts`
     - `frontend/user_interface/src/app/components/citationPdfHighlight.test.ts`
   - change: ensure first full sentence is candidate index 0, then rank remaining candidates by length

## Exit Criteria
- 420-char backend phrases are never shortened again by frontend normalization
- char offsets are used first for exact multi-span highlight reconstruction
- citation preview passes offset metadata end-to-end
- fuzzy candidate fallback still works when offsets are absent
- first sentence is always the lead fuzzy candidate
